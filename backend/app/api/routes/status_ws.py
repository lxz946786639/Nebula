import asyncio
from typing import Any

from fastapi import APIRouter, Query, WebSocket
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.core.cache import get_redis
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.core.timezone import now_china
from app.models.node import Node
from app.models.smart_proxy import SmartProxy
from app.models.subscription import Subscription
from app.models.user import User
from app.services.settings import get_public_base_url, get_subconverter_url, get_subscription_token
from app.services.smart_proxy import (
    add_smart_proxy_switch_log,
    apply_stability_priority_runtime,
    mihomo_core_status,
    smart_proxy_runtime_status,
)
from app.services.subconverter import SubconverterClient
from app.services.traffic import get_or_create_traffic_snapshot


router = APIRouter()


async def _authenticate(token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token, "access")
        user_id = int(payload["sub"])
    except (ValueError, TypeError, KeyError):
        return None
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user


def _client_subscription_urls(token: str) -> list[dict[str, str]]:
    return [
        {"label": "Mihomo / Clash.Meta", "target": "mihomo", "path": f"/api/sub/mihomo?token={token}&group=default&emoji=true"},
        {"label": "Clash", "target": "clash", "path": f"/api/sub/clash?token={token}&group=default&emoji=true"},
        {"label": "sing-box", "target": "singbox", "path": f"/api/sub/singbox?token={token}&group=default&emoji=true"},
        {"label": "v2rayN / v2ray", "target": "v2ray", "path": f"/api/sub/v2ray?token={token}&group=default&emoji=true"},
    ]


def _traffic_payload(snapshot) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "upload": snapshot.upload,
        "download": snapshot.download,
        "used": snapshot.used,
        "total": snapshot.total,
        "remaining": snapshot.remaining,
        "expire_at": snapshot.expire_at,
        "polled_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "items": [
            {
                "subscription_id": item.get("subscription_id", 0),
                "name": item.get("name", ""),
                "upload": item.get("upload", 0),
                "download": item.get("download", 0),
                "used": item.get("used", 0),
                "total": item.get("total", 0),
                "remaining": item.get("remaining", 0),
                "expire_at": item.get("expire_at"),
                "available": item.get("available", False),
                "error": item.get("error"),
            }
            for item in snapshot.items
        ],
    }


async def _dashboard_payload() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        subscriptions = await session.scalar(select(func.count()).select_from(Subscription)) or 0
        enabled = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))) or 0
        nodes = await session.scalar(select(func.count()).select_from(Node).where(Node.enabled.is_(True))) or 0
        smart_proxies = await session.scalar(select(func.count()).select_from(SmartProxy)) or 0
        enabled_smart_proxies = (
            await session.scalar(select(func.count()).select_from(SmartProxy).where(SmartProxy.enabled.is_(True))) or 0
        )
        last_seen_at = await session.scalar(select(func.max(Node.last_seen_at)).select_from(Node))
        try:
            redis = get_redis()
            await redis.ping()
            cache_keys = int(await redis.dbsize())
            redis_status = "ok"
        except Exception:
            cache_keys = 0
            redis_status = "unavailable"
        client = SubconverterClient(await get_subconverter_url(session))
        subconverter_status = "ok" if await client.health() else "unavailable"
        mihomo = await mihomo_core_status(session)
        traffic_snapshot = await get_or_create_traffic_snapshot(session)
        return {
            "subscriptions": subscriptions,
            "enabled_subscriptions": enabled,
            "nodes": nodes,
            "smart_proxies": smart_proxies,
            "enabled_smart_proxies": enabled_smart_proxies,
            "cache_keys": cache_keys,
            "redis_status": redis_status,
            "subconverter_status": subconverter_status,
            "mihomo_status": "ok" if mihomo["available"] else "unavailable",
            "mihomo_version": mihomo["version"],
            "last_updated_at": last_seen_at.isoformat() if last_seen_at else None,
            "public_base_url": await get_public_base_url(session),
            "traffic": _traffic_payload(traffic_snapshot),
            "client_subscriptions": _client_subscription_urls(await get_subscription_token(session)),
        }


async def _smart_proxies_payload() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        core = await mihomo_core_status(session)
        proxies = list((await session.scalars(select(SmartProxy).order_by(SmartProxy.id.asc()))).all())
        statuses: list[dict[str, Any]] = []
        stable_changed: list[SmartProxy] = []
        for proxy in proxies:
            status = await smart_proxy_runtime_status(session, proxy, run_delay=False)
            proxy.status = status["status"]
            proxy.last_error = status["error"]
            changed = add_smart_proxy_switch_log(session, proxy, status.get("current_node"), reason="WebSocket 状态推送发现当前节点变化")
            if changed:
                stable_changed.append(proxy)
            status["switch_count"] = proxy.switch_count or 0
            status["current_node"] = proxy.current_node
            statuses.append(status)
        await session.commit()
        if stable_changed:
            await apply_stability_priority_runtime(session, stable_changed)
        return {"core": core, "proxies": statuses}


async def _status_payload(topics: set[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "status",
        "sent_at": now_china().isoformat(),
    }
    if "dashboard" in topics:
        payload["dashboard"] = await _dashboard_payload()
    if "smart_proxies" in topics:
        payload["smart_proxies"] = await _smart_proxies_payload()
    return payload


@router.websocket("/status")
async def status_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    topics: str = Query(default="dashboard,smart_proxies"),
    interval_ms: int = Query(default=10000, ge=3000, le=60000),
) -> None:
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=1008)
        return
    topic_set = {item.strip() for item in topics.split(",") if item.strip()}
    topic_set &= {"dashboard", "smart_proxies"}
    if not topic_set:
        topic_set = {"dashboard", "smart_proxies"}
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(jsonable_encoder(await _status_payload(topic_set)))
            await asyncio.sleep(interval_ms / 1000)
    except Exception:
        return
