import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.timezone import CHINA_TZ, as_china, now_china
from app.models.subscription import Subscription
from app.services.aggregator import refresh_subscription_source
from app.services.audit import write_audit
from app.services.settings import (
    get_smart_proxy_auto_apply_interval_minutes,
    get_smart_proxy_monitor_interval_minutes,
    get_traffic_poll_interval_minutes,
)
from app.services.smart_proxy import (
    apply_mihomo_runtime_if_changed,
    reconcile_smart_proxy_runtime_after_traffic_change,
    refresh_smart_proxy_statuses,
)
from app.services.traffic import latest_traffic_snapshot, poll_traffic_snapshot


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=CHINA_TZ)
last_smart_proxy_apply_at: datetime | None = None
last_smart_proxy_monitor_at: datetime | None = None


def _as_china(value: datetime) -> datetime:
    return as_china(value) or value


def _subscription_refresh_due(subscription: Subscription, now: datetime) -> bool:
    if subscription.last_updated_at is None:
        return True
    interval_seconds = max(int(subscription.update_interval or 0), 60)
    return now - _as_china(subscription.last_updated_at) >= timedelta(seconds=interval_seconds)


async def refresh_enabled_subscriptions() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.scalars(select(Subscription).where(Subscription.enabled.is_(True)))
        now = now_china()
        success_count = 0
        failed: list[str] = []
        due_subscriptions = [item for item in result.all() if _subscription_refresh_due(item, now)]
        if not due_subscriptions:
            return
        for subscription in due_subscriptions:
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
                f"按订阅更新间隔刷新完成：到期 {len(due_subscriptions)} 个，成功 {success_count} 个，失败 {len(failed)} 个。"
                + (f"异常：{'；'.join(failed[:3])}。" if failed else "")
            ),
        )
        await session.commit()


async def poll_traffic_by_setting() -> None:
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_traffic_poll_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = now_china()
        latest = await latest_traffic_snapshot(session)
        if latest and latest.created_at and now - _as_china(latest.created_at) < timedelta(minutes=interval_minutes):
            return
        try:
            previous_snapshot = latest
            snapshot = await poll_traffic_snapshot(session)
            await reconcile_smart_proxy_runtime_after_traffic_change(
                session,
                previous_snapshot,
                snapshot,
                actor="system",
            )
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
        now = now_china()
        if last_smart_proxy_apply_at and now - last_smart_proxy_apply_at < timedelta(minutes=interval_minutes):
            return
        try:
            result, content_changed = await apply_mihomo_runtime_if_changed(session, reload_core=True)
            last_smart_proxy_apply_at = now
            if content_changed or result.error:
                await write_audit(
                    session,
                    actor="system",
                    action="reload",
                    resource="smart_proxy",
                    detail=(
                        f"定时检查智能代理运行时配置完成：配置文件 {result.config_path}，"
                        + ("检测到配置变化并已应用，" if content_changed else "配置无变化，")
                        + f"核心重载{'成功' if result.reloaded else '未完成'}"
                        + (f"，错误：{result.error}" if result.error else "")
                        + "。"
                    ),
                )
                await session.commit()
        except Exception as exc:
            logger.info("Scheduled smart proxy apply skipped: %s", exc)


async def monitor_smart_proxy_by_setting() -> None:
    global last_smart_proxy_monitor_at
    async with AsyncSessionLocal() as session:
        interval_minutes = await get_smart_proxy_monitor_interval_minutes(session)
        if interval_minutes <= 0:
            return
        now = now_china()
        if last_smart_proxy_monitor_at and now - last_smart_proxy_monitor_at < timedelta(minutes=interval_minutes):
            return
        try:
            summary = await refresh_smart_proxy_statuses(session)
            if (
                summary.get("status_changes", 0)
                or summary.get("current_node_changes", 0)
                or summary.get("closed_connections", 0)
            ):
                await write_audit(
                    session,
                    actor="system",
                    action="monitor",
                    resource="smart_proxy",
                    detail=(
                        "定时刷新智能代理运行状态完成："
                        f"状态变化 {summary.get('status_changes', 0)} 个，"
                        f"当前节点变化 {summary.get('current_node_changes', 0)} 个，"
                        f"关闭未授权连接 {summary.get('closed_connections', 0)} 个。"
                    ),
                )
                await session.commit()
            last_smart_proxy_monitor_at = now
        except Exception as exc:
            logger.info("Scheduled smart proxy monitor skipped: %s", exc)


async def maintenance_tick() -> None:
    steps = (
        refresh_enabled_subscriptions,
        poll_traffic_by_setting,
        apply_smart_proxy_by_setting,
        monitor_smart_proxy_by_setting,
    )
    for step in steps:
        try:
            await step()
        except Exception:
            logger.exception("Scheduled maintenance step failed: %s", step.__name__)


def start_scheduler() -> None:
    if scheduler.running:
        return
    job_defaults = {"replace_existing": True, "coalesce": True, "max_instances": 1}
    scheduler.add_job(maintenance_tick, "interval", minutes=1, id="maintenance_tick", **job_defaults)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
