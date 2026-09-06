import base64
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth_deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_auth_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db_session
from app.models.conversation import AuthToken, User
from app.models.settings import UserSettings
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GenericMessageResponse,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    VerifyEmailRequest,
)
from app.services.email import EmailConfigurationError, EmailDeliveryError, email_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _build_user_response(user: User) -> UserResponse:
    display_name = user.name or (user.settings.display_name if user.settings else "Developer")
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        display_name=display_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: UserSignupRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    normalized_email = payload.email.strip().lower()

    try:
        # Check for existing account with same email
        stmt = select(User).where(User.email == normalized_email)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # Create user with bcrypt password hash
        hashed = hash_password(payload.password)
        user = User(
            email=normalized_email,
            password_hash=hashed,
            name=payload.name.strip(),
            is_active=True,
            is_verified=False,
        )
        session.add(user)
        await session.flush()

        # Create default user settings with user display_name
        settings_obj = UserSettings(
            user_id=user.id,
            display_name=payload.name.strip() or "Developer",
        )
        session.add(settings_obj)

        # Generate and store email verification token
        raw_token = generate_auth_token(32)
        token_hash_str = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_token_expire_hours)
        
        token_record = AuthToken(
            user_id=user.id,
            token_hash=token_hash_str,
            token_type="email_verification",
            expires_at=expires_at,
            is_used=False,
        )
        session.add(token_record)
        await session.commit()
        await session.refresh(user, attribute_names=["settings"])
    except HTTPException:
        await session.rollback()
        raise
    except Exception as db_err:
        await session.rollback()
        logger.error("[AUTH] signup_db_error error=%s", type(db_err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please try again.",
        ) from db_err

    # Dispatch verification email via Resend in background (non-blocking)
    verification_url = f"{settings.frontend_url}/verify-email?token={raw_token}"
    if email_service.is_configured():
        import asyncio
        asyncio.create_task(
            email_service.send_verification_email(
                to_email=user.email,
                verification_url=verification_url,
                user_name=user.name,
            )
        )

    # Generate JWT tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        user=_build_user_response(user),
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    normalized_email = payload.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email).options(selectinload(User.settings))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        user=_build_user_response(user),
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _build_user_response(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected refresh token.",
            )
        user_id_str = data.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token subject missing.",
            )
        user_id = UUID(user_id_str)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    stmt = select(User).where(User.id == user_id).options(selectinload(User.settings))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive.",
        )

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        user=_build_user_response(user),
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"status": "ok", "message": "Successfully logged out."}


@router.post("/forgot-password", response_model=GenericMessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    """Generate a secure password reset token and dispatch via Resend."""
    normalized_email = payload.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None and user.is_active:
        # Invalidate any prior unused password reset tokens
        await session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user.id,
                AuthToken.token_type == "password_reset",
                AuthToken.is_used == False,
            )
            .values(is_used=True)
        )

        # Generate new one-time token
        raw_token = generate_auth_token(32)
        token_hash_str = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)

        token_record = AuthToken(
            user_id=user.id,
            token_hash=token_hash_str,
            token_type="password_reset",
            expires_at=expires_at,
            is_used=False,
        )
        session.add(token_record)
        await session.commit()

        # Send email via Resend
        reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
        try:
            await email_service.send_password_reset_email(
                to_email=user.email,
                reset_url=reset_url,
                user_name=user.name,
            )
        except EmailConfigurationError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e) or "Email delivery service is currently not configured.",
            )
        except EmailDeliveryError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e) or "Failed to send password reset email. Please try again later.",
            )

    # Safe generic message to prevent email enumeration
    return GenericMessageResponse(
        message="If an account exists for this email, recovery instructions have been sent."
    )


