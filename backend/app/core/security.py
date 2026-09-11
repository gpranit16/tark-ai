import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def generate_auth_token(nbytes: int = 32) -> str:
    """Generate a high-entropy URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a token for secure database storage and fast lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with automatic salt generation."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not hashed_password or not plain_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str | UUID, extra_claims: dict | None = None, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str | UUID, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT refresh token with longer expiration."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a signed JWT token, raising exceptions on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def _get_fernet():
    import base64
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt sensitive OAuth tokens/secrets at rest using AES-128/Fernet."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt sensitive OAuth tokens/secrets from database storage."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def create_oauth_state(user_id: str | UUID, provider: str = "google", service: str = "calendar") -> str:
    """Create a signed, time-limited state string for OAuth 2.0 CSRF protection."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "provider": provider,
        "service": service,
        "type": "oauth_state",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_oauth_state(state: str, expected_provider: str = "google", expected_service: str = "calendar") -> UUID:
    """Verify state token and extract user_id, raising ValueError on failure."""
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "oauth_state":
            raise ValueError("Invalid state token type")
        if payload.get("provider") != expected_provider or payload.get("service") != expected_service:
            raise ValueError("State provider or service mismatch")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("State missing user_id")
        return UUID(user_id_str)
    except Exception as e:
        raise ValueError(f"Invalid or expired OAuth state: {e}")

