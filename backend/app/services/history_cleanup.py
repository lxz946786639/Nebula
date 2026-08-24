from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_china
from app.models.ant_proxy_traffic import AntProxyTrafficSample
from app.models.audit import AuditLog
from app.models.node_snapshot import NodeSnapshot
from app.models.smart_proxy_health import SmartProxyHealthLog
from app.models.smart_proxy_stability import SmartProxyStabilitySample
from app.models.smart_proxy_switch import SmartProxySwitchLog
from app.models.smart_proxy_traffic import SmartProxyTrafficSample
from app.models.traffic_snapshot import TrafficSnapshot
from app.services.audit import write_audit
from app.services.settings import (
    HISTORY_RETENTION_ANT_PROXY_TRAFFIC_DAYS_KEY,
    HISTORY_RETENTION_AUDIT_LOG_DAYS_KEY,
    HISTORY_RETENTION_NODE_SNAPSHOT_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_HEALTH_LOG_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_STABILITY_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_SWITCH_LOG_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_TRAFFIC_DAYS_KEY,
    HISTORY_RETENTION_SUBSCRIPTION_TRAFFIC_DAYS_KEY,
    get_history_retention_days,
)


@dataclass(frozen=True)
class HistoryCleanupTarget:
    key: str
    label: str
    retention_key: str
    model: type[Any]
    timestamp_column: Any


HISTORY_CLEANUP_TARGETS = (
    HistoryCleanupTarget(
        "smart_proxy_traffic_samples",
        "智能代理流量统计",
        HISTORY_RETENTION_SMART_PROXY_TRAFFIC_DAYS_KEY,
        SmartProxyTrafficSample,
        SmartProxyTrafficSample.sampled_at,
    ),
    HistoryCleanupTarget(
        "ant_proxy_traffic_samples",
        "蚂蚁流量统计",
        HISTORY_RETENTION_ANT_PROXY_TRAFFIC_DAYS_KEY,
        AntProxyTrafficSample,
        AntProxyTrafficSample.sampled_at,
    ),
    HistoryCleanupTarget("audit_logs", "日志中心", HISTORY_RETENTION_AUDIT_LOG_DAYS_KEY, AuditLog, AuditLog.created_at),
    HistoryCleanupTarget(
        "traffic_snapshots",
        "订阅流量快照",
        HISTORY_RETENTION_SUBSCRIPTION_TRAFFIC_DAYS_KEY,
        TrafficSnapshot,
        TrafficSnapshot.created_at,
    ),
    HistoryCleanupTarget(
        "smart_proxy_stability_samples",
        "智能代理稳定性样本",
        HISTORY_RETENTION_SMART_PROXY_STABILITY_DAYS_KEY,
        SmartProxyStabilitySample,
        SmartProxyStabilitySample.sampled_at,
    ),
    HistoryCleanupTarget(
        "smart_proxy_health_logs",
        "智能代理健康检测日志",
        HISTORY_RETENTION_SMART_PROXY_HEALTH_LOG_DAYS_KEY,
        SmartProxyHealthLog,
        SmartProxyHealthLog.created_at,
    ),
    HistoryCleanupTarget(
        "smart_proxy_switch_logs",
        "智能代理节点切换历史",
        HISTORY_RETENTION_SMART_PROXY_SWITCH_LOG_DAYS_KEY,
        SmartProxySwitchLog,
        SmartProxySwitchLog.created_at,
    ),
    HistoryCleanupTarget(
        "node_snapshots",
        "节点转换快照",
        HISTORY_RETENTION_NODE_SNAPSHOT_DAYS_KEY,
        NodeSnapshot,
        NodeSnapshot.created_at,
    ),
)


def _deleted_count(rowcount: int | None) -> int:
    if rowcount is None or rowcount < 0:
        return 0
    return rowcount


def _cleanup_detail(
    retention_days: dict[str, int],
    cutoffs: dict[str, datetime],
    deleted: dict[str, int],
) -> str:
    targets = {target.key: target for target in HISTORY_CLEANUP_TARGETS}
    parts = [
        (
            f"{targets.get(key).label if targets.get(key) else key}"
            f"（保留 {retention_days.get(key, 0)} 天）{count} 条"
        )
        for key, count in deleted.items()
        if count > 0
    ]
    summary = "、".join(parts) if parts else "无过期数据"
    oldest_cutoff = min(cutoffs.values()) if cutoffs else None
    cutoff_text = f"，最早清理边界 {oldest_cutoff:%Y-%m-%d %H:%M:%S}" if oldest_cutoff else ""
    return f"历史数据清理完成{cutoff_text}，删除 {summary}。"


async def cleanup_history_data(
    session: AsyncSession,
    *,
    retention_days: int | None = None,
    actor: str = "system",
    write_log: bool = False,
) -> dict[str, Any]:
    # SQLite 存储/读回的 datetime 均无时区信息（naive 中国时间），cutoff 保持 naive 以与存储格式一致。
    now = now_china().replace(tzinfo=None)
    retention_by_target: dict[str, int] = {}
    cutoffs: dict[str, datetime] = {}
    deleted: dict[str, int] = {}
    for target in HISTORY_CLEANUP_TARGETS:
        days = (
            max(int(retention_days or 0), 0)
            if retention_days is not None
            else await get_history_retention_days(session, target.retention_key)
        )
        retention_by_target[target.key] = days
        if days <= 0:
            deleted[target.key] = 0
            continue
        cutoff = now - timedelta(days=days)
        cutoffs[target.key] = cutoff
        result = await session.execute(
            delete(target.model)
            .where(target.timestamp_column < cutoff)
            .execution_options(synchronize_session=False)
        )
        deleted[target.key] = _deleted_count(result.rowcount)

    total_deleted = sum(deleted.values())
    if write_log and total_deleted:
        await write_audit(
            session,
            actor=actor,
            action="cleanup",
            resource="history_cleanup",
            detail=_cleanup_detail(retention_by_target, cutoffs, deleted),
        )

    return {
        "skipped": not cutoffs,
        "retention_days": retention_by_target,
        "cutoffs": cutoffs,
        "deleted": deleted,
        "total_deleted": total_deleted,
    }
