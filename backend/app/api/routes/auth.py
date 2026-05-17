from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserRead
from app.services.audit import write_audit
from app.services.auth import authenticate_user, get_user_from_refresh, issue_token_pair


router = APIRouter()


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
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None
    access, refresh = issue_token_pair(user)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
