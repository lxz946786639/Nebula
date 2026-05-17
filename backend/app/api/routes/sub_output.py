from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import SessionDep
from app.services.aggregator import convert_subscription
from app.services.config_generator import build_clash_subscription_from_pool, build_v2ray_subscription_from_pool
from app.services.settings import get_subscription_token
from app.services.subconverter import SubconverterError


router = APIRouter()


async def _subscription_response(
    target: str,
    session: SessionDep,
    token: str,
    group: str | None,
    template: str | None,
    emoji: bool,
) -> Response:
    expected = await get_subscription_token(session)
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid subscription token")
    try:
        if target in {"clash", "mihomo"}:
            content = await build_clash_subscription_from_pool(
                session,
                target=target,
                group=group,
                template=template,
                emoji=emoji,
            )
        elif target == "v2ray":
            content = await build_v2ray_subscription_from_pool(session, group=group, emoji=emoji)
        else:
            content, _ = await convert_subscription(
                session,
                api_target=target,
                group=group,
                template=template,
                emoji=emoji,
            )
    except (SubconverterError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    media_type = "text/plain; charset=utf-8" if target == "v2ray" else "text/yaml; charset=utf-8"
    return Response(content=content, media_type=media_type)


@router.get("/clash")
async def clash(
    session: SessionDep,
    token: str = Query(...),
    group: str | None = None,
    template: str | None = None,
    emoji: bool = True,
) -> Response:
    return await _subscription_response("clash", session, token, group, template, emoji)


@router.get("/mihomo")
async def mihomo(
    session: SessionDep,
    token: str = Query(...),
    group: str | None = None,
    template: str | None = None,
    emoji: bool = True,
) -> Response:
    return await _subscription_response("mihomo", session, token, group, template, emoji)


@router.get("/singbox")
async def singbox(
    session: SessionDep,
    token: str = Query(...),
    group: str | None = None,
    template: str | None = None,
    emoji: bool = True,
) -> Response:
    return await _subscription_response("singbox", session, token, group, template, emoji)


@router.get("/v2ray")
async def v2ray(
    session: SessionDep,
    token: str = Query(...),
    group: str | None = None,
    template: str | None = None,
    emoji: bool = True,
) -> Response:
    return await _subscription_response("v2ray", session, token, group, template, emoji)
