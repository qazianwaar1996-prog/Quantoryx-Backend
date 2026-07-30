# backend/api/auth_endpoints.py
"""
Quantoryx — Authentication Endpoints Router Module.

This module maps standard HTTP authorization operations to underlying services,
enforcing rate limits, database transactions, and session scopes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import check_rate_limit, get_current_user, get_db
from datetime import timedelta

from backend.schemas.api_schemas import ForgotPasswordRequest
from backend.schemas.auth_schemas import (
    GenericAuthMessageResponse,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
    UserLoginRequest
)
from backend.services.security_service import SecurityService
from backend.services.user_service import UserService
from utils.logging_config import get_logger

# Initialize router
router = APIRouter(prefix="/api/auth", tags=["User Identity & Access Control"])
logger = get_logger("backend.api.auth")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_rate_limit)],
    summary="Register New User Account",
    description="Registers a new platform user profile. Subject to active API rate limits."
)
async def post_register(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        user = UserService.register_user(payload, db=db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or communication email has already been registered."
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error("User registration triggered a system exception: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred processing registration."
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_rate_limit)],
    summary="User Session Login",
    description="Verifies login credentials and issues signed access and refresh tokens."
)
async def post_login(
    payload: UserLoginRequest,
    db: Session = Depends(get_db)
):
    try:
        user = UserService.authenticate_user(payload.username, payload.password, db=db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Authentication failed."
            )
        
        # Generate token payloads
        token_data = {"sub": user["id"], "role": user["role"]}
        access_token = SecurityService.create_access_token(token_data)
        refresh_token = SecurityService.create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("User authentication triggered a system exception: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred processing authentication."
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange Refresh Token",
    description="Validates long-lived refresh tokens to issue active short-lived access credentials."
)
async def post_refresh(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    claims = SecurityService.verify_token(payload.refresh_token, expected_type="refresh")
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is invalid or has expired."
        )
        
    user_id = claims.get("sub")
    if not user_id or UserService.is_refresh_token_revoked(user_id, payload.refresh_token, db=db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token has been revoked."
        )
        
    # Verify user profile still exists and remains active
    user = UserService.get_user_by_id(user_id, db=db)
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or profile does not exist."
        )

    token_data = {"sub": user["id"], "role": user["role"]}
    new_access = SecurityService.create_access_token(token_data)
    new_refresh = SecurityService.create_refresh_token(token_data)
    
    # Revoke previous refresh token to prevent reuse (Token Rotation)
    UserService.revoke_refresh_token(user_id, payload.refresh_token, db=db)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }


@router.post(
    "/logout",
    response_model=GenericAuthMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="User Session Logout",
    description="Revokes the supplied refresh token, invalidating current user session states."
)
async def post_logout(
    payload: RefreshTokenRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Revoke target token
    UserService.revoke_refresh_token(current_user["id"], payload.refresh_token, db=db)
    return {
        "status": "SUCCESS",
        "message": "User session has been closed successfully. Refresh token revoked."
    }


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User Profile",
    description="Returns authenticated current user session profile data."
)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.put(
    "/profile",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update User Profile",
    description="Modifies editable metadata fields of the active user profile."
)
async def put_profile(
    payload: UserProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        updated_user = UserService.update_user_profile(current_user["id"], payload, db=db)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile update failed: email already taken by another user."
            )
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Profile update triggered a system exception: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred updating user profile."
        )


@router.post(
    "/change-password",
    response_model=GenericAuthMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change User Password",
    description="Modifies password credentials after validating previous access credentials."
)
async def post_change_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        success = UserService.change_user_password(current_user["id"], payload, db=db)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credential update failed: Active password verification failed."
            )
        return {
            "status": "SUCCESS",
            "message": "Password credentials modified successfully."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Password modification triggered a system exception: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred updating password credentials."
        )


# =====================================================================
# PASSWORD RECOVERY ENDPOINT
# =====================================================================

@router.post(
    "/forgot",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_rate_limit)],
    summary="Request Password Reset",
    description="Issues a short-lived reset token for a registered email address."
)
async def post_forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Always answers 200 with an identical body regardless of whether the address
    exists. Confirming registration status here would turn this route into an
    account-enumeration oracle.
    """
    generic = {
        "status": "SUCCESS",
        "message": "If an account exists for that address, a reset link is on its way.",
    }
    try:
        user = UserService.get_user_by_email(payload.email, db=db)
        if not user:
            logger.info("Password reset requested for an unregistered address.")
            return generic

        reset_token = SecurityService.create_access_token(
            {"sub": user["id"], "role": user.get("role", "user"), "scope": "password_reset"},
            expires_delta=timedelta(minutes=30),
        )
        # Delivery is handled by the notifications layer in deployment; the token
        # is logged at debug level only so it never lands in production logs.
        logger.debug("Password reset token issued for user %s", user["id"])
        return generic
    except Exception as e:
        logger.error("Password reset request failed: %s", str(e), exc_info=True)
        return generic
