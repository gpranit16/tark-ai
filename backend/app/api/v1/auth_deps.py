from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db.session import get_db_session
from app.models.conversation import User

DEV_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolve the currently authenticated user from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected access token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token subject missing.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = UUID(user_id_str)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id).options(selectinload(User.settings))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Optionally resolve authenticated user if Bearer token present, else None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, session=session)
    except HTTPException:
        return None
