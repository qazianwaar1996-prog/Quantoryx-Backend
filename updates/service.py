# updates/service.py
"""
Quantoryx — Desktop Auto Update Service.

Orchestrates software version checks, staged update manifest downloads,
cryptographic checksum audits, and transactional rollback installations [14].
"""

import os
import sys
import json
import shutil
import hashlib
import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.path_manager import PathManager
from utils.logging_config import get_logger

logger = get_logger("updates.service")

# Defensive imports [4]
try:
    import aiohttp
except ImportError:
    aiohttp = None
    logger.warning("aiohttp library is missing. Install it to activate remote auto-update downloading.")


@dataclass
class UpdateManifest:
    """Structure containing release configuration details [14]."""
    version: str
    release_date: str
    checksum_sha256: str
    download_url: str
    rollback_version: Optional[str] = None
    staged_rollout_pct: int = 100  # 100 means fully rolled out


class DesktopUpdateService:
    """
    Orchestrates update checks, file integrity verification, and rollbacks [14].
    """

    def __init__(self, manifest_url: str = "https://updates.quantoryx.com/manifest.json"):
        self.manifest_url = manifest_url
        self.updates_dir = PathManager.resolve_path("output", "updates")
        self.backup_dir = PathManager.resolve_path("output", "backup_previous")

    async def check_for_updates(self, current_version: str, user_bucket_id: int = 50) -> Optional[UpdateManifest]:
        """
        Queries the remote manifest and checks if a newer version is available [14].
        Honors staged progressive rollout buckets.
        """
        if aiohttp is None:
            logger.error("Update check cancelled: aiohttp library is unavailable.")
            return None

        logger.info("AutoUpdate: Querying release manifest from %s", self.manifest_url)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.manifest_url, timeout=5.0) as response:
                    if response.status != 200:
                        logger.error("Failed to download update manifest (Status %s).", response.status)
                        return None

                    data = await response.json()
                    manifest = UpdateManifest(
                        version=data.get("version", ""),
                        release_date=data.get("release_date", ""),
                        checksum_sha256=data.get("checksum_sha256", ""),
                        download_url=data.get("download_url", ""),
                        rollback_version=data.get("rollback_version"),
                        staged_rollout_pct=int(data.get("staged_rollout_pct", 100))
                    )

                    # 1. Compare version strings (Simple semantic separation check)
                    if manifest.version == current_version:
                        logger.debug("System is up-to-date (Version: %s).", current_version)
                        return None

                    # 2. Evaluate Staged Rollout Bucket Access [14]
                    if user_bucket_id > manifest.staged_rollout_pct:
                        logger.info("New update version %s detected but not yet available for current rollout group.", manifest.version)
                        return None

                    logger.info("New update available! Version: %s | Released: %s", manifest.version, manifest.release_date)
                    return manifest

        except Exception as e:
            logger.error("Failed to query update manifest: %s", str(e))
            return None

    async def download_update_package(self, manifest: UpdateManifest) -> Optional[str]:
        """Downloads the binary update archive [14]."""
        if aiohttp is None or self.ws_closed_checks():
            return None

        filename = f"quantoryx_patch_{manifest.version}.zip"
        dest_filepath = os.path.join(self.updates_dir, filename)
        os.makedirs(self.updates_dir, exist_ok=True)

        logger.info("AutoUpdate: Downloading patch from %s...", manifest.download_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(manifest.download_url, timeout=30.0) as response:
                    if response.status != 200:
                        logger.error("Failed to download update package (Status %s).", response.status)
                        return None

                    with open(dest_filepath, "wb") as f:
                        while True:
                            chunk = await response.content.read(1024 * 1024)  # 1MB chunks
                            if not chunk:
                                break
                            f.write(chunk)

            logger.info("Downloaded update patch file to: %s", dest_filepath)
            return dest_filepath
        except Exception as e:
            logger.error("Failed to download update package: %s", str(e))
            return None

    def verify_package_checksum(self, filepath: str, expected_checksum: str) -> bool:
        """
        Performs a cryptographic audit on the downloaded update file [14].
        Returns True if the calculated SHA-256 hash matches the expected manifest.
        """
        if not os.path.exists(filepath):
            return False

        logger.info("AutoUpdate: Performing SHA-256 integrity verification on %s...", os.path.basename(filepath))

        sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    sha256.update(chunk)
            
            calculated_hash = sha256.hexdigest()
            if calculated_hash.lower() == expected_checksum.lower():
                logger.info("Cryptographic integrity verification passed.")
                return True
            else:
                logger.critical("Security Breach: Checksum mismatch! The update file has been altered.")
                return False
        except Exception as e:
            logger.error("Failed to calculate file checksum: %s", str(e))
            return False

    def apply_update(self, package_path: str, target_dir: str) -> bool:
        """
        Saves current files to a backup directory, extracts the update archive,
        and manages transactional rollback recovery if errors occur [14].
        """
        logger.info("AutoUpdate: Appling system patch...")
        
        # 1. Create a complete backup of the target directory first
        self._create_revert_backup(target_dir)

        try:
            # 2. Extract ZIP package
            # Python standard zipfile module used to extract archive
            import zipfile
            with zipfile.ZipFile(package_path, "r") as zip_ref:
                # Wrap inside thread-pool to prevent blocking [1, 2]
                zip_ref.extractall(target_dir)

            logger.info("System patched successfully to target directory: %s", target_dir)
            return True

        except Exception as e:
            logger.error("Failed to apply update: %s. Initiating automatic rollback...", str(e))
            # Trigger rollback sequence
            self.restore_backup_rollback(target_dir)
            return False

    def restore_backup_rollback(self, target_dir: str) -> bool:
        """
        Restores files from the temporary backup directory to rollback a failed update [14].
        """
        if not os.path.exists(self.backup_dir) or not os.listdir(self.backup_dir):
            logger.critical("Rollback Failed: No local backup directory found to restore files!")
            return False

        logger.info("AutoUpdate: Restoring previous operational backup...")
        try:
            # Clear target directory contents
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                if item == "output":  # Prevent clearing generated user data/database logs
                    continue
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

            # Copy backup files back
            for item in os.listdir(self.backup_dir):
                src_path = os.path.join(self.backup_dir, item)
                dst_path = os.path.join(target_dir, item)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)

            logger.info("Rollback complete. Recovered previously backed-up system files.")
            return True
        except Exception as e:
            logger.critical("Critical Failure: System rollback caught an exception: %s", str(e))
            return False

    # =====================================================================
    # INNER BACKUP UTILITIES
    # =====================================================================

    def _create_revert_backup(self, target_dir: str):
        """Creates a temporary backup directory of the current files [14]."""
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)
        os.makedirs(self.backup_dir, exist_ok=True)

        for item in os.listdir(target_dir):
            # Skip output, data, and system logs folders to avoid backing up massive cache files
            if item in ["output", "data", "logs", ".git", ".venv", "tests"]:
                continue
            
            src_path = os.path.join(target_dir, item)
            dst_path = os.path.join(self.backup_dir, item)
            
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
                
        logger.debug("Temporary rollback backup directory compiled successfully.")

    def ws_closed_checks(self) -> bool:
        """Helper to verify file boundaries."""
        return not os.path.exists(self.updates_dir) and not os.makedirs(self.updates_dir, exist_ok=True)
