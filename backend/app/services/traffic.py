import asyncio
from dataclasses import dataclass
from datetime import datetime

import aiohttp
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import CHINA_TZ
from app.models.subscription import Subscription
from app.models.traffic_snapshot import TrafficSnapshot
from app.utils.network import validate_subscription_url


@dataclass(frozen=True)
class SubscriptionTraffic:
    subscription_id: int
    name: str
    upload: int = 0
    download: int = 0
    total: int = 0
    expire_at: str | None = None
    available: bool = False
    stale: bool = False
    error: str | None = None

    @property
    def used(self) -> int:
        return self.upload + self.download

    @property
    def remaining(self) -> int:
        return max(self.total - self.used, 0)


def parse_subscription_userinfo(value: str | None) -> tuple[int, int, int, str | None]:
    if not value:
        return 0, 0, 0, None

    parts: dict[str, str] = {}
    for item in value.split(";"):
        if "=" not in item:
            continue
        key, raw = item.split("=", 1)
        parts[key.strip().lower()] = raw.strip()

    upload = int(parts.get("upload") or 0)
    download = int(parts.get("download") or 0)
    total = int(parts.get("total") or 0)
    expire_at = None
    if parts.get("expire"):
        expire_at = datetime.fromtimestamp(int(parts["expire"]), tz=CHINA_TZ).isoformat()
    return upload, download, total, expire_at


async def fetch_subscription_traffic(
    session: aiohttp.ClientSession,
    *,
    subscription_id: int,
    name: str,
    url: str,
) -> SubscriptionTraffic:
    try:
        await validate_subscription_url(url)
        async with session.get(url) as response:
            header = response.headers.get("subscription-userinfo")
            if response.status >= 400:
                body = (await response.text())[:200]
                detail = f"subscription returned HTTP {response.status}"
                if body.strip():
                    detail = f"{detail}: {body.strip()}"
                return SubscriptionTraffic(subscription_id=subscription_id, name=name, available=False, error=detail)
            response.release()
            upload, download, total, expire_at = parse_subscription_userinfo(header)
            if total <= 0:
                return SubscriptionTraffic(
                    subscription_id=subscription_id,
                    name=name,
                    available=False,
                    error="subscription-userinfo header not found",
                )
            return SubscriptionTraffic(
                subscription_id=subscription_id,
                name=name,
                upload=upload,
                download=download,
                total=total,
                expire_at=expire_at,
                available=True,
            )
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        return SubscriptionTraffic(subscription_id=subscription_id, name=name, available=False, error=message)


async def collect_traffic(subscriptions: list) -> list[SubscriptionTraffic]:
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "ClashforWindows/0.20.39"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [
            fetch_subscription_traffic(
                session,
                subscription_id=item.id,
                name=item.name,
                url=item.url,
            )
            for item in subscriptions
        ]
        return await asyncio.gather(*tasks)


def _restore_previous_traffic(item: SubscriptionTraffic, previous: dict | None) -> SubscriptionTraffic:
    if item.available or not previous or int(previous.get("total") or 0) <= 0:
        return item
    upload = int(previous.get("upload") or 0)
    download = int(previous.get("download") or 0)
    total = int(previous.get("total") or 0)
    return SubscriptionTraffic(
        subscription_id=item.subscription_id,
        name=item.name,
        upload=upload,
        download=download,
        total=total,
        expire_at=previous.get("expire_at"),
        available=False,
        stale=True,
        error=item.error,
    )


def merge_previous_traffic(items: list[SubscriptionTraffic], snapshot: TrafficSnapshot | None) -> list[SubscriptionTraffic]:
    if snapshot is None:
        return items
    previous_by_id = {int(item.get("subscription_id") or 0): item for item in snapshot.items}
    return [_restore_previous_traffic(item, previous_by_id.get(item.subscription_id)) for item in items]


def traffic_item_payload(item: SubscriptionTraffic) -> dict:
    return {
        "subscription_id": item.subscription_id,
        "name": item.name,
        "upload": item.upload,
        "download": item.download,
        "used": item.used,
        "total": item.total,
        "remaining": item.remaining,
        "expire_at": item.expire_at,
        "available": item.available,
        "stale": item.stale,
        "error": item.error,
    }


def aggregate_traffic(items: list[SubscriptionTraffic]) -> dict:
    counted_items = [item for item in items if item.available or item.stale]
    expire_values = [item.expire_at for item in counted_items if item.expire_at]
    upload = sum(item.upload for item in counted_items)
    download = sum(item.download for item in counted_items)
    total = sum(item.total for item in counted_items)
    used = upload + download
    return {
        "upload": upload,
        "download": download,
        "used": used,
        "total": total,
        "remaining": max(total - used, 0),
        "expire_at": min(expire_values) if expire_values else None,
        "items": [traffic_item_payload(item) for item in items],
    }


async def collect_enabled_subscription_traffic(session: AsyncSession) -> list[SubscriptionTraffic]:
    enabled_items = (
        await session.scalars(select(Subscription).where(Subscription.enabled.is_(True)).order_by(Subscription.priority.asc()))
    ).all()
    return await collect_traffic(list(enabled_items))


async def prune_traffic_snapshots(session: AsyncSession, *, keep: int = 100) -> None:
    ids = list((await session.scalars(select(TrafficSnapshot.id).order_by(TrafficSnapshot.id.desc()).offset(keep))).all())
    if ids:
        await session.execute(delete(TrafficSnapshot).where(TrafficSnapshot.id.in_(ids)))


async def poll_traffic_snapshot(session: AsyncSession) -> TrafficSnapshot:
    items = await collect_enabled_subscription_traffic(session)
    items = merge_previous_traffic(items, await latest_traffic_snapshot(session))
    aggregate = aggregate_traffic(items)
    snapshot = TrafficSnapshot(**aggregate)
    session.add(snapshot)
    await prune_traffic_snapshots(session)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def latest_traffic_snapshot(session: AsyncSession) -> TrafficSnapshot | None:
    return await session.scalar(select(TrafficSnapshot).order_by(TrafficSnapshot.id.desc()).limit(1))


async def get_or_create_traffic_snapshot(session: AsyncSession) -> TrafficSnapshot:
    snapshot = await latest_traffic_snapshot(session)
    if snapshot is not None:
        return snapshot
    return await poll_traffic_snapshot(session)