@router.post("/reset-password", response_model=GenericMessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    """Validate one-time reset token and update user password."""
    token_hash_str = hash_token(payload.token.strip())
    now = datetime.now(timezone.utc)

    stmt = select(AuthToken).where(
        AuthToken.token_hash == token_hash_str,
        AuthToken.token_type == "password_reset",
        AuthToken.is_used == False,
        AuthToken.expires_at > now,
    )
    result = await session.execute(stmt)
    token_record = result.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link.",
        )

    # Fetch user and update password
    user = await session.get(User, token_record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account associated with this token was not found or is inactive.",
        )

    user.password_hash = hash_password(payload.new_password)
    token_record.is_used = True

    # Invalidate all other reset tokens for this user
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.token_type == "password_reset",
        )
        .values(is_used=True)
    )

    await session.commit()
    return GenericMessageResponse(message="Your password has been successfully reset. You may now sign in.")


@router.post("/verify-email", response_model=GenericMessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    """Verify an account using a secure one-time verification token."""
    token_hash_str = hash_token(payload.token.strip())
    now = datetime.now(timezone.utc)

    stmt = select(AuthToken).where(
        AuthToken.token_hash == token_hash_str,
        AuthToken.token_type == "email_verification",
        AuthToken.is_used == False,
        AuthToken.expires_at > now,
    )
    result = await session.execute(stmt)
    token_record = result.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification link.",
        )

    user = await session.get(User, token_record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account associated with this token was not found.",
        )

    user.is_verified = True
    token_record.is_used = True
    await session.commit()

    return GenericMessageResponse(message="Your email address has been successfully verified.")


@router.post("/resend-verification", response_model=GenericMessageResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    """Resend email verification link to user."""
    normalized_email = payload.email.strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None and user.is_active and not user.is_verified:
        # Invalidate previous verification tokens
        await session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user.id,
                AuthToken.token_type == "email_verification",
                AuthToken.is_used == False,
            )
            .values(is_used=True)
        )

        raw_token = generate_auth_token(32)
        token_hash_str = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_token_expire_hours)

        token_record = AuthToken(
            user_id=user.id,
            token_hash=token_hash_str,
            token_type="email_verification",
            expires_at=expires_at,
            is_used=False,
        )
        session.add(token_record)
        await session.commit()

        verification_url = f"{settings.frontend_url}/verify-email?token={raw_token}"
        if email_service.is_configured():
            try:
                await email_service.send_verification_email(
                    to_email=user.email,
                    verification_url=verification_url,
                    user_name=user.name,
                )
            except Exception:
                pass

    return GenericMessageResponse(
        message="If an account exists with this email address, a verification link has been sent."
    )


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update current user's profile information (display name and/or avatar URL)."""
    stmt = select(User).where(User.id == current_user.id).options(selectinload(User.settings))
    result = await session.execute(stmt)
    user = result.scalar_one()

    if payload.name is not None:
        user.name = payload.name.strip()
        if user.settings:
            user.settings.display_name = payload.name.strip()

    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip() if payload.avatar_url else None

    await session.commit()
    await session.refresh(user, attribute_names=["settings"])
    return _build_user_response(user)


@router.post("/change-password", response_model=GenericMessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    """Update current user's password after validating their existing password."""
    stmt = select(User).where(User.id == current_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one()

    if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return GenericMessageResponse(message="Password successfully changed.")


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Upload custom avatar image file for the current user."""
    allowed_content_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
        "image/svg+xml",
    }
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image format '{file.content_type}'. Allowed types: PNG, JPEG, WebP, GIF, SVG.",
        )

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar image file must be smaller than 5 MB.",
        )

    encoded = base64.b64encode(content).decode("utf-8")
    data_uri = f"data:{content_type};base64,{encoded}"

    stmt = select(User).where(User.id == current_user.id).options(selectinload(User.settings))
    result = await session.execute(stmt)
    user = result.scalar_one()

    user.avatar_url = data_uri
    await session.commit()
    await session.refresh(user, attribute_names=["settings"])
    return _build_user_response(user)
