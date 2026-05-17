from urllib.parse import urlencode

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.cache import get_redis
from app.models.node import Node
from app.models.smart_proxy import SmartProxy
from app.models.subscription import Subscription
from app.schemas.dashboard import ClientSubscriptionUrl, DashboardStats, TrafficItem, TrafficStats
from app.services.settings import get_subconverter_url, get_subscription_token
from app.services.smart_proxy import mihomo_core_status
from app.services.subconverter import SubconverterClient
from app.models.traffic_snapshot import TrafficSnapshot
from app.services.traffic import get_or_create_traffic_snapshot, poll_traffic_snapshot


router = APIRouter()


def build_client_subscription_urls(token: str) -> list[ClientSubscriptionUrl]:
    targets = [
        ("Mihomo / Clash.Meta", "mihomo"),
        ("Clash", "clash"),
        ("sing-box", "singbox"),
        ("v2rayN / v2ray", "v2ray"),
    ]
    items: list[ClientSubscriptionUrl] = []
    for label, target in targets:
        query = urlencode({"token": token, "group": "default", "emoji": "true"})
        items.append(ClientSubscriptionUrl(label=label, target=target, path=f"/api/sub/{target}?{query}"))
    return items


def _traffic_stats(snapshot: TrafficSnapshot, subscription_statuses: dict[int, tuple[str | None, str | None]] | None = None) -> TrafficStats:
    subscription_statuses = subscription_statuses or {}
    return TrafficStats(
        upload=snapshot.upload,
        download=snapshot.download,
        used=snapshot.used,
        total=snapshot.total,
        remaining=snapshot.remaining,
        expire_at=snapshot.expire_at,
        polled_at=snapshot.created_at.isoformat() if snapshot.created_at else None,
        items=[
            TrafficItem(
                subscription_id=item.get("subscription_id", 0),
                name=item.get("name", ""),
                upload=item.get("upload", 0),
                download=item.get("download", 0),
                used=item.get("used", 0),
                total=item.get("total", 0),
                remaining=item.get("remaining", 0),
                expire_at=item.get("expire_at"),
                available=item.get("available", False),
                stale=item.get("stale", False),
                error=item.get("error"),
                subscription_status=subscription_statuses.get(int(item.get("subscription_id", 0)), (None, None))[0],
                subscription_error=subscription_statuses.get(int(item.get("subscription_id", 0)), (None, None))[1],
            )
            for item in snapshot.items
        ],
    )


@router.post("/traffic/refresh", response_model=TrafficStats)
async def refresh_dashboard_traffic(session: SessionDep, current_user: CurrentUser) -> TrafficStats:
    subscriptions = (await session.scalars(select(Subscription))).all()
    statuses = {item.id: (item.last_status, item.last_error) for item in subscriptions}
    return _traffic_stats(await poll_traffic_snapshot(session), statuses)


@router.get("", response_model=DashboardStats)
async def dashboard(session: SessionDep, current_user: CurrentUser) -> DashboardStats:
    subscriptions = await session.scalar(select(func.count()).select_from(Subscription)) or 0
    enabled = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))) or 0
    nodes = await session.scalar(select(func.count()).select_from(Node).where(Node.enabled.is_(True))) or 0
    smart_proxies = await session.scalar(select(func.count()).select_from(SmartProxy)) or 0
    enabled_smart_proxies = await session.scalar(select(func.count()).select_from(SmartProxy).where(SmartProxy.enabled.is_(True))) or 0
    last_seen_at = await session.scalar(select(func.max(Node.last_seen_at)).select_from(Node))
    last_updated_at = last_seen_at.isoformat() if last_seen_at else None
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
    subscription_items = (await session.scalars(select(Subscription))).all()
    subscription_statuses = {item.id: (item.last_status, item.last_error) for item in subscription_items}
    traffic = _traffic_stats(traffic_snapshot, subscription_statuses)
    return DashboardStats(
        subscriptions=subscriptions,
        enabled_subscriptions=enabled,
        nodes=nodes,
        smart_proxies=smart_proxies,
        enabled_smart_proxies=enabled_smart_proxies,
        cache_keys=cache_keys,
        redis_status=redis_status,
        subconverter_status=subconverter_status,
        mihomo_status="ok" if mihomo["available"] else "unavailable",
        mihomo_version=mihomo["version"],
        last_updated_at=last_updated_at,
        traffic=traffic,
        client_subscriptions=build_client_subscription_urls(await get_subscription_token(session)),
    )
