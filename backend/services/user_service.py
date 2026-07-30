# backend/services/user_service.py
"""
Quantoryx — User Service & Persistence Module.

This module implements user identity management, credential hashing, profile
updates, and password changes, backed by SQLAlchemy repositories. It maintains
full backward-compatible dictionaries outputs for service consumers.
"""

import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

# Ensure root is in path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database.connection import SessionLocal
from backend.models.models import User, UserSettings, AuditLog
from backend.repositories.repositories import user_repo, settings_repo, audit_repo
from backend.schemas.auth_schemas import (
    PasswordChangeRequest,
    UserProfileUpdateRequest,
    UserRegisterRequest
)
from backend.schemas.api_schemas import UserSettingsUpdateRequest
from backend.services.security_service import SecurityService
from utils.logging_config import get_logger

# Initialize centralized logger
logger = get_logger("backend.services.user")


class UserService:
    """
    RDBMS-backed user database repository and profile manager.
    Coordinates transactional database scopes if no active session is supplied.
    """

    @staticmethod
    def _to_dict(user: User) -> Optional[Dict[str, Any]]:
        """Serializes SQLAlchemy User entity to a clean dictionary response format."""
        if not user:
            return None
        created_at_str = user.created_at.isoformat() if isinstance(user.created_at, datetime) else str(user.created_at)
        if not created_at_str.endswith("Z"):
            created_at_str += "Z"
            
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": created_at_str
        }

    @classmethod
    def register_user(cls, request: UserRegisterRequest, db: Session = None) -> Optional[Dict[str, Any]]:
        """
        Registers a new user profile with secure hashed password credentials and 
        associates default user operational settings.
        """
        # Scoped transactional block if called outside FastAPI dependency injects
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            # Enforce unique credential checks
            if user_repo.get_by_username(session, request.username):
                logger.warning("Registration rejected: username '%s' is already taken.", request.username)
                return None
            if user_repo.get_by_email(session, request.email):
                logger.warning("Registration rejected: email '%s' is already registered.", request.email)
                return None

            # Secure password hashing via SecurityService
            hashed_pw = SecurityService.hash_password(request.password)
            user_id = str(uuid.uuid4())

            # Create User profile record
            user_data = {
                "id": user_id,
                "username": request.username,
                "email": request.email,
                "hashed_password": hashed_pw,
                "full_name": request.full_name,
                "role": request.role.lower(),
                "is_active": True
            }
            user_obj = user_repo.create(session, obj_in=user_data)

            # Auto-initialize default UserSettings profile settings
            settings_data = {
                "user_id": user_id,
                "default_symbol": "EURUSD",
                "default_timeframe": "1H",
                "risk_per_trade_pct": 1.0,
                "leverage": 30.0,
                "spread": 0.0002,
                "confidence_threshold": 65.0
            }
            settings_repo.create(session, obj_in=settings_data)

            # Log registration audit event
            audit_repo.log_event(
                session, 
                user_id=user_id, 
                action="USER_REGISTRATION", 
                entity_type="users", 
                entity_id=user_id,
                details=f"User registered with email {request.email}"
            )

            if standalone:
                session.commit()

            logger.info("User registered successfully. ID: %s | Username: %s", user_id, request.username)
            return cls._to_dict(user_obj)

        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("User registration transaction aborted: %s", str(e), exc_info=True)
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def authenticate_user(cls, username_or_email: str, password: str, db: Session = None) -> Optional[Dict[str, Any]]:
        """
        Authenticates username/email credentials and verifies hashed passwords.
        """
        session = db if db is not None else SessionLocal()
        try:
            # Query User by username or email
            user_obj = user_repo.get_by_username(session, username_or_email)
            if not user_obj:
                user_obj = user_repo.get_by_email(session, username_or_email)

            if user_obj:
                # Verify password against active hash
                if SecurityService.verify_password(password, user_obj.hashed_password):
                    if not user_obj.is_active:
                        logger.warning("Authentication rejected: User profile '%s' is inactive.", user_obj.username)
                        return None
                    
                    # Log login event
                    audit_repo.log_event(
                        session, 
                        user_id=user_obj.id, 
                        action="USER_LOGIN", 
                        details="User logged in successfully"
                    )
                    if db is None:
                        session.commit()
                        
                    return cls._to_dict(user_obj)

            logger.warning("Authentication failed: invalid credentials for identifier '%s'.", username_or_email)
            return None
        except Exception as e:
            logger.error("User authentication raised exception: %s", str(e))
            return None
        finally:
            if db is None:
                session.close()

    @classmethod
    def get_user_by_id(cls, user_id: str, db: Session = None) -> Optional[Dict[str, Any]]:
        """Retrieves a single user profile matching a target ID."""
        session = db if db is not None else SessionLocal()
        try:
            user_obj = user_repo.get(session, user_id)
            return cls._to_dict(user_obj) if user_obj else None
        finally:
            if db is None:
                session.close()

    @classmethod
    def get_user_by_username(cls, username: str, db: Session = None) -> Optional[Dict[str, Any]]:
        """Retrieves a user profile matching a target username."""
        session = db if db is not None else SessionLocal()
        try:
            user_obj = user_repo.get_by_username(session, username)
            return cls._to_dict(user_obj) if user_obj else None
        finally:
            if db is None:
                session.close()

    @classmethod
    def get_user_by_email(cls, email: str, db: Session = None) -> Optional[Dict[str, Any]]:
        """Retrieves a user profile matching a target email address."""
        session = db if db is not None else SessionLocal()
        try:
            user_obj = user_repo.get_by_email(session, email)
            return cls._to_dict(user_obj) if user_obj else None
        finally:
            if db is None:
                session.close()

    @classmethod
    def update_user_profile(
        cls, 
        user_id: str, 
        update_request: UserProfileUpdateRequest, 
        db: Session = None
    ) -> Optional[Dict[str, Any]]:
        """
        Modifies target communication and metadata elements of a user profile.
        """
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            user_obj = user_repo.get(session, user_id)
            if not user_obj:
                return None

            # Check for unique email collisions if modified
            if update_request.email:
                new_email = update_request.email.lower()
                if new_email != user_obj.email.lower():
                    colliding_user = user_repo.get_by_email(session, new_email)
                    if colliding_user and colliding_user.id != user_id:
                        logger.warning("Profile update rejected: email '%s' is already taken.", update_request.email)
                        return None
                    user_obj.email = update_request.email

            if update_request.full_name is not None:
                user_obj.full_name = update_request.full_name

            # Commit update
            session.add(user_obj)
            
            # Log update audit event
            audit_repo.log_event(
                session, 
                user_id=user_id, 
                action="PROFILE_UPDATE", 
                entity_type="users", 
                entity_id=user_id,
                details="User updated profile metadata"
            )

            if standalone:
                session.commit()
                session.refresh(user_obj)

            logger.info("User profile updated successfully. ID: %s", user_id)
            return cls._to_dict(user_obj)

        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("User profile update transaction aborted: %s", str(e), exc_info=True)
            return None
        finally:
            if standalone:
                session.close()

    @classmethod
    def change_user_password(cls, user_id: str, change_request: PasswordChangeRequest, db: Session = None) -> bool:
        """
        Verifies old password credentials and commits new hashed target passwords.
        """
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            user_obj = user_repo.get(session, user_id)
            if not user_obj:
                return False

            # Verify previous active credentials
            if not SecurityService.verify_password(change_request.old_password, user_obj.hashed_password):
                logger.warning("Password update rejected: invalid old password provided.")
                return False

            # Apply and save target hashed password
            user_obj.hashed_password = SecurityService.hash_password(change_request.new_password)
            session.add(user_obj)

            # Log password modification audit event
            audit_repo.log_event(
                session, 
                user_id=user_id, 
                action="PASSWORD_CHANGE", 
                entity_type="users", 
                entity_id=user_id,
                details="User changed account security password"
            )

            if standalone:
                session.commit()
            return True

        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Password modification transactional error: %s", str(e))
            return False
        finally:
            if standalone:
                session.close()

    @classmethod
    def revoke_refresh_token(cls, user_id: str, refresh_token: str, db: Session = None) -> None:
        """Saves a refresh token to the revoked token listing using AuditLog as a blacklist ledger."""
        standalone = db is None
        session = db if db is not None else SessionLocal()
        try:
            # We log the revoked token in our audit table for relational tracking
            audit_repo.log_event(
                session,
                user_id=user_id,
                action="TOKEN_REVOKED",
                entity_type="tokens",
                details=refresh_token
            )
            if standalone:
                session.commit()
            logger.debug("Refresh token revoked successfully for user ID: %s", user_id)
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("Failed to revoke refresh token: %s", str(e))
        finally:
            if standalone:
                session.close()

    @classmethod
    def is_refresh_token_revoked(cls, user_id: str, refresh_token: str, db: Session = None) -> bool:
        """Validates if a target refresh token has been logged as revoked."""
        session = db if db is not None else SessionLocal()
        try:
            # Check if there is an audit entry with "TOKEN_REVOKED" matching details
            query = session.query(AuditLog).filter(
                AuditLog.user_id == user_id,
                AuditLog.action == "TOKEN_REVOKED",
                AuditLog.details == refresh_token
            )
            return session.query(query.exists()).scalar()
        except Exception as e:
            logger.error("Failed to check refresh token revocation status: %s", str(e))
            return True
        finally:
            if db is None:
                session.close()

    # =====================================================================
    # v4.5 USER SETTINGS MANAGEMENT WORKFLOWS
    # =====================================================================

    @classmethod
    def get_user_settings(cls, user_id: str, db: Session = None) -> Optional[UserSettings]:
        """Retrieves operational configurations matching a target user ID."""
        session = db if db is not None else SessionLocal()
        try:
            return settings_repo.get_by_user_id(session, user_id)
        finally:
            if db is None:
                session.close()

    @classmethod
    def update_user_settings(
        cls, 
        user_id: str, 
        update_request: UserSettingsUpdateRequest, 
        db: Session = None
    ) -> Optional[UserSettings]:
        """Modifies customizable operational configurations per user profile."""
        standalone = db is None
        session = db if db is not None else SessionLocal()

        try:
            settings_obj = settings_repo.get_by_user_id(session, user_id)
            if not settings_obj:
                return None

            # Map inputs to database columns
            update_data = update_request.model_dump(exclude_unset=True)
            updated_settings = settings_repo.update(session, db_obj=settings_obj, obj_in=update_data)

            # Log settings modification audit event
            audit_repo.log_event(
                session, 
                user_id=user_id, 
                action="SETTINGS_UPDATE", 
                entity_type="user_settings", 
                entity_id=str(updated_settings.id),
                details="User updated system default preference parameters"
            )

            if standalone:
                session.commit()
                session.refresh(updated_settings)

            return updated_settings
        except Exception as e:
            if standalone:
                session.rollback()
            logger.error("User settings update transactional error: %s", str(e))
            return None
        finally:
            if standalone:
                session.close()
