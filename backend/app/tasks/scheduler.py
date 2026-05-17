import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.services.aggregator import convert_subscription, refresh_subscription_source
from app.services.audit import write_audit
from app.services.node_pool import sync_node_pool
from app.services.settings import (
    get_node_pool_sync_interval_minutes,
    get_smart_proxy_auto_apply_interval_minutes,
    get_smart_proxy_monitor_interval_minutes,
    get_traffic_poll_interval_minutes,
)
from app.services.smart_proxy import apply_mihomo_runtime, refresh_smart_proxy_statuses
from app.services.traffic import latest_traffic_snapshot, poll_traffic_snapshot


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")
last_node_pool_sync_at: datetime | None = None
last_smart_proxy_apply_at: datetime | None = None
last_smart_proxy_monitor_at: datetime | None = None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def refresh_enabled_subscriptions() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.scalars(select(Subscription).where(Subscription.enabled.is_(True)))
        success_count = 0
        failed: list[str] = []
        for subscription in result.all():
            try:
                await refresh_subscription_source(session, subscription, audit_actor="system")
                success_count += 1
            except Exception as exc:
                subscription.last_status = "failed"
                subscription.last_error = str(exc)
                await session.commit()
                failed.append(f"{subscription.name}: {exc}")
                logger.warning("Failed to refresh subscription %s: %s", subscription.id, exc)
        await write_audit(
            session,
            actor="system",
            action="refresh",
            resource="subscription",
            detail=(
                f"定时刷新订阅完成：成功 {success_count} 个，失败 {len(failed)} 个。"
                + (f"异常：{'；'.join(failed[:3])}。" if failed else "")
            ),
        )
        await session.commit()


async def warm_default_cache() -> None:
    async with AsyncSessionLocal() as session:
        try:
            await convert_subscription(session, api_target="singbox", group=None, template=None, emoji=True, bypass_cache=True)
        except Exception as exc:
            logger.info("Default cache warm skipped: %s", exc)


async def sync_node_pool_by_setting() -> None:
    global last_node_pool_sync_at
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_node_pool_sync_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = datetime.now(UTC)
        if last_node_pool_sync_at and now - last_node_pool_sync_at < timedelta(minutes=interval_minutes):
            return
        try:
            await sync_node_pool(session, emoji=True, audit_actor="system", audit_reason="定时同步")
            last_node_pool_sync_at = now
        except Exception as exc:
            logger.info("Scheduled node pool sync skipped: %s", exc)


async def poll_traffic_by_setting() -> None:
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_traffic_poll_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = datetime.now(UTC)
        latest = await latest_traffic_snapshot(session)
        if latest and latest.created_at and now - _as_utc(latest.created_at) < timedelta(minutes=interval_minutes):
            return
        try:
            snapshot = await poll_traffic_snapshot(session)
            failed = sum(1 for item in snapshot.items if item.get("error"))
            await write_audit(
                session,
                actor="system",
                action="traffic_refresh",
                resource="subscription",
                detail=f"定时刷新订阅流量完成：共 {len(snapshot.items)} 个订阅，异常 {failed} 个。",
            )
            await session.commit()
        except Exception as exc:
            logger.info("Scheduled traffic poll skipped: %s", exc)


async def apply_smart_proxy_by_setting() -> None:
    global last_smart_proxy_apply_at
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_smart_proxy_auto_apply_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = datetime.now(UTC)
        if last_smart_proxy_apply_at and now - last_smart_proxy_apply_at < timedelta(minutes=interval_minutes):
            return
        try:
            result = await apply_mihomo_runtime(session, reload_core=True)
            await write_audit(
                session,
                actor="system",
                action="reload",
                resource="smart_proxy",
                detail=(
                    f"定时应用智能代理运行时配置完成：配置文件 {result.config_path}，"
                    f"核心重载{'成功' if result.reloaded else '未完成'}"
                    + (f"，错误：{result.error}" if result.error else "")
                    + "。"
                ),
            )
            await session.commit()
            last_smart_proxy_apply_at = now
        except Exception as exc:
            logger.info("Scheduled smart proxy apply skipped: %s", exc)


async def monitor_smart_proxy_by_setting() -> None:
    global last_smart_proxy_monitor_at
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_smart_proxy_monitor_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = datetime.now(UTC)
        if last_smart_proxy_monitor_at and now - last_smart_proxy_monitor_at < timedelta(minutes=interval_minutes):
            return
        try:
            await refresh_smart_proxy_statuses(session)
            await write_audit(
                session,
                actor="system",
                action="monitor",
                resource="smart_proxy",
                detail="定时刷新智能代理运行状态完成。",
            )
            await session.commit()
            last_smart_proxy_monitor_at = now
        except Exception as exc:
            logger.info("Scheduled smart proxy monitor skipped: %s", exc)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(sync_node_pool_by_setting, "interval", minutes=1, id="sync_node_pool", replace_existing=True)
    scheduler.add_job(poll_traffic_by_setting, "interval", minutes=1, id="poll_traffic", replace_existing=True)
    scheduler.add_job(apply_smart_proxy_by_setting, "interval", minutes=1, id="apply_smart_proxy", replace_existing=True)
    scheduler.add_job(monitor_smart_proxy_by_setting, "interval", minutes=1, id="monitor_smart_proxy", replace_existing=True)
    scheduler.add_job(warm_default_cache, "interval", minutes=30, id="warm_default_cache", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
