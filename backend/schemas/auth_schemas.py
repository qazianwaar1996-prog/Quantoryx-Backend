# backend/schemas/auth_schemas.py
"""
Quantoryx — Authentication & User Management Schemas Module.

This module defines Pydantic validation structures for secure user registration,
login credentials, token exchange operations, profile updates, and password changes.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# =====================================================================
# REQUEST SCHEMAS
# =====================================================================

class UserRegisterRequest(BaseModel):
    """Schema for POST /auth/register payload."""
    username: str = Field(..., min_length=3, max_length=50, description="Unique login handle")
    email: EmailStr = Field(..., description="Unique user communication email address")
    password: str = Field(..., min_length=8, max_length=128, description="Secure account password")
    full_name: Optional[str] = Field(None, max_length=100, description="Display name of the user")
    role: str = Field("user", pattern="^(admin|user)$", description="Role access levels ('admin' or 'user')")


class UserLoginRequest(BaseModel):
    """Schema for POST /auth/login payload."""
    username: str = Field(..., description="Account username or email address")
    password: str = Field(..., description="Account secure password")


class RefreshTokenRequest(BaseModel):
    """Schema for POST /auth/refresh payload."""
    refresh_token: str = Field(..., description="Valid refresh token value")


class UserProfileUpdateRequest(BaseModel):
    """Schema for PUT /auth/profile payload."""
    email: Optional[EmailStr] = Field(None, description="Updated communication email address")
    full_name: Optional[str] = Field(None, max_length=100, description="Updated display name")


class PasswordChangeRequest(BaseModel):
    """Schema for POST /auth/change-password payload."""
    old_password: str = Field(..., description="Active password credential")
    new_password: str = Field(..., min_length=8, max_length=128, description="Target replacement password")


# =====================================================================
# RESPONSE SCHEMAS
# =====================================================================

class UserResponse(BaseModel):
    """Schema representing structured user records returned to clients."""
    id: str = Field(..., description="Unique database UUID index identifier")
    username: str = Field(..., description="Registered login handle")
    email: EmailStr = Field(..., description="Registered email address")
    full_name: Optional[str] = Field(None, description="Registered display name")
    role: str = Field(..., description="Assigned access level role")
    is_active: bool = Field(..., description="Flag tracking active operating statuses")
    created_at: datetime = Field(..., description="Timestamp of account creation")


class TokenResponse(BaseModel):
    """Schema returning authorization token structures on login and refresh."""
    access_token: str = Field(..., description="Signed JSON Web Token with expiration payload")
    refresh_token: str = Field(..., description="Secure signed refresh token payload")
    token_type: str = Field("bearer", description="Token transmission model (standard Bearer)")


class GenericAuthMessageResponse(BaseModel):
    """Schema indicating standardized functional feedback messages."""
    status: str = Field(..., description="Message execution status code (e.g., 'SUCCESS')")
    message: str = Field(..., description="Message feedback explanation")


# =====================================================================
# INTERNAL & SECURITY PAYLOADS
# =====================================================================

class TokenPayload(BaseModel):
    """Internal validation model mapping parsed JWT payload contents."""
    sub: str = Field(..., description="The subject token identification index")
    role: str = Field(..., description="The embedded access role level")
    exp: int = Field(..., description="UTC Timestamp expiration marker")
