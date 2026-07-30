# backend/services/security_service.py
"""
Quantoryx — Security & Token Operations Service.

This module handles secure password hashing, verification, JSON Web Token (JWT)
signatures, and verification. It establishes a secure, robust, and deprecation-free
cryptographic baseline for the user authentication system.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
import jwt

from utils.logging_config import get_logger

# Initialize centralized logger
logger = get_logger("backend.services.security")

# =====================================================================
# SECURITY SYSTEM CONSTANTS
# =====================================================================
# Read secret keys from environment variables with safe fallback generation
JWT_SECRET_KEY = os.environ.get("QUANTORYX_SECRET_KEY")
if not JWT_SECRET_KEY:
    logger.warning(
        "QUANTORYX_SECRET_KEY environment variable not set. "
        "Generating an ephemeral key — all active JWT sessions will be invalidated on every restart. "
        "Set QUANTORYX_SECRET_KEY in Railway environment variables for persistent sessions."
    )
    JWT_SECRET_KEY = secrets.token_hex(32)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class SecurityService:
    """
    Cryptographic orchestrator providing secure credential hashing and
    JSON Web Token creation, parsing, and verification services.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hashes a plain-text password securely using blowfish-based salt derivation (bcrypt).
        """
        # Bcrypt requires byte sequences for calculation
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt(rounds=12)
        hashed_bytes = bcrypt.hashpw(password_bytes, salt)
        return hashed_bytes.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Validates a plain-text password against a secure hashed credential.
        """
        try:
            plain_bytes = plain_password.encode("utf-8")
            hashed_bytes = hashed_password.encode("utf-8")
            return bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception as e:
            logger.error("Verification error occurred during password check: %s", str(e))
            return False

    @classmethod
    def create_access_token(cls, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Generates a signed JSON Web Access Token for user authorization.
        """
        payload = data.copy()
        
        # Calculate expiration boundary
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            
        payload.update({
            "exp": int(expire.timestamp()),
            "type": "access"
        })
        
        # Sign token
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @classmethod
    def create_refresh_token(cls, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Generates a long-lived, signed JSON Web Refresh Token.
        """
        payload = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
            
        payload.update({
            "exp": int(expire.timestamp()),
            "type": "refresh"
        })
        
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @classmethod
    def verify_token(cls, token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Parses and validates a signed JSON Web Token signature and payload claims.
        Returns the parsed token claims dict if valid, or None if invalid or expired.
        """
        try:
            claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            
            # Enforce token type matching (access vs refresh)
            if claims.get("type") != expected_type:
                logger.warning("Token verification type mismatch. Expected '%s', got '%s'", expected_type, claims.get("type"))
                return None
                
            return claims
            
        except jwt.ExpiredSignatureError:
            logger.debug("Token verification rejected: token has expired.")
            return None
        except jwt.InvalidTokenError as ite:
            logger.debug("Token verification rejected: token is invalid. Detail: %s", str(ite))
            return None
        except Exception as e:
            logger.error("Token verification exception triggered: %s", str(e))
            return None
