# licensing/manager.py
"""
Quantoryx — Licensing and Subscription Management Module.

Manages cryptographically signed license validation keys, device activation limits, 
offline grace period checkpoints, and premium feature gating [10].
"""

import os
import sys
import json
import base64
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger

logger = get_logger("licensing.manager")


@dataclass
class LicenseMetadata:
    """Structure holding authenticated license parameters."""
    license_key: str
    owner_email: str
    tier: str                      # "STANDARD", "PREMIUM", "ENTERPRISE"
    expires_at: datetime
    device_limit: int
    activated_devices: List[str] = field(default_factory=list)
    is_active: bool = True
    last_verified_at: datetime = field(default_factory=datetime.utcnow)


class LicensingManager:
    """
    Orchestrates local license security, feature access checks, and grace periods [10].
    """

    def __init__(self, salt: str = "QuantoryxSecureSalt2026"):
        self.salt = salt
        self.active_license: Optional[LicenseMetadata] = None
        self.checkpoint_filename = "data/.license_checkpoint"

    def validate_license_key(self, key_str: str, signature_block: str, expected_payload: Dict[str, Any]) -> bool:
        """
        Cryptographically verifies the authenticity of a license key signature [10].
        Prevents local license spoofing by validating SHA-256 verification hashes.
        """
        try:
            # Reconstruct the expected hash block
            payload_str = json.dumps(expected_payload, sort_keys=True)
            raw_signature = f"{key_str}:{payload_str}:{self.salt}"
            calculated_hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()

            if calculated_hash == signature_block:
                # Map payload parameters to active metadata
                expires_dt = datetime.fromisoformat(expected_payload["expires_at"])
                
                self.active_license = LicenseMetadata(
                    license_key=key_str,
                    owner_email=expected_payload["email"],
                    tier=expected_payload.get("tier", "STANDARD").upper(),
                    expires_at=expires_dt,
                    device_limit=int(expected_payload.get("device_limit", 1)),
                    activated_devices=expected_payload.get("activated_devices", []),
                    is_active=expected_payload.get("is_active", True),
                    last_verified_at=datetime.utcnow()
                )
                
                logger.info("License key %s verified successfully. Active Tier: %s", key_str, self.active_license.tier)
                return True
            else:
                logger.error("License validation failed: Signature block mismatch.")
                return False
        except Exception as e:
            logger.error("Exception triggered during license validation: %s", str(e))
            return False

    # =====================================================================
    # DEVICE LIMIT AUDITS
    # =====================================================================

    def activate_device(self, device_id: str) -> bool:
        """
        Registers and activates a specific hardware node under the active license [10].
        Returns False if the device ceiling limit is exceeded.
        """
        if not self.active_license:
            logger.warning("Device activation failed: No active license registered.")
            return False

        if not self.active_license.is_active:
            logger.warning("Device activation failed: Registered license has been suspended.")
            return False

        if datetime.utcnow() >= self.active_license.expires_at:
            logger.warning("Device activation failed: Registered license expired on %s.", self.active_license.expires_at)
            return False

        # If already activated on this node, return True
        if device_id in self.active_license.activated_devices:
            logger.debug("Device %s is already registered and active.", device_id)
            return True

        # Check device ceiling limits
        if len(self.active_license.activated_devices) >= self.active_license.device_limit:
            logger.error(
                "Activation Rejected: Device limit reached (%s/%s). Deactivate an older node first.",
                len(self.active_license.activated_devices), self.active_license.device_limit
            )
            return False

        self.active_license.activated_devices.append(device_id)
        logger.info("Device %s activated successfully. Active nodes: %s/%s", device_id, len(self.active_license.activated_devices), self.active_license.device_limit)
        return True

    # =====================================================================
    # OFFLINE GRACE PERIOD CHECKPOINTS
    # =====================================================================

    def save_offline_checkpoint(self) -> bool:
        """
        Obfuscates and persists license parameters locally to enable offline grace periods [10].
        Creates an encrypted-looking base64 payload to prevent simple file edits.
        """
        if not self.active_license:
            return False

        try:
            # Map license attributes to dictionary
            checkpoint_data = {
                "key": self.active_license.license_key,
                "email": self.active_license.owner_email,
                "tier": self.active_license.tier,
                "expires_at": self.active_license.expires_at.isoformat(),
                "device_limit": self.active_license.device_limit,
                "activated_devices": self.active_license.activated_devices,
                "is_active": self.active_license.is_active,
                "last_verified_at": datetime.utcnow().isoformat()
            }

            # Serialize and apply obfuscation hashes
            json_str = json.dumps(checkpoint_data)
            payload_bytes = json_str.encode("utf-8")
            obfuscated_payload = base64.b64encode(payload_bytes).decode("utf-8")

            # Create an integrity verification block
            integrity_hash = hashlib.sha256(f"{obfuscated_payload}:{self.salt}".encode("utf-8")).hexdigest()

            file_payload = {
                "checkpoint": obfuscated_payload,
                "integrity": integrity_hash
            }

            os.makedirs(os.path.dirname(self.checkpoint_filename), exist_ok=True)
            with open(self.checkpoint_filename, "w", encoding="utf-8") as f:
                json.dump(file_payload, f, indent=4)

            logger.debug("Secure local license checkpoint saved.")
            return True
        except Exception as e:
            logger.error("Failed to save offline license checkpoint: %s", str(e))
            return False

    def load_offline_checkpoint(self, device_id: str, grace_days: int = 14) -> bool:
        """
        Loads and verifies a local license checkpoint during network disconnects [10].
        Permits offline trading up to a specified grace limit (defaults to 14 days) [10].
        """
        if not os.path.exists(self.checkpoint_filename):
            logger.warning("Offline license verification failed: No local checkpoint found.")
            return False

        try:
            with open(self.checkpoint_filename, "r", encoding="utf-8") as f:
                file_payload = json.load(f)

            obfuscated_payload = file_payload.get("checkpoint", "")
            integrity_hash = file_payload.get("integrity", "")

            # Verify file integrity against local modification
            calculated_hash = hashlib.sha256(f"{obfuscated_payload}:{self.salt}".encode("utf-8")).hexdigest()
            if calculated_hash != integrity_hash:
                logger.critical("Offline license verification rejected: Checkpoint file integrity has been compromised!")
                return False

            # Decode obfuscated payload
            payload_bytes = base64.b64decode(obfuscated_payload.encode("utf-8"))
            checkpoint_data = json.loads(payload_bytes.decode("utf-8"))

            last_check_dt = datetime.fromisoformat(checkpoint_data["last_verified_at"])
            expires_dt = datetime.fromisoformat(checkpoint_data["expires_at"])
            now = datetime.utcnow()

            # 1. Verify Offline Grace Period Lifespan
            if now - last_check_dt > timedelta(days=grace_days):
                logger.error("Offline license expired: Grace period of %s days exceeded. Connection required.", grace_days)
                return False

            # 2. Verify Absolute License Lifespan
            if now >= expires_dt:
                logger.error("Offline license expired: License validity ended on %s.", expires_dt)
                return False

            # 3. Verify Active Node Verification
            if device_id not in checkpoint_data.get("activated_devices", []):
                logger.error("Offline license verification rejected: Current device %s is not registered.", device_id)
                return False

            # Load checkpoint parameters into active memory
            self.active_license = LicenseMetadata(
                license_key=checkpoint_data["key"],
                owner_email=checkpoint_data["email"],
                tier=checkpoint_data["tier"],
                expires_at=expires_dt,
                device_limit=checkpoint_data["device_limit"],
                activated_devices=checkpoint_data["activated_devices"],
                is_active=checkpoint_data["is_active"],
                last_verified_at=last_check_dt
            )

            logger.info("Loaded secure offline license checkpoint. Grace days remaining: %s", grace_days - (now - last_check_dt).days)
            return True

        except Exception as e:
            logger.error("Failed to load offline license checkpoint: %s", str(e))
            return False

    # =====================================================================
    # PREMIUM FEATURE GATING
    # =====================================================================

    def check_feature_access(self, feature_name: str) -> bool:
        """
        Determines if the active license tier is permitted to execute a specific feature [10].
        
        Gating Rules:
            - STANDARD: Backtesting, indicators
            - PREMIUM: Optimizations, walk-forward, paper-trading, AI selector
            - ENTERPRISE: Multi-broker execution gateways, portfolio optimization
        """
        if not self.active_license or not self.active_license.is_active:
            logger.warning("Feature Access Denied: No active authorized license registered.")
            return False

        if datetime.utcnow() >= self.active_license.expires_at:
            logger.warning("Feature Access Denied: License has expired.")
            return False

        tier = self.active_license.tier
        feature_upper = feature_name.upper()

        tier_access = {
            "STANDARD": ["BACKTESTING", "INDICATORS"],
            "PREMIUM": ["BACKTESTING", "INDICATORS", "OPTIMIZATION", "WALK_FORWARD", "PAPER_TRADING", "AI_SELECTOR"],
            "ENTERPRISE": ["BACKTESTING", "INDICATORS", "OPTIMIZATION", "WALK_FORWARD", "PAPER_TRADING", "AI_SELECTOR", "BROKERS", "PORTFOLIO_OPTIMIZATION"]
        }

        allowed_features = tier_access.get(tier, [])
        access_granted = feature_upper in allowed_features

        if not access_granted:
            logger.warning("Feature Access Denied: Current license tier '%s' lacks permissions for '%s'.", tier, feature_upper)
            
        return access_granted
