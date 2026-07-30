# backend/api/deps.py
"""
Quantoryx — Security Dependency Injection Module.

This module implements FastAPI dependencies for extracting bearer tokens from HTTP headers,
verifying JWT payloads, enforcing RBAC access levels, and providing transactional
SQLAlchemy database sessions across endpoints.
"""

import os
import sys
import time
from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

# Ensure root is in path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database.connection import get_db
from backend.services.security_service import SecurityService
from backend.services.user_service import UserService
from utils.logging_config import get_logger

# Initialize centralized logger
logger = get_logger("backend.api.deps")

# Security schema initialization
security_scheme = HTTPBearer(auto_error=False)

# =====================================================================
# IN-MEMORY RATE LIMITER CONFIGURATION
# =====================================================================
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 100
_IP_RATE_TRACKER: Dict[str, list] = {}


def check_rate_limit(request: Request) -> None:
    """
    Dependency checking the request rate limit of the calling client IP address.
    """
    client_ip = request.client.host if request.client else "unknown_ip"
    now = time.time()

    # Retrieve sliding window history for this client IP
    history = _IP_RATE_TRACKER.get(client_ip, [])
    
    # Filter out entries older than active sliding window size
    history = [t for t in history if now - t < RATE_LIMIT_WINDOW_SECONDS]
    
    if len(history) >= RATE_LIMIT_MAX_REQUESTS:
        logger.warning("Rate limit exceeded for client IP: %s (Requests: %s/%s s)", client_ip, len(history), RATE_LIMIT_WINDOW_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before executing further requests."
        )

    # Append current timestamp to list and update tracker
    history.append(now)
    _IP_RATE_TRACKER[client_ip] = history


# =====================================================================
# CORE USER AUTHORIZATION DEPENDENCIES
# =====================================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Dependency that extracts, verifies, and resolves the currently active user profile.
    Raises 401 UNAUTHORIZED if the token is missing, expired, or invalid.
    """
    if not credentials:
        logger.warning("Authentication failed: Authorization header token missing.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization credentials are missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    claims = SecurityService.verify_token(token, expected_type="access")
    
    if not claims:
        logger.warning("Authentication failed: Invalid or expired access token signatures.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = claims.get("sub")
    if not user_id:
        logger.warning("Authentication failed: Subject claims missing in token payload.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check database persistence layers passing current active database session
    user = UserService.get_user_by_id(user_id, db=db)
    if not user:
        logger.warning("Authentication failed: Registered user matching ID %s was not resolved.", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User matching these credentials was not resolved.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        logger.warning("Authentication failed: User account '%s' is inactive.", user["username"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account has been disabled."
        )

    return user


async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    RBAC dependency enforcing admin role permissions on target endpoints.
    Raises 403 FORBIDDEN if the resolved user role is not 'admin'.
    """
    role = current_user.get("role", "user").lower()
    if role != "admin":
        logger.warning("Access forbidden: User '%s' lacks the required 'admin' permissions.", current_user["username"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin clearance is required."
        )
    return current_user
