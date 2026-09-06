from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserSignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="User full name or display name")
    email: EmailStr = Field(description="Valid email address")
    password: str = Field(min_length=6, max_length=128, description="Password with minimum 6 characters")


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(description="Account email address")
    password: str = Field(min_length=1, description="Account password")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, description="Valid JWT refresh token")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(description="Email address to receive password reset link")


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, description="One-time password reset token")
    new_password: str = Field(min_length=6, max_length=128, description="New password with minimum 6 characters")


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, description="One-time email verification token")


class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(description="Email address to receive a new verification link")


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, description="Updated display name")
    avatar_url: str | None = Field(default=None, max_length=500000, description="Updated avatar URL or base64 SVG/data URI")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, description="Current password")
    new_password: str = Field(min_length=6, max_length=128, description="New password with minimum 6 characters")


class GenericMessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: UUID
    email: str | None = None
    name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
