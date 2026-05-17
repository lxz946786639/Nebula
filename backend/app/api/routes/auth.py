from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import CurrentUser, SessionDep, bearer_scheme
from app.core.security import TokenExpiredError, decode_token
from app.models.user import User
from app.schemas.common import Message
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserRead
from app.services.audit import write_audit
from app.services.auth import authenticate_user, get_user_from_refresh, issue_token_pair


router = APIRouter()


async def _logout_actor(session: SessionDep, token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = decode_token(token, "access", verify_exp=False)
    except ValueError:
        return None
    user_id = payload.get("sub")
    if user_id is not None:
        try:
            user = await session.get(User, int(user_id))
        except (TypeError, ValueError):
            user = None
        if user is not None:
            return user.username
    username = payload.get("username")
    return str(username).strip() if username else None


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    user = await authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    access, refresh = issue_token_pair(user)
    await write_audit(session, actor=user.username, action="login", resource="auth", detail=f"用户「{user.username}」登录系统。")
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        user = await get_user_from_refresh(session, payload.refresh_token)
    except TokenExpiredError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired") from None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None
    access, refresh = issue_token_pair(user)
    await write_audit(
        session,
        actor=user.username,
        action="token_refresh",
        resource="auth",
        detail=f"用户「{user.username}」刷新登录状态。",
    )
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/logout", response_model=Message)
async def logout(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Message:
    actor = await _logout_actor(session, credentials.credentials if credentials else None)
    if actor:
        await write_audit(
            session,
            actor=actor,
            action="logout",
            resource="auth",
            detail=f"用户「{actor}」退出登录。",
        )
        await session.commit()
    return Message(message="Logged out")


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
