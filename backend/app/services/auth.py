from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_token, decode_token, verify_password
from app.models.user import User


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def issue_token_pair(user: User) -> tuple[str, str]:
    settings = get_settings()
    access = create_token(
        str(user.id),
        settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "access",
        {"username": user.username, "is_admin": user.is_admin},
    )
    refresh = create_token(str(user.id), settings.REFRESH_TOKEN_EXPIRE_MINUTES, "refresh")
    return access, refresh


async def get_user_from_refresh(session: AsyncSession, refresh_token: str) -> User:
    payload = decode_token(refresh_token, "refresh")
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise ValueError("Inactive user")
    return user
