# compliance/audit_logger.py
"""
Quantoryx — Immutable Audit and Compliance Logger.

Implements a tamper-evident SHA-256 hash-chained compliance logger.
Guarantees tracking integrity for logins, trades, and system alterations [12].
"""

import os
import sys
import json
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is mapped
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.path_manager import PathManager
from utils.logging_config import get_logger

logger = get_logger("compliance.audit")


class AuditLogger:
    """
    Tamper-evident system audit and compliance logger [12].
    """

    def __init__(self, log_filename: str = "compliance_audit.jsonl"):
        # Resolve target log path via PathManager
        self.log_filepath = PathManager.resolve_path("logs", log_filename)
        self.genesis_hash = "QuantoryxGenesisComplianceHash2026"

    def log_compliance_event(
        self,
        user_id: str,
        action: str,                # e.g., "USER_LOGIN", "TRADE_OPENED", "STRATEGY_SWITCH", "ERROR"
        entity_type: str,           # e.g., "user", "order", "ai_decision", "strategy"
        entity_id: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Appends an immutable, hash-chained compliance record to the log file [12].
        
        Returns:
            str: The unique, generated Event UUID.
        """
        event_id = str(uuid.uuid4())
        timestamp_str = datetime.utcnow().isoformat()

        # 1. Resolve the hash of the previous log entry to maintain the integrity chain
        prev_hash = self._get_last_entry_hash()

        # 2. Construct the core payload
        record = {
            "event_id": event_id,
            "timestamp": timestamp_str,
            "user_id": user_id,
            "action": action.upper(),
            "entity_type": entity_type.lower(),
            "entity_id": str(entity_id),
            "details": details,
            "prev_hash": prev_hash
        }

        # 3. Calculate the cryptographic hash of the current record
        record_json_str = json.dumps(record, sort_keys=True)
        record["hash"] = hashlib.sha256(record_json_str.encode("utf-8")).hexdigest()

        # 4. Append the record to the JSONL log file (Atomic append operation)
        try:
            with open(self.log_filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            logger.debug("Compliance event %s logged. Action: %s | Entity: %s", event_id, action, entity_type)
            return event_id
        except Exception as e:
            logger.critical("Failed to write immutable audit log! Critical compliance failure: %s", str(e))
            raise e

    # =====================================================================
    # CRYPTOGRAPHIC INTEGRITY VERIFICATION
    # =====================================================================

    def verify_audit_trail_integrity(self) -> Tuple[bool, int, List[str]]:
        """
        Scans the compliance logs chronologically and verifies the cryptographic hash chain.
        Returns a tuple of (is_valid, records_verified, list_of_violations) [12].
        """
        if not os.path.exists(self.log_filepath):
            return True, 0, []

        is_valid = True
        violations = []
        records_verified = 0
        expected_prev_hash = self.genesis_hash

        try:
            with open(self.log_filepath, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    
                    record = json.loads(line)
                    event_id = record.get("event_id", "Unknown")
                    records_verified += 1

                    # 1. Verify previous hash link consistency
                    if record.get("prev_hash") != expected_prev_hash:
                        is_valid = False
                        msg = f"Violation on Line {line_no} (Event {event_id}): Previous hash mismatch. Expected {expected_prev_hash[:10]}..., got {record.get('prev_hash', '')[:10]}..."
                        violations.append(msg)
                        logger.critical(msg)

                    # 2. Extract and verify the current record hash
                    actual_hash = record.get("hash", "")
                    
                    # Temporarily strip current hash to recalculate the original payload signature
                    record_copy = record.copy()
                    record_copy.pop("hash", None)
                    
                    recalculated_json_str = json.dumps(record_copy, sort_keys=True)
                    recalculated_hash = hashlib.sha256(recalculated_json_str.encode("utf-8")).hexdigest()

                    if actual_hash != recalculated_hash:
                        is_valid = False
                        msg = f"Violation on Line {line_no} (Event {event_id}): Cryptographic signature mismatch. Record has been altered!"
                        violations.append(msg)
                        logger.critical(msg)

                    # Update expected hash for the next step of the chain
                    expected_prev_hash = actual_hash

            if is_valid:
                logger.info("Compliance Audit Check passed. Successfully verified %s chronological log records.", records_verified)
            else:
                logger.critical("Compliance Audit Check failed! %s security violations identified in the audit trail.", len(violations))

            return is_valid, records_verified, violations

        except Exception as e:
            logger.error("Exception triggered during compliance audit sweep: %s", str(e))
            return False, records_verified, [f"Audit aborted due to exception: {str(e)}"]

    # =====================================================================
    # INNER UTILITIES
    # =====================================================================

    def _get_last_entry_hash(self) -> str:
        """Retrieves the hash of the last successfully written log record."""
        if not os.path.exists(self.log_filepath) or os.path.getsize(self.log_filepath) == 0:
            return self.genesis_hash

        try:
            with open(self.log_filepath, "rb") as f:
                # Seek to the end of the file and read the last line
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b"\n":
                    f.seek(-2, os.SEEK_CUR)
                last_line = f.readline().decode("utf-8")
                
                if last_line.strip():
                    last_record = json.loads(last_line)
                    return last_record.get("hash", self.genesis_hash)
        except Exception:
            # Safe default fallback if file contains formatting glitches
            pass
            
        return self.genesis_hash
