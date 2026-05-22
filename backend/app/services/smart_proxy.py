from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import aiohttp
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR, get_settings
from app.core.locks import exclusive_lock
from app.core.timezone import as_china, now_china
from app.models.node import Node
from app.models.smart_proxy import SmartProxy
from app.models.smart_proxy_health import SmartProxyHealthLog
from app.models.smart_proxy_switch import SmartProxySwitchLog
from app.models.system_setting import SystemSetting
from app.models.traffic_snapshot import TrafficSnapshot
from app.services.audit import write_audit
from app.services.node_latency import test_selected_node_latencies
from app.services.node_processor import dump_yaml_config
from app.services.settings import (
    get_mihomo_api_secret,
    get_mihomo_api_url,
    get_mihomo_core_config_path,
    get_mihomo_runtime_config_path,
    get_proxy_public_base_url,
    get_smart_proxy_exclude_unknown_traffic,
    get_smart_proxy_expire_soon_days,
    get_smart_proxy_low_remaining_mb,
    get_smart_proxy_min_remaining_mb,
    get_smart_proxy_port_range,
    get_smart_proxy_traffic_guard_enabled,
    public_host_port_from_base_url,
)
from app.services.traffic import latest_traffic_snapshot


PROXY_TYPES = {"http", "socks", "mixed"}
STRATEGIES = {"select", "stable", "fallback", "url-test", "load-balance", "relay", "round-robin"}
DATA_SOURCES = {"subscription", "ant"}
TEST_URL = "http://www.gstatic.com/generate_204"
SCENARIO_CHECKS = {
    "ai": ("chatgpt", "https://chat.openai.com/cdn-cgi/trace"),
    "streaming": ("netflix", "https://www.netflix.com/title/80018499"),
}
RUNTIME_NODE_ID_RE = re.compile(r"^node-(\d+)\b")
TRAFFIC_RUNTIME_RELOAD_COOLDOWN = timedelta(minutes=5)
CORE_TRAFFIC_STATE_KEY = "mihomo_core_traffic_state"
_core_traffic_sample: tuple[datetime, int, int] | None = None
_proxy_traffic_samples: dict[int, tuple[datetime, int, int]] = {}
_last_traffic_runtime_reload_at: datetime | None = None
_pending_traffic_runtime_reload = False


@dataclass(slots=True)
class RuntimeApplyResult:
    config_path: str
    enabled_services: int
    proxies: int
    proxy_groups: int
    listeners: int
    applied_proxy_ids: list[int] = field(default_factory=list)
    reloaded: bool = False
    error: str | None = None
    content: str | None = None
    content_changed: bool = True


class SmartProxyError(ValueError):
    pass


class MihomoApiError(RuntimeError):
    pass


@dataclass(slots=True)
class TrafficState:
    subscription_id: int
    available: bool
    remaining: int
    total: int
    expire_at: datetime | None
    status: str
    reason: str | None
    priority: int


@dataclass(slots=True)
class TrafficSchedule:
    enabled: bool
    total_nodes: int
    usable_nodes: int
    excluded_nodes: int
    risk_nodes: int
    unknown_nodes: int
    snapshot_at: datetime | None
    reasons: list[str]


@dataclass(slots=True)
class SmartProxyTrafficPolicy:
    traffic_guard_enabled: bool
    min_remaining_mb: int
    low_remaining_mb: int
    expire_soon_days: int
    exclude_unknown_traffic: bool


@dataclass(slots=True)
class TrafficRuntimeReconcileResult:
    changed_subscriptions: int = 0
    checked_nodes: int = 0
    online_nodes: int = 0
    failed_nodes: int = 0
    applied: bool = False
    content_changed: bool = False
    cooldown_active: bool = False
    pending_reload: bool = False
    reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ConnectionStats:
    active_connections: int = 0
    upload_total: int = 0
    download_total: int = 0
    upload_speed: int = 0
    download_speed: int = 0
    unauthorized_connections: int = 0
    source_ips: set[str] | None = None


def normalize_proxy_type(value: str) -> str:
    proxy_type = value.strip().lower()
    if proxy_type == "https":
        return "http"
    if proxy_type not in PROXY_TYPES:
        raise SmartProxyError("Unsupported proxy type")
    return proxy_type


def normalize_strategy(value: str) -> str:
    strategy = value.strip().lower()
    if strategy not in STRATEGIES:
        raise SmartProxyError("Unsupported smart proxy strategy")
    return strategy


def normalize_data_source(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"", "node", "nodes", "subscription", "subscriptions"}:
        return "subscription"
    if normalized in {"ant", "ant_proxy", "ant-proxy", "蚂蚁", "蚂蚁代理"}:
        return "ant"
    raise SmartProxyError("Unsupported smart proxy data source")


def endpoint_for(proxy: SmartProxy) -> str:
    scheme = "socks5" if proxy.proxy_type == "socks" else "http"
    auth = ""
    if proxy.username and proxy.password:
        auth = f"{proxy.username}:{proxy.password}@"
    elif proxy.access_token:
        auth = f"token:{proxy.access_token}@"
    return f"{scheme}://{auth}{proxy.listen_host}:{proxy.port}"


def endpoint_for_public_base_url(proxy: SmartProxy, public_base_url: str | None) -> str:
    endpoint = endpoint_for(proxy)
    host, public_port = public_host_port_from_base_url(public_base_url)
    if not host:
        return endpoint
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return endpoint
    auth = f"{parsed.netloc.rsplit('@', 1)[0]}@" if "@" in parsed.netloc else ""
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    port = public_port or proxy.port
    return urlunsplit((parsed.scheme, f"{auth}{host_part}:{port}", parsed.path, parsed.query, parsed.fragment))


async def public_endpoint_for(session: AsyncSession, proxy: SmartProxy) -> str:
    return endpoint_for_public_base_url(proxy, await get_proxy_public_base_url(session))


def runtime_group_name(proxy: SmartProxy) -> str:
    return f"Nebula::{proxy.id}::{proxy.name}"


def runtime_listener_name(proxy: SmartProxy) -> str:
    return f"nebula-{proxy.id}-{proxy.proxy_type}"


def runtime_node_name(node: Node) -> str:
    source = str(node.source_subscription_name or node.source_subscription_id or "source").strip()
    return f"node-{node.id} [{source}] {node.name}".strip()


def runtime_node_id(name: str) -> int | None:
    match = RUNTIME_NODE_ID_RE.match(name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def smart_proxy_stability_priority_enabled(proxy: SmartProxy) -> bool:
    return bool(proxy.strategy == "stable" or (proxy.stability_priority and proxy.strategy in {"select", "fallback"}))


def _prioritize_stable_current_node(nodes: list[Node], proxy: SmartProxy) -> list[Node]:
    if not smart_proxy_stability_priority_enabled(proxy) or not proxy.current_node:
        return nodes
    current_id = runtime_node_id(proxy.current_node)
    if current_id is None:
        return nodes
    current = [node for node in nodes if node.id == current_id]
    if not current:
        return nodes
    return current + [node for node in nodes if node.id != current_id]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_core_traffic_state(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


async def _core_traffic_setting(session: AsyncSession) -> SystemSetting | None:
    return await session.scalar(select(SystemSetting).where(SystemSetting.key == CORE_TRAFFIC_STATE_KEY))


async def _read_persisted_core_traffic(session: AsyncSession) -> tuple[int, int]:
    item = await _core_traffic_setting(session)
    state = _parse_core_traffic_state(item.value if item is not None else None)
    return _safe_int(state.get("upload_total")), _safe_int(state.get("download_total"))


async def _persist_core_traffic_sample(
    session: AsyncSession,
    *,
    api_url: str,
    raw_upload_total: int,
    raw_download_total: int,
    observed_at: datetime,
) -> tuple[int, int]:
    async with exclusive_lock("mihomo_core_traffic_state"):
        raw_upload_total = max(raw_upload_total, 0)
        raw_download_total = max(raw_download_total, 0)
        item = await _core_traffic_setting(session)
        state = _parse_core_traffic_state(item.value if item is not None else None)
        previous_api_url = str(state.get("api_url") or "")
        previous_raw_upload = _safe_int(state.get("raw_upload_total"))
        previous_raw_download = _safe_int(state.get("raw_download_total"))
        upload_total = _safe_int(state.get("upload_total"))
        download_total = _safe_int(state.get("download_total"))

        if not state:
            upload_total = max(raw_upload_total, 0)
            download_total = max(raw_download_total, 0)
        elif previous_api_url and previous_api_url != api_url:
            # A different Mihomo API may already have non-zero counters; use the
            # first read as its baseline so switching endpoints does not invent traffic.
            pass
        else:
            upload_delta = raw_upload_total - previous_raw_upload
            download_delta = raw_download_total - previous_raw_download
            upload_total += raw_upload_total if upload_delta < 0 else max(upload_delta, 0)
            download_total += raw_download_total if download_delta < 0 else max(download_delta, 0)

        if (
            item is not None
            and previous_api_url == api_url
            and previous_raw_upload == raw_upload_total
            and previous_raw_download == raw_download_total
            and _safe_int(state.get("upload_total")) == upload_total
            and _safe_int(state.get("download_total")) == download_total
        ):
            return upload_total, download_total

        payload = {
            "api_url": api_url,
            "upload_total": upload_total,
            "download_total": download_total,
            "raw_upload_total": raw_upload_total,
            "raw_download_total": raw_download_total,
            "updated_at": observed_at.isoformat(),
        }
        value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if item is None:
            session.add(
                SystemSetting(
                    key=CORE_TRAFFIC_STATE_KEY,
                    value=value,
                    secret=False,
                    description="Persisted Mihomo traffic totals",
                )
            )
        elif item.value != value:
            item.value = value
            item.description = "Persisted Mihomo traffic totals"
        await session.commit()
        return upload_total, download_total


def _speed_from_sample(
    previous: tuple[datetime, int, int] | None,
    current: tuple[datetime, int, int],
) -> tuple[int, int]:
    if previous is None:
        return 0, 0
    previous_at, previous_upload, previous_download = previous
    current_at, current_upload, current_download = current
    seconds = max((current_at - previous_at).total_seconds(), 0)
    if seconds <= 0:
        return 0, 0
    upload_delta = current_upload - previous_upload
    download_delta = current_download - previous_download
    if upload_delta < 0 or download_delta < 0:
        return 0, 0
    return round(upload_delta / seconds), round(download_delta / seconds)


def _connection_chains(connection: dict[str, Any]) -> set[str]:
    chains = connection.get("chains")
    if isinstance(chains, list):
        return {str(item) for item in chains if str(item).strip()}
    return set()


def _connection_source_ip(connection: dict[str, Any]) -> str | None:
    metadata = connection.get("metadata")
    if not isinstance(metadata, dict):
        return None
    for key in ("sourceIP", "source_ip", "srcIP", "src_ip"):
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def _connection_destination(connection: dict[str, Any]) -> str | None:
    metadata = connection.get("metadata")
    if not isinstance(metadata, dict):
        return None
    host = metadata.get("host") or metadata.get("destinationIP") or metadata.get("remoteDestination")
    port = metadata.get("destinationPort") or metadata.get("remoteDestinationPort")
    if host and port:
        return f"{host}:{port}"
    return str(host) if host else None


def _source_allowed(source_ip: str | None, whitelist: list[str] | None) -> bool:
    items = [str(item).strip() for item in whitelist or [] if str(item).strip()]
    if not items:
        return True
    if not source_ip:
        return False
    try:
        source = ip_address(source_ip)
    except ValueError:
        return False
    for item in items:
        if item == "*":
            return True
        try:
            if source in ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


def resolve_runtime_config_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def _normalize_list(values: list[Any] | None) -> list[Any]:
    return values if isinstance(values, list) else []


def smart_proxy_is_ant(proxy: SmartProxy) -> bool:
    return normalize_data_source(str(getattr(proxy, "data_source", "") or "subscription")) == "ant"


def _tag_match(node: Node, wanted_tags: list[str]) -> bool:
    if not wanted_tags:
        return True
    node_tags = {str(tag).lower() for tag in (node.tags or [])}
    return all(tag.lower() in node_tags for tag in wanted_tags)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return as_china(parsed)


def _traffic_exclusion_reason(
    raw: dict[str, Any] | None,
    policy: SmartProxyTrafficPolicy,
    reference_time: datetime,
) -> str | None:
    if not isinstance(raw, dict):
        return None
    total = int(raw.get("total") or 0)
    remaining = int(raw.get("remaining") or 0)
    expire_at = _parse_datetime(raw.get("expire_at"))
    min_remaining = policy.min_remaining_mb * 1024 * 1024
    if expire_at is not None and expire_at <= reference_time:
        return "subscription expired"
    if total > 0 and remaining <= min_remaining:
        return "subscription traffic exhausted"
    return None


async def smart_proxy_traffic_policy(session: AsyncSession, proxy: SmartProxy | None = None) -> SmartProxyTrafficPolicy:
    global_policy = SmartProxyTrafficPolicy(
        traffic_guard_enabled=await get_smart_proxy_traffic_guard_enabled(session),
        min_remaining_mb=await get_smart_proxy_min_remaining_mb(session),
        low_remaining_mb=await get_smart_proxy_low_remaining_mb(session),
        expire_soon_days=await get_smart_proxy_expire_soon_days(session),
        exclude_unknown_traffic=await get_smart_proxy_exclude_unknown_traffic(session),
    )
    if proxy is None:
        return global_policy
    return SmartProxyTrafficPolicy(
        traffic_guard_enabled=(
            proxy.traffic_guard_enabled
            if proxy.traffic_guard_enabled is not None
            else global_policy.traffic_guard_enabled
        ),
        min_remaining_mb=proxy.min_remaining_mb if proxy.min_remaining_mb is not None else global_policy.min_remaining_mb,
        low_remaining_mb=proxy.low_remaining_mb if proxy.low_remaining_mb is not None else global_policy.low_remaining_mb,
        expire_soon_days=proxy.expire_soon_days if proxy.expire_soon_days is not None else global_policy.expire_soon_days,
        exclude_unknown_traffic=(
            proxy.exclude_unknown_traffic
            if proxy.exclude_unknown_traffic is not None
            else global_policy.exclude_unknown_traffic
        ),
    )


def smart_proxy_uses_global_policy(proxy: SmartProxy) -> bool:
    return (
        proxy.traffic_guard_enabled is None
        and proxy.min_remaining_mb is None
        and proxy.low_remaining_mb is None
        and proxy.expire_soon_days is None
        and proxy.exclude_unknown_traffic is None
    )


async def _traffic_state_map(
    session: AsyncSession,
    policy: SmartProxyTrafficPolicy,
) -> tuple[dict[int, TrafficState], datetime | None]:
    snapshot = await latest_traffic_snapshot(session)
    if snapshot is None:
        return {}, None

    low_remaining = policy.low_remaining_mb * 1024 * 1024
    expire_soon_days = policy.expire_soon_days
    exclude_unknown = policy.exclude_unknown_traffic
    now = now_china()
    soon_before = now + timedelta(days=expire_soon_days)
    states: dict[int, TrafficState] = {}

    for raw in snapshot.items or []:
        try:
            subscription_id = int(raw.get("subscription_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        available = bool(raw.get("available"))
        total = int(raw.get("total") or 0)
        remaining = int(raw.get("remaining") or 0)
        expire_at = _parse_datetime(raw.get("expire_at"))
        exclusion_reason = _traffic_exclusion_reason(raw, policy, now)
        low = available and low_remaining > 0 and remaining <= low_remaining
        expire_soon = expire_at is not None and now < expire_at <= soon_before

        status = "healthy"
        reason: str | None = None
        priority = 0
        if exclusion_reason:
            status = "excluded"
            reason = exclusion_reason
            priority = 3
        elif not available:
            status = "excluded" if exclude_unknown else "unknown"
            reason = str(raw.get("error") or "traffic header missing")
            priority = 3 if exclude_unknown else 2
        elif low:
            status = "risk"
            reason = "subscription traffic is low"
            priority = 1
        elif expire_soon:
            status = "risk"
            reason = "subscription expires soon"
            priority = 1

        states[subscription_id] = TrafficState(
            subscription_id=subscription_id,
            available=available,
            remaining=remaining,
            total=total,
            expire_at=expire_at,
            status=status,
            reason=reason,
            priority=priority,
        )

    return states, snapshot.created_at


def _traffic_priority(node: Node, states: dict[int, TrafficState], *, guard_enabled: bool) -> tuple[int, bool, int, int, str]:
    latency = node.latency if node.latency is not None else 999999
    if not guard_enabled:
        return 0, node.latency is None, latency, 0, ""
    state = states.get(node.source_subscription_id or -1)
    if state is None:
        return 0, node.latency is None, latency, 0, ""
    return state.priority, node.latency is None, latency, -(state.remaining), state.reason or ""


async def traffic_schedule_for_nodes(
    session: AsyncSession,
    nodes: list[Node],
    *,
    proxy: SmartProxy | None = None,
) -> tuple[list[Node], TrafficSchedule]:
    policy = await smart_proxy_traffic_policy(session, proxy)
    guard_enabled = policy.traffic_guard_enabled
    if not guard_enabled:
        return nodes, TrafficSchedule(
            enabled=False,
            total_nodes=len(nodes),
            usable_nodes=len(nodes),
            excluded_nodes=0,
            risk_nodes=0,
            unknown_nodes=0,
            snapshot_at=None,
            reasons=[],
        )

    states, snapshot_at = await _traffic_state_map(session, policy)
    if not states:
        return nodes, TrafficSchedule(
            enabled=True,
            total_nodes=len(nodes),
            usable_nodes=len(nodes),
            excluded_nodes=0,
            risk_nodes=0,
            unknown_nodes=0,
            snapshot_at=snapshot_at,
            reasons=["No traffic snapshot found; traffic scheduling skipped"],
        )

    selected: list[Node] = []
    excluded_nodes = 0
    risk_nodes = 0
    unknown_nodes = 0
    reasons: list[str] = []
    seen_reasons: set[str] = set()
    for node in nodes:
        state = states.get(node.source_subscription_id or -1)
        if state is None:
            selected.append(node)
            continue
        if state.status == "excluded":
            excluded_nodes += 1
            reason = f"{node.source_subscription_name or node.source_subscription_id}: {state.reason}"
            if reason not in seen_reasons:
                reasons.append(reason)
                seen_reasons.add(reason)
            continue
        if state.status == "risk":
            risk_nodes += 1
            reason = f"{node.source_subscription_name or node.source_subscription_id}: {state.reason}"
            if reason not in seen_reasons:
                reasons.append(reason)
                seen_reasons.add(reason)
        elif state.status == "unknown":
            unknown_nodes += 1
        selected.append(node)

    selected.sort(key=lambda item: _traffic_priority(item, states, guard_enabled=guard_enabled))
    return selected, TrafficSchedule(
        enabled=True,
        total_nodes=len(nodes),
        usable_nodes=len(selected),
        excluded_nodes=excluded_nodes,
        risk_nodes=risk_nodes,
        unknown_nodes=unknown_nodes,
        snapshot_at=snapshot_at,
        reasons=reasons[:10],
    )


async def allocate_smart_proxy_port(session: AsyncSession) -> int:
    start, end = await get_smart_proxy_port_range(session)
    used_ports = set((await session.scalars(select(SmartProxy.port))).all())
    candidates = [port for port in range(start, end + 1) if port not in used_ports]
    random.shuffle(candidates)
    if candidates:
        return candidates[0]
    raise SmartProxyError("No available smart proxy ports")


async def allocate_runtime_proxy_port(session: AsyncSession, *, allow_port: int | None = None) -> int:
    start, end = await get_smart_proxy_port_range(session)
    used_ports = {int(port) for port in (await session.scalars(select(SmartProxy.port))).all()}
    if allow_port is not None and start <= allow_port <= end and allow_port not in used_ports:
        return allow_port
    candidates = [port for port in range(start, end + 1) if port not in used_ports]
    random.shuffle(candidates)
    if candidates:
        return candidates[0]
    raise SmartProxyError(f"代理端口池 {start}-{end} 没有可用端口")


async def ensure_runtime_proxy_port_available(session: AsyncSession, port: int, *, allow_port: int | None = None) -> None:
    start, end = await get_smart_proxy_port_range(session)
    if port < start or port > end:
        raise SmartProxyError(f"端口 {port} 不在部署映射范围 {start}-{end} 内")

    stmt = select(SmartProxy).where(SmartProxy.port == port)
    existing = await session.scalar(stmt)
    if existing is not None:
        raise SmartProxyError(f"端口 {port} 已被智能代理「{existing.name}」占用")

    if allow_port is not None and port == allow_port:
        return


async def ensure_unique_port(session: AsyncSession, port: int, *, exclude_id: int | None = None) -> None:
    start, end = await get_smart_proxy_port_range(session)
    if port < start or port > end:
        raise SmartProxyError(f"端口 {port} 不在部署映射范围 {start}-{end} 内")

    stmt = select(SmartProxy).where(SmartProxy.port == port)
    if exclude_id is not None:
        stmt = stmt.where(SmartProxy.id != exclude_id)
    existing = await session.scalar(stmt)
    if existing is not None:
        raise SmartProxyError(f"Port {port} is already used by {existing.name}")


async def source_nodes_for_proxy(session: AsyncSession, proxy: SmartProxy, *, latency_order: bool = True) -> list[Node]:
    stmt = select(Node).where(Node.enabled.is_(True))
    source_mode = str(proxy.source_mode or "all")
    subscription_ids = _normalize_list(proxy.subscription_ids)
    country_codes = [str(item).upper() for item in _normalize_list(proxy.country_codes) if str(item).strip()]
    protocol_types = [str(item).lower() for item in _normalize_list(proxy.protocol_types) if str(item).strip()]
    source_node_ids = [int(item) for item in _normalize_list(proxy.node_ids) if str(item).strip()]
    tags = [str(item).strip() for item in _normalize_list(proxy.tags) if str(item).strip()]

    if source_mode == "manual":
        if not source_node_ids:
            return []
        stmt = stmt.where(Node.id.in_(source_node_ids))
    elif source_mode == "subscription":
        if not subscription_ids:
            return []
        stmt = stmt.where(Node.source_subscription_id.in_(subscription_ids))

    if country_codes:
        stmt = stmt.where(Node.country_code.in_(country_codes))

    if source_mode != "manual" and protocol_types:
        stmt = stmt.where(Node.type.in_(protocol_types))

    if latency_order:
        stmt = stmt.order_by(Node.latency.is_(None), Node.latency.asc(), Node.country_code.asc(), Node.name.asc(), Node.id.asc())
    else:
        stmt = stmt.order_by(Node.id.asc())
    nodes = list((await session.scalars(stmt)).all())
    filtered = [node for node in nodes if _tag_match(node, tags)] if tags else nodes
    if source_mode == "manual" and source_node_ids:
        by_id = {node.id: node for node in filtered}
        return [by_id[node_id] for node_id in source_node_ids if node_id in by_id]
    return filtered


def _apply_strategy_node_selection(nodes: list[Node], proxy: SmartProxy) -> list[Node]:
    strategy_node_ids = [int(item) for item in _normalize_list(proxy.strategy_node_ids) if str(item).strip()]
    if not strategy_node_ids:
        return nodes
    by_id = {node.id: node for node in nodes}
    return [by_id[node_id] for node_id in strategy_node_ids if node_id in by_id]


async def candidate_nodes_for_proxy(session: AsyncSession, proxy: SmartProxy) -> list[Node]:
    source_nodes = await source_nodes_for_proxy(session, proxy, latency_order=True)
    selected_nodes = _apply_strategy_node_selection(source_nodes, proxy)
    scheduled, _ = await traffic_schedule_for_nodes(session, selected_nodes, proxy=proxy)
    return _prioritize_stable_current_node(scheduled, proxy)


def _ant_node_sort_key(node: Any) -> tuple[int, int, str, str, str]:
    latency = getattr(node, "latency_ms", None)
    return (
        1 if latency is None else 0,
        int(latency or 0),
        str(getattr(node, "line_type", "") or ""),
        str(getattr(node, "country_code", "") or ""),
        str(getattr(node, "name", "") or ""),
    )


def _ant_node_tag_match(node: Any, wanted_tags: list[str]) -> bool:
    if not wanted_tags:
        return True
    values = {
        str(getattr(node, "line_type", "") or "").lower(),
        str(getattr(node, "line_label", "") or "").lower(),
        str(getattr(node, "source", "") or "").lower(),
        str(getattr(node, "group", "") or "").lower(),
        f"line:{str(getattr(node, 'line_type', '') or '').lower()}",
        f"source:{str(getattr(node, 'source', '') or '').lower()}",
        f"group:{str(getattr(node, 'group', '') or '').lower()}",
    }
    return all(tag.lower() in values for tag in wanted_tags)


def _normalize_ant_node_ids(values: list[Any] | None) -> list[str]:
    return [str(item).strip() for item in _normalize_list(values) if str(item).strip()]


async def source_ant_nodes_for_proxy(proxy: SmartProxy, *, latency_order: bool = True) -> list[Any]:
    from app.services.ant_proxy import ant_proxy_service

    if not ant_proxy_service.nodes:
        return []

    nodes = list(ant_proxy_service.nodes)
    source_mode = str(proxy.source_mode or "all")
    country_codes = {str(item).upper() for item in _normalize_list(proxy.country_codes) if str(item).strip()}
    protocol_types = {str(item).lower() for item in _normalize_list(proxy.protocol_types) if str(item).strip()}
    tags = [str(item).strip() for item in _normalize_list(proxy.tags) if str(item).strip()]
    source_node_ids = _normalize_ant_node_ids(proxy.ant_node_ids)

    if source_mode == "manual":
        if not source_node_ids:
            return []
        by_id = {node.id: node for node in nodes}
        nodes = [by_id[node_id] for node_id in source_node_ids if node_id in by_id]

    if country_codes:
        nodes = [node for node in nodes if str(node.country_code or "").upper() in country_codes]
    if tags:
        nodes = [node for node in nodes if _ant_node_tag_match(node, tags)]
    if protocol_types:
        nodes = [node for node in nodes if str(node.transport or "").lower() in protocol_types]
    if latency_order:
        nodes.sort(key=_ant_node_sort_key)
    return nodes


def _apply_strategy_ant_node_selection(nodes: list[Any], proxy: SmartProxy) -> list[Any]:
    strategy_node_ids = _normalize_ant_node_ids(proxy.ant_strategy_node_ids)
    if not strategy_node_ids:
        return nodes
    by_id = {node.id: node for node in nodes}
    return [by_id[node_id] for node_id in strategy_node_ids if node_id in by_id]


async def candidate_ant_nodes_for_proxy(proxy: SmartProxy) -> list[Any]:
    source_nodes = await source_ant_nodes_for_proxy(proxy, latency_order=True)
    return _apply_strategy_ant_node_selection(source_nodes, proxy)


async def traffic_schedule_for_proxy(session: AsyncSession, proxy: SmartProxy) -> TrafficSchedule:
    if smart_proxy_is_ant(proxy):
        nodes = await source_ant_nodes_for_proxy(proxy, latency_order=False)
        selected_nodes = _apply_strategy_ant_node_selection(nodes, proxy)
        return TrafficSchedule(
            enabled=False,
            total_nodes=len(nodes),
            usable_nodes=len(selected_nodes),
            excluded_nodes=0,
            risk_nodes=0,
            unknown_nodes=0,
            snapshot_at=None,
            reasons=[],
        )
    source_nodes = await source_nodes_for_proxy(session, proxy, latency_order=False)
    selected_nodes = _apply_strategy_node_selection(source_nodes, proxy)
    _, schedule = await traffic_schedule_for_nodes(session, selected_nodes, proxy=proxy)
    return schedule


def _snapshot_item_map(snapshot: TrafficSnapshot | None) -> dict[int, dict[str, Any]]:
    if snapshot is None:
        return {}
    items: dict[int, dict[str, Any]] = {}
    for raw in snapshot.items or []:
        if not isinstance(raw, dict):
            continue
        try:
            subscription_id = int(raw.get("subscription_id"))
        except (TypeError, ValueError):
            continue
        if subscription_id > 0:
            items[subscription_id] = raw
    return items


def _snapshot_reference_time(snapshot: TrafficSnapshot | None, fallback: datetime) -> datetime:
    if snapshot is None or snapshot.created_at is None:
        return fallback
    return as_china(snapshot.created_at) or fallback


def _traffic_exclusion_reasons(
    snapshot: TrafficSnapshot | None,
    policy: SmartProxyTrafficPolicy,
    reference_time: datetime,
) -> dict[int, str]:
    reasons: dict[int, str] = {}
    for subscription_id, raw in _snapshot_item_map(snapshot).items():
        reason = _traffic_exclusion_reason(raw, policy, reference_time)
        if reason:
            reasons[subscription_id] = reason
    return reasons


async def _smart_proxy_nodes_for_subscriptions(
    session: AsyncSession,
    subscription_ids: set[int],
) -> tuple[list[Node], set[str]]:
    if not subscription_ids:
        return [], set()
    proxies = list((await session.scalars(select(SmartProxy).where(SmartProxy.enabled.is_(True)))).all())
    nodes_by_id: dict[int, Node] = {}
    proxy_names: set[str] = set()
    for proxy in proxies:
        nodes = await source_nodes_for_proxy(session, proxy, latency_order=False)
        matched = [node for node in nodes if node.id is not None and node.source_subscription_id in subscription_ids]
        if not matched:
            continue
        proxy_names.add(proxy.name)
        for node in matched:
            nodes_by_id[node.id] = node
    return list(nodes_by_id.values()), proxy_names


def _traffic_runtime_reload_cooldown_remaining(now: datetime) -> timedelta | None:
    if _last_traffic_runtime_reload_at is None:
        return None
    elapsed = now - _last_traffic_runtime_reload_at
    if elapsed >= TRAFFIC_RUNTIME_RELOAD_COOLDOWN:
        return None
    return TRAFFIC_RUNTIME_RELOAD_COOLDOWN - elapsed


def _mark_pending_traffic_runtime_reload() -> None:
    global _pending_traffic_runtime_reload
    _pending_traffic_runtime_reload = True


def _clear_pending_traffic_runtime_reload() -> None:
    global _pending_traffic_runtime_reload
    _pending_traffic_runtime_reload = False


def _mark_traffic_runtime_reload_attempt(now: datetime) -> None:
    global _last_traffic_runtime_reload_at
    _last_traffic_runtime_reload_at = now


async def _auto_apply_changed_mihomo_runtime(
    session: AsyncSession,
    *,
    actor: str,
    reason_parts: list[str],
    changed_subscriptions: int,
    checked_nodes: int,
    online_nodes: int,
    failed_nodes: int,
    proxy_names: set[str],
) -> TrafficRuntimeReconcileResult:
    result, content_changed = await apply_mihomo_runtime_if_changed(session, reload_core=True)
    if not content_changed:
        _clear_pending_traffic_runtime_reload()
        return TrafficRuntimeReconcileResult(
            changed_subscriptions=changed_subscriptions,
            checked_nodes=checked_nodes,
            online_nodes=online_nodes,
            failed_nodes=failed_nodes,
            content_changed=False,
            reason="runtime content unchanged",
        )

    now = now_china()
    _mark_traffic_runtime_reload_attempt(now)
    _clear_pending_traffic_runtime_reload()
    scope_text = (
        f"影响订阅 {changed_subscriptions} 个，"
        f"检测节点 {checked_nodes} 个，在线 {online_nodes} 个，失败 {failed_nodes} 个，"
        f"影响智能代理 {len(proxy_names)} 个"
        + (f"（{ '、'.join(sorted(proxy_names)[:3]) }）" if proxy_names else "")
        + "，"
        if changed_subscriptions or checked_nodes or proxy_names
        else "处理冷却期内累积变更，"
    )
    await write_audit(
        session,
        actor=actor,
        action="reload",
        resource="smart_proxy",
        detail=(
            "订阅流量状态变化后自动重新应用 Mihomo runtime："
            f"触发原因 {'、'.join(reason_parts)}，"
            f"{scope_text}"
            + f"核心重载{'成功' if result.reloaded else '未完成'}"
            + (f"，错误：{result.error}" if result.error else "")
            + "。"
        ),
    )
    await session.commit()
    return TrafficRuntimeReconcileResult(
        changed_subscriptions=changed_subscriptions,
        checked_nodes=checked_nodes,
        online_nodes=online_nodes,
        failed_nodes=failed_nodes,
        applied=True,
        content_changed=True,
        reason="; ".join(reason_parts),
        error=result.error,
    )


async def reconcile_smart_proxy_runtime_after_traffic_change(
    session: AsyncSession,
    previous_snapshot: TrafficSnapshot | None,
    current_snapshot: TrafficSnapshot,
    *,
    actor: str = "system",
) -> TrafficRuntimeReconcileResult:
    global _pending_traffic_runtime_reload
    policy = await smart_proxy_traffic_policy(session)
    if not policy.traffic_guard_enabled:
        return TrafficRuntimeReconcileResult(reason="traffic guard disabled")

    now = now_china()
    previous_reasons = _traffic_exclusion_reasons(
        previous_snapshot,
        policy,
        _snapshot_reference_time(previous_snapshot, now),
    )
    current_items = _snapshot_item_map(current_snapshot)
    current_reasons = _traffic_exclusion_reasons(current_snapshot, policy, now)
    changed_subscription_ids = {
        subscription_id
        for subscription_id in set(previous_reasons) | set(current_reasons)
        if subscription_id in current_items
        if previous_reasons.get(subscription_id) != current_reasons.get(subscription_id)
    }
    if not changed_subscription_ids:
        if _pending_traffic_runtime_reload:
            remaining = _traffic_runtime_reload_cooldown_remaining(now)
            if remaining is not None:
                return TrafficRuntimeReconcileResult(
                    cooldown_active=True,
                    pending_reload=True,
                    reason=f"runtime reload cooldown active, {round(remaining.total_seconds())}s remaining",
                )
            return await _auto_apply_changed_mihomo_runtime(
                session,
                actor=actor,
                reason_parts=["冷却结束后补充应用待处理变更"],
                changed_subscriptions=0,
                checked_nodes=0,
                online_nodes=0,
                failed_nodes=0,
                proxy_names=set(),
            )
        return TrafficRuntimeReconcileResult(reason="no blocking traffic state change")

    affected_nodes, proxy_names = await _smart_proxy_nodes_for_subscriptions(session, changed_subscription_ids)
    if not affected_nodes:
        return TrafficRuntimeReconcileResult(
            changed_subscriptions=len(changed_subscription_ids),
            reason="no referenced smart proxy nodes",
        )

    check = await test_selected_node_latencies(session, affected_nodes, timeout_ms=3000, concurrency=30)
    nodes_by_id = {node.id: node for node in affected_nodes if node.id is not None}
    failed_node_ids = set(check.failed_node_ids)
    online_node_ids = set(check.online_node_ids)
    blocked_subscription_ids = {item for item in changed_subscription_ids if current_reasons.get(item)}
    restored_subscription_ids = changed_subscription_ids - blocked_subscription_ids

    blocked_and_failed = any(
        node.source_subscription_id in blocked_subscription_ids and node_id in failed_node_ids
        for node_id, node in nodes_by_id.items()
    )
    restored_and_online = any(
        node.source_subscription_id in restored_subscription_ids and node_id in online_node_ids
        for node_id, node in nodes_by_id.items()
    )
    if not (blocked_and_failed or restored_and_online):
        await session.commit()
        return TrafficRuntimeReconcileResult(
            changed_subscriptions=len(changed_subscription_ids),
            checked_nodes=check.tested_nodes,
            online_nodes=check.online_nodes,
            failed_nodes=check.failed_nodes,
            reason="checked nodes did not require runtime reload",
        )

    reason_parts: list[str] = []
    if blocked_and_failed:
        reason_parts.append("到期/耗尽订阅节点不可用")
    if restored_and_online:
        reason_parts.append("订阅恢复且节点可用")
    remaining = _traffic_runtime_reload_cooldown_remaining(now)
    if remaining is not None:
        _mark_pending_traffic_runtime_reload()
        await session.commit()
        return TrafficRuntimeReconcileResult(
            changed_subscriptions=len(changed_subscription_ids),
            checked_nodes=check.tested_nodes,
            online_nodes=check.online_nodes,
            failed_nodes=check.failed_nodes,
            cooldown_active=True,
            pending_reload=True,
            reason=f"runtime reload cooldown active, {round(remaining.total_seconds())}s remaining",
        )

    return await _auto_apply_changed_mihomo_runtime(
        session,
        actor=actor,
        reason_parts=reason_parts,
        changed_subscriptions=len(changed_subscription_ids),
        checked_nodes=check.tested_nodes,
        online_nodes=check.online_nodes,
        failed_nodes=check.failed_nodes,
        proxy_names=proxy_names,
    )


async def smart_proxy_candidate_count(session: AsyncSession, proxy: SmartProxy) -> int:
    if smart_proxy_is_ant(proxy):
        return len(await candidate_ant_nodes_for_proxy(proxy))
    return len(await candidate_nodes_for_proxy(session, proxy))


def _base_runtime_config() -> dict[str, Any]:
    return {
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "0.0.0.0:9090",
        "dns": {
            "enable": True,
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "default-nameserver": ["223.5.5.5", "119.29.29.29", "8.8.8.8"],
            "nameserver": ["223.5.5.5", "119.29.29.29", "8.8.8.8"],
            "fallback": ["1.1.1.1", "8.8.8.8"],
        },
        "proxies": [],
        "proxy-groups": [],
        "listeners": [],
        "rules": ["MATCH,DIRECT"],
    }


def _group_config(proxy: SmartProxy, proxy_names: list[str]) -> dict[str, Any]:
    if proxy.strategy == "round-robin":
        group_type = "load-balance"
    elif proxy.strategy == "stable":
        group_type = "fallback"
    else:
        group_type = proxy.strategy
    group: dict[str, Any] = {
        "name": runtime_group_name(proxy),
        "type": group_type,
        "proxies": proxy_names,
    }
    if proxy.strategy in {"stable", "fallback", "url-test", "load-balance", "round-robin"}:
        group["url"] = proxy.health_check_url or TEST_URL
        group["interval"] = proxy.health_check_interval
    if proxy.strategy == "url-test":
        group["tolerance"] = proxy.tolerance
    if proxy.strategy == "round-robin":
        group["strategy"] = "round-robin"
    elif proxy.strategy == "load-balance":
        group["strategy"] = "consistent-hashing"
    return group


def _listener_config(proxy: SmartProxy, listen_host: str | None = None) -> dict[str, Any]:
    listener: dict[str, Any] = {
        "name": runtime_listener_name(proxy),
        "type": proxy.proxy_type,
        "port": proxy.port,
        "listen": listen_host or proxy.listen_host,
        "proxy": runtime_group_name(proxy),
    }
    if proxy.proxy_type in {"socks", "mixed"}:
        listener["udp"] = True
    users: list[dict[str, str]] = []
    if proxy.username and proxy.password:
        users.append({"username": proxy.username, "password": proxy.password})
    if proxy.access_token:
        users.append({"username": "token", "password": proxy.access_token})
    if users:
        listener["users"] = users
    return listener


async def runtime_bind_host(session: AsyncSession, configured_host: str | None) -> str:
    core_path = await get_mihomo_core_config_path(session)
    host = (configured_host or "").strip()
    if core_path.startswith("/root/.config/mihomo/") and host not in {"", "0.0.0.0", "::"}:
        return "0.0.0.0"
    return host or "0.0.0.0"


async def runtime_listener_bind_host(session: AsyncSession, proxy: SmartProxy) -> str:
    return await runtime_bind_host(session, proxy.listen_host)


async def ant_adapter_hosts(session: AsyncSession) -> tuple[str, str]:
    settings = get_settings()
    bind_override = settings.ANT_ADAPTER_BIND_HOST.strip()
    connect_override = settings.ANT_ADAPTER_CONNECT_HOST.strip()
    core_path = await get_mihomo_core_config_path(session)
    if core_path.startswith("/root/.config/mihomo/"):
        api_host = (urlsplit(await get_mihomo_api_url(session)).hostname or "").lower()
        if api_host in {"127.0.0.1", "localhost", "::1"}:
            return bind_override or "0.0.0.0,::", connect_override or "host.docker.internal"
        return bind_override or "0.0.0.0", connect_override or "backend"
    return bind_override or "127.0.0.1", connect_override or "127.0.0.1"


async def build_mihomo_runtime_config(session: AsyncSession) -> tuple[dict[str, Any], RuntimeApplyResult]:
    smart_proxies = list(
        (await session.scalars(select(SmartProxy).where(SmartProxy.enabled.is_(True)).order_by(SmartProxy.id.asc()))).all()
    )
    config = _base_runtime_config()
    node_name_by_id: dict[int, str] = {}
    node_raw_by_id: dict[int, dict[str, Any]] = {}
    ant_raw_by_name: dict[str, dict[str, Any]] = {}
    applied_proxy_ids: list[int] = []
    ant_adapters_ready = False

    async def ensure_ant_adapters() -> tuple[bool, str | None]:
        nonlocal ant_adapters_ready
        if ant_adapters_ready:
            return True, None
        from app.services.ant_proxy import DEFAULT_ANT_LISTEN_PORT, ant_proxy_service

        if not ant_proxy_service.nodes:
            return False, "请先在蚂蚁代理页登录 Ant 账号或上传 ant.db"
        adapter_bind_host, adapter_connect_host = await ant_adapter_hosts(session)
        try:
            await ant_proxy_service.start(
                listen_host="127.0.0.1",
                listen_port=DEFAULT_ANT_LISTEN_PORT,
                adapter_bind_host=adapter_bind_host,
                adapter_connect_host=adapter_connect_host,
            )
        except Exception as exc:
            return False, f"Ant 内部适配器启动失败：{exc}"
        ant_adapters_ready = True
        return True, None

    for smart_proxy in smart_proxies:
        if smart_proxy_is_ant(smart_proxy):
            from app.services.ant_proxy import ant_proxy_service

            nodes = await candidate_ant_nodes_for_proxy(smart_proxy)
            if not nodes:
                smart_proxy.status = "degraded"
                smart_proxy.last_error = "No Ant nodes matched this smart proxy"
                continue
            ready, error = await ensure_ant_adapters()
            if not ready:
                smart_proxy.status = "degraded"
                smart_proxy.last_error = error or "Ant adapters are not ready"
                continue
            proxy_names: list[str] = []
            for node in nodes:
                raw = ant_proxy_service.mihomo_proxy_config_for_node(node)
                if not raw:
                    continue
                name = str(raw["name"])
                ant_raw_by_name[name] = raw
                proxy_names.append(name)
            if not proxy_names:
                smart_proxy.status = "degraded"
                smart_proxy.last_error = "No Ant adapters matched this smart proxy"
                continue
            config["proxy-groups"].append(_group_config(smart_proxy, proxy_names))
            config["listeners"].append(_listener_config(smart_proxy, await runtime_listener_bind_host(session, smart_proxy)))
            smart_proxy.status = "configured"
            smart_proxy.last_error = None
            applied_proxy_ids.append(smart_proxy.id)
            continue

        nodes = await candidate_nodes_for_proxy(session, smart_proxy)
        if not nodes:
            smart_proxy.status = "degraded"
            schedule = await traffic_schedule_for_proxy(session, smart_proxy)
            if schedule.excluded_nodes and schedule.reasons:
                smart_proxy.last_error = "No usable nodes after traffic scheduling: " + "; ".join(schedule.reasons[:3])
            else:
                smart_proxy.last_error = "No candidate nodes matched this smart proxy"
            continue
        proxy_names: list[str] = []
        for node in nodes:
            node_name = node_name_by_id.get(node.id)
            if node_name is None:
                node_name = runtime_node_name(node)
                node_name_by_id[node.id] = node_name
                raw = deepcopy(node.raw or {})
                raw["name"] = node_name
                node_raw_by_id[node.id] = raw
            proxy_names.append(node_name)
        config["proxy-groups"].append(_group_config(smart_proxy, proxy_names))
        config["listeners"].append(_listener_config(smart_proxy, await runtime_listener_bind_host(session, smart_proxy)))
        smart_proxy.status = "configured"
        smart_proxy.last_error = None
        applied_proxy_ids.append(smart_proxy.id)

    config["proxies"] = [
        *list(node_raw_by_id.values()),
        *list(ant_raw_by_name.values()),
    ]
    path = resolve_runtime_config_path(await get_mihomo_runtime_config_path(session))
    return config, RuntimeApplyResult(
        config_path=str(path),
        enabled_services=len(smart_proxies),
        proxies=len(config["proxies"]),
        proxy_groups=len(config["proxy-groups"]),
        listeners=len(config["listeners"]),
        applied_proxy_ids=applied_proxy_ids,
    )


async def write_mihomo_runtime_config(session: AsyncSession) -> RuntimeApplyResult:
    async with exclusive_lock("mihomo_runtime"):
        return await _write_mihomo_runtime_config_unlocked(session)


async def _build_mihomo_runtime_content(session: AsyncSession) -> tuple[str, RuntimeApplyResult]:
    config, result = await build_mihomo_runtime_config(session)
    secret = await get_mihomo_api_secret(session)
    if secret:
        config["secret"] = secret
    content = dump_yaml_config(config)
    result.content = content
    return content, result


def _runtime_content_changed(path: Path, content: str) -> bool:
    try:
        return not path.exists() or path.read_text(encoding="utf-8") != content
    except OSError:
        return True


def _write_runtime_content(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


async def _mark_enabled_proxies_applied(session: AsyncSession) -> None:
    now = now_china()
    proxies = list((await session.scalars(select(SmartProxy).where(SmartProxy.enabled.is_(True)))).all())
    for proxy in proxies:
        proxy.last_applied_at = now


async def _write_mihomo_runtime_config_unlocked(session: AsyncSession) -> RuntimeApplyResult:
    content, result = await _build_mihomo_runtime_content(session)
    path = Path(result.config_path)
    result.content_changed = _runtime_content_changed(path, content)
    if result.content_changed:
        _write_runtime_content(path, content)
    await session.commit()
    return result


async def reload_mihomo_config(session: AsyncSession, config_path: str) -> tuple[bool, str | None]:
    api_url = await get_mihomo_api_url(session)
    secret = await get_mihomo_api_secret(session)
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
            async with http.put(f"{api_url}/configs", params={"force": "true"}, json={"path": config_path}) as response:
                body = await response.text()
                if response.status >= 400:
                    return False, f"Mihomo reload failed: {response.status} {body[:300]}"
        return True, None
    except aiohttp.ClientError as exc:
        return False, f"Cannot connect to Mihomo API at {api_url}: {exc}"


async def apply_mihomo_runtime(session: AsyncSession, *, reload_core: bool = False) -> RuntimeApplyResult:
    async with exclusive_lock("mihomo_runtime"):
        result = await _write_mihomo_runtime_config_unlocked(session)
        if reload_core:
            core_config_path = await get_mihomo_core_config_path(session)
            reloaded, error = await reload_mihomo_config(session, core_config_path or result.config_path)
            result.reloaded = reloaded
            result.error = error
            if reloaded:
                await _mark_enabled_proxies_applied(session)
                await session.commit()
        return result


async def apply_mihomo_runtime_if_changed(session: AsyncSession, *, reload_core: bool = False) -> tuple[RuntimeApplyResult, bool]:
    async with exclusive_lock("mihomo_runtime"):
        content, result = await _build_mihomo_runtime_content(session)
        path = Path(result.config_path)
        result.content_changed = _runtime_content_changed(path, content)
        if not result.content_changed:
            await session.commit()
            return result, False

        _write_runtime_content(path, content)
        if reload_core:
            core_config_path = await get_mihomo_core_config_path(session)
            reloaded, error = await reload_mihomo_config(session, core_config_path or result.config_path)
            result.reloaded = reloaded
            result.error = error
            if reloaded:
                await _mark_enabled_proxies_applied(session)
        await session.commit()
        return result, True


async def apply_stability_priority_runtime(
    session: AsyncSession,
    proxies: list[SmartProxy],
) -> RuntimeApplyResult | None:
    if not any(proxy.enabled and proxy.current_node and smart_proxy_stability_priority_enabled(proxy) for proxy in proxies):
        return None
    return await apply_mihomo_runtime(session, reload_core=True)


async def mihomo_get_json(session: AsyncSession, path: str, *, params: dict[str, Any] | None = None, timeout_seconds: int = 8) -> Any:
    api_url = await get_mihomo_api_url(session)
    secret = await get_mihomo_api_secret(session)
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
            async with http.get(f"{api_url}{path}", params=params) as response:
                body = await response.text()
                if response.status >= 400:
                    raise MihomoApiError(f"Mihomo API returned {response.status}: {body[:300]}")
                if not body:
                    return {}
                return await response.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise MihomoApiError(f"Cannot connect to Mihomo API at {api_url}: {exc}") from exc


async def mihomo_delete(session: AsyncSession, path: str, *, timeout_seconds: int = 8) -> None:
    api_url = await get_mihomo_api_url(session)
    secret = await get_mihomo_api_secret(session)
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
            async with http.delete(f"{api_url}{path}") as response:
                body = await response.text()
                if response.status >= 400:
                    raise MihomoApiError(f"Mihomo API returned {response.status}: {body[:300]}")
    except aiohttp.ClientError as exc:
        raise MihomoApiError(f"Cannot connect to Mihomo API at {api_url}: {exc}") from exc


async def mihomo_connections(session: AsyncSession) -> dict[str, Any]:
    data = await mihomo_get_json(session, "/connections")
    return data if isinstance(data, dict) else {}


async def mihomo_core_status(session: AsyncSession) -> dict[str, Any]:
    global _core_traffic_sample
    api_url = await get_mihomo_api_url(session)
    try:
        version_data = await mihomo_get_json(session, "/version")
        connections_available = True
        try:
            connections_data = await mihomo_connections(session)
        except MihomoApiError:
            connections_available = False
            connections_data = {}
        connections = connections_data.get("connections") if isinstance(connections_data, dict) else []
        now = now_china()
        connections_available = (
            connections_available
            and isinstance(connections_data, dict)
            and ("uploadTotal" in connections_data or "downloadTotal" in connections_data)
        )
        raw_upload_total = _safe_int(connections_data.get("uploadTotal")) if isinstance(connections_data, dict) else 0
        raw_download_total = _safe_int(connections_data.get("downloadTotal")) if isinstance(connections_data, dict) else 0
        if connections_available:
            upload_total, download_total = await _persist_core_traffic_sample(
                session,
                api_url=api_url,
                raw_upload_total=raw_upload_total,
                raw_download_total=raw_download_total,
                observed_at=now,
            )
        else:
            upload_total, download_total = await _read_persisted_core_traffic(session)
        upload_speed, download_speed = _speed_from_sample(
            _core_traffic_sample,
            (now, upload_total, download_total),
        )
        _core_traffic_sample = (now, upload_total, download_total)
        return {
            "api_url": api_url,
            "available": True,
            "version": version_data.get("version") if isinstance(version_data, dict) else None,
            "active_connections": len(connections) if isinstance(connections, list) else 0,
            "download_total": download_total,
            "upload_total": upload_total,
            "download_speed": download_speed,
            "upload_speed": upload_speed,
            "memory": connections_data.get("memory") if isinstance(connections_data, dict) else None,
            "error": None,
        }
    except MihomoApiError as exc:
        upload_total, download_total = await _read_persisted_core_traffic(session)
        return {
            "api_url": api_url,
            "available": False,
            "version": None,
            "active_connections": 0,
            "download_total": download_total,
            "upload_total": upload_total,
            "download_speed": 0,
            "upload_speed": 0,
            "memory": None,
            "error": str(exc),
        }


async def mihomo_proxy_map(session: AsyncSession) -> dict[str, Any]:
    data = await mihomo_get_json(session, "/proxies")
    proxies = data.get("proxies") if isinstance(data, dict) else {}
    return proxies if isinstance(proxies, dict) else {}


async def mihomo_group_delay(session: AsyncSession, group_name: str, *, url: str = TEST_URL, timeout_ms: int = 5000) -> int | None:
    data = await mihomo_get_json(
        session,
        f"/group/{quote(group_name, safe='')}/delay",
        params={"url": url, "timeout": str(timeout_ms)},
        timeout_seconds=max(timeout_ms // 1000 + 3, 8),
    )
    if isinstance(data, dict) and data.get("delay") is not None:
        return int(data["delay"])
    if isinstance(data, dict):
        delays = [int(value) for value in data.values() if isinstance(value, int | float) and value > 0]
        return min(delays) if delays else None
    return None


async def mihomo_group_delay_map(
    session: AsyncSession,
    group_name: str,
    *,
    url: str = TEST_URL,
    timeout_ms: int = 8000,
) -> tuple[dict[str, int], str | None]:
    try:
        data = await mihomo_get_json(
            session,
            f"/group/{quote(group_name, safe='')}/delay",
            params={"url": url, "timeout": str(timeout_ms)},
            timeout_seconds=max(timeout_ms // 1000 + 5, 10),
        )
    except MihomoApiError as exc:
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "Mihomo returned an unexpected delay payload"
    if data.get("delay") is not None:
        return {group_name: int(data["delay"])}, None
    delays: dict[str, int] = {}
    for name, value in data.items():
        try:
            delay = int(value)
        except (TypeError, ValueError):
            continue
        if delay > 0:
            delays[str(name)] = delay
    return delays, None


def _latest_history_delay(proxy_data: dict[str, Any] | None) -> int | None:
    if not isinstance(proxy_data, dict):
        return None
    history = proxy_data.get("history")
    if not isinstance(history, list) or not history:
        return None
    latest = history[-1]
    if not isinstance(latest, dict):
        return None
    try:
        delay = int(latest.get("delay"))
    except (TypeError, ValueError):
        return None
    return delay if delay > 0 else None


def _delay_summary(runtime_nodes: list[str], proxies: dict[str, Any]) -> dict[str, Any]:
    delays: list[tuple[str, int]] = []
    online_nodes = 0
    for name in runtime_nodes:
        item = proxies.get(name)
        delay = _latest_history_delay(item if isinstance(item, dict) else None)
        if isinstance(item, dict) and (item.get("alive") is True or (item.get("alive") is None and delay is not None)):
            online_nodes += 1
        if delay is not None:
            delays.append((name, delay))
    best = min(delays, key=lambda item: item[1]) if delays else None
    return {
        "online_nodes": online_nodes,
        "failed_nodes": max(len(runtime_nodes) - online_nodes, 0),
        "average_delay": round(sum(delay for _, delay in delays) / len(delays)) if delays else None,
        "best_node": best[0] if best else None,
        "delay": best[1] if best else None,
    }


def _runtime_node_status(runtime_nodes: list[str], online_nodes: int) -> tuple[str, str | None]:
    if not runtime_nodes:
        return "degraded", "No runtime nodes in Mihomo group"
    if online_nodes <= 0:
        return "proxy_unavailable", "All proxy nodes are unavailable"
    return "running", None


def _loopback_host(value: str | None) -> bool:
    host = (value or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _smart_proxy_bind_check() -> dict[str, Any]:
    bind_host = get_settings().SMART_PROXY_BIND_HOST.strip() or "127.0.0.1"
    if _loopback_host(bind_host):
        return {
            "check_type": "host_bind",
            "status": "warning",
            "delay": None,
            "message": f"智能代理宿主机端口当前绑定 {bind_host}，仅 Ubuntu 本机可访问；外部设备请设置 SMART_PROXY_BIND_HOST=0.0.0.0 并重建/重启 mihomo。",
        }
    return {
        "check_type": "host_bind",
        "status": "ok",
        "delay": None,
        "message": f"智能代理宿主机端口绑定 {bind_host}",
    }


def _proxy_credentials(proxy: SmartProxy) -> tuple[str, str] | None:
    if proxy.username and proxy.password:
        return proxy.username, proxy.password
    if proxy.access_token:
        return "token", proxy.access_token
    return None


async def _read_http_head(reader: asyncio.StreamReader, timeout_seconds: float) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 65536:
        chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout_seconds)
        if not chunk:
            break
        data += chunk
    return data


def _http_status_code(data: bytes) -> int | None:
    first_line = data.split(b"\r\n", 1)[0].decode("latin1", errors="replace") if data else ""
    parts = first_line.split()
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _mihomo_listener_host(api_url: str) -> str:
    host = (urlsplit(api_url).hostname or "127.0.0.1").strip()
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


async def _probe_http_listener(host: str, port: int, proxy: SmartProxy, timeout_seconds: float) -> tuple[bool, int | None, str | None]:
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    started = datetime.now()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        parsed = urlsplit(TEST_URL)
        target_host = parsed.hostname or "www.gstatic.com"
        lines = [
            f"GET {TEST_URL} HTTP/1.1",
            f"Host: {target_host}",
            "User-Agent: Nebula-SmartProxy-Probe/1.0",
            "Connection: close",
        ]
        credentials = _proxy_credentials(proxy)
        if credentials is not None:
            token = base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode("utf-8")).decode("ascii")
            lines.append(f"Proxy-Authorization: Basic {token}")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))
        await writer.drain()
        head = await _read_http_head(reader, timeout_seconds)
        status_code = _http_status_code(head)
        if status_code is None:
            return False, None, "Listener did not return an HTTP response"
        if 200 <= status_code < 400:
            return True, max(1, round((datetime.now() - started).total_seconds() * 1000)), None
        return False, None, f"Listener HTTP probe returned {status_code}"
    except Exception as exc:
        return False, None, f"Listener HTTP probe failed at {host}:{port}: {exc}"
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def _probe_socks_listener(host: str, port: int, proxy: SmartProxy, timeout_seconds: float) -> tuple[bool, int | None, str | None]:
    writer: asyncio.StreamWriter | None = None
    started = datetime.now()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        credentials = _proxy_credentials(proxy)
        methods = b"\x00\x02" if credentials else b"\x00"
        writer.write(b"\x05" + bytes([len(methods)]) + methods)
        await writer.drain()
        method_response = await asyncio.wait_for(reader.readexactly(2), timeout=timeout_seconds)
        if method_response[0] != 0x05 or method_response[1] == 0xFF:
            return False, None, "SOCKS listener rejected authentication methods"
        if method_response[1] == 0x02:
            if credentials is None:
                return False, None, "SOCKS listener requires authentication"
            username = credentials[0].encode("utf-8")
            password = credentials[1].encode("utf-8")
            if len(username) > 255 or len(password) > 255:
                return False, None, "SOCKS credentials are too long"
            writer.write(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
            await writer.drain()
            auth_response = await asyncio.wait_for(reader.readexactly(2), timeout=timeout_seconds)
            if auth_response != b"\x01\x00":
                return False, None, "SOCKS listener authentication failed"
        target = b"www.gstatic.com"
        writer.write(b"\x05\x01\x00\x03" + bytes([len(target)]) + target + (80).to_bytes(2, "big"))
        await writer.drain()
        reply = await asyncio.wait_for(reader.readexactly(4), timeout=timeout_seconds)
        if reply[1] != 0x00:
            return False, None, f"SOCKS listener connect failed with code {reply[1]}"
        if reply[3] == 0x01:
            await asyncio.wait_for(reader.readexactly(6), timeout=timeout_seconds)
        elif reply[3] == 0x03:
            length = (await asyncio.wait_for(reader.readexactly(1), timeout=timeout_seconds))[0]
            await asyncio.wait_for(reader.readexactly(length + 2), timeout=timeout_seconds)
        elif reply[3] == 0x04:
            await asyncio.wait_for(reader.readexactly(18), timeout=timeout_seconds)
        writer.write(b"GET /generate_204 HTTP/1.1\r\nHost: www.gstatic.com\r\nConnection: close\r\n\r\n")
        await writer.drain()
        head = await _read_http_head(reader, timeout_seconds)
        status_code = _http_status_code(head)
        if status_code is None:
            return False, None, "SOCKS listener did not return target HTTP response"
        if 200 <= status_code < 400:
            return True, max(1, round((datetime.now() - started).total_seconds() * 1000)), None
        return False, None, f"SOCKS listener target probe returned {status_code}"
    except Exception as exc:
        return False, None, f"SOCKS listener probe failed at {host}:{port}: {exc}"
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def smart_proxy_listener_probe(
    session: AsyncSession,
    proxy: SmartProxy,
    *,
    timeout_ms: int = 8000,
) -> tuple[str, int | None, str | None]:
    timeout_seconds = max(1.0, timeout_ms / 1000)
    host = _mihomo_listener_host(await get_mihomo_api_url(session))
    if proxy.proxy_type in {"http", "mixed"}:
        ok, delay, error = await _probe_http_listener(host, proxy.port, proxy, timeout_seconds)
    else:
        ok, delay, error = await _probe_socks_listener(host, proxy.port, proxy, timeout_seconds)
    return ("ok" if ok else "failed"), delay, error


def _empty_connection_stats(proxy_id: int) -> dict[str, Any]:
    return {
        "active_connections": 0,
        "online_users": 0,
        "source_ips": [],
        "upload_total": 0,
        "download_total": 0,
        "upload_speed": 0,
        "download_speed": 0,
        "unauthorized_connections": 0,
        "switch_count": 0,
    }


async def smart_proxy_connection_stats(
    session: AsyncSession,
    proxies: list[SmartProxy] | None = None,
) -> dict[int, dict[str, Any]]:
    global _proxy_traffic_samples
    if proxies is None:
        proxies = list((await session.scalars(select(SmartProxy).where(SmartProxy.enabled.is_(True)))).all())
    stats_by_id = {proxy.id: ConnectionStats(source_ips=set()) for proxy in proxies}
    if not proxies:
        return {}

    data = await mihomo_connections(session)
    connections = data.get("connections")
    if not isinstance(connections, list):
        connections = []

    groups = {runtime_group_name(proxy): proxy for proxy in proxies}
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        chains = _connection_chains(connection)
        if not chains:
            continue
        upload = _safe_int(connection.get("upload"))
        download = _safe_int(connection.get("download"))
        source_ip = _connection_source_ip(connection)
        for group_name, proxy in groups.items():
            if group_name not in chains:
                continue
            stats = stats_by_id[proxy.id]
            stats.active_connections += 1
            stats.upload_total += upload
            stats.download_total += download
            if source_ip and stats.source_ips is not None:
                stats.source_ips.add(source_ip)
            if not _source_allowed(source_ip, proxy.ip_whitelist):
                stats.unauthorized_connections += 1

    now = now_china()
    payload: dict[int, dict[str, Any]] = {}
    for proxy in proxies:
        stats = stats_by_id[proxy.id]
        current = (now, stats.upload_total, stats.download_total)
        upload_speed, download_speed = _speed_from_sample(_proxy_traffic_samples.get(proxy.id), current)
        _proxy_traffic_samples[proxy.id] = current
        source_ips = sorted(stats.source_ips or set())
        payload[proxy.id] = {
            "active_connections": stats.active_connections,
            "online_users": len(source_ips),
            "source_ips": source_ips,
            "upload_total": stats.upload_total,
            "download_total": stats.download_total,
            "upload_speed": upload_speed,
            "download_speed": download_speed,
            "unauthorized_connections": stats.unauthorized_connections,
            "switch_count": proxy.switch_count or 0,
        }
    return payload


async def enforce_smart_proxy_access(
    session: AsyncSession,
    proxy: SmartProxy | None = None,
) -> dict[str, Any]:
    if proxy is not None:
        proxies = [proxy] if proxy.enabled and proxy.ip_whitelist else []
    else:
        proxies = list(
            (
                await session.scalars(
                    select(SmartProxy).where(SmartProxy.enabled.is_(True), SmartProxy.ip_whitelist.is_not(None))
                )
            ).all()
        )
        proxies = [item for item in proxies if item.ip_whitelist]
    result: dict[str, Any] = {"checked_connections": 0, "closed_connections": 0, "violations": []}
    if not proxies:
        return result

    data = await mihomo_connections(session)
    connections = data.get("connections")
    if not isinstance(connections, list):
        return result
    groups = {runtime_group_name(item): item for item in proxies}
    closed_ids: set[str] = set()
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        result["checked_connections"] += 1
        connection_id = str(connection.get("id") or "")
        if not connection_id or connection_id in closed_ids:
            continue
        chains = _connection_chains(connection)
        source_ip = _connection_source_ip(connection)
        for group_name, item in groups.items():
            if group_name not in chains or _source_allowed(source_ip, item.ip_whitelist):
                continue
            await mihomo_delete(session, f"/connections/{quote(connection_id, safe='')}")
            closed_ids.add(connection_id)
            result["closed_connections"] += 1
            result["violations"].append(
                {
                    "proxy_id": item.id,
                    "proxy_name": item.name,
                    "connection_id": connection_id,
                    "source_ip": source_ip,
                    "destination": _connection_destination(connection),
                }
            )
            break
    return result


def record_smart_proxy_current_node(
    proxy: SmartProxy,
    current_node: Any,
    *,
    reason: str,
) -> tuple[SmartProxySwitchLog | None, bool]:
    next_node = str(current_node) if current_node else None
    previous_node = proxy.current_node
    if not next_node and smart_proxy_stability_priority_enabled(proxy) and proxy.enabled:
        return None, False
    changed = previous_node != next_node
    if next_node and previous_node and previous_node != next_node:
        proxy.switch_count = (proxy.switch_count or 0) + 1
        proxy.current_node = next_node
        session_log = SmartProxySwitchLog(
            smart_proxy_id=proxy.id,
            from_node=previous_node,
            to_node=next_node,
            reason=reason,
        )
        return session_log, True
    proxy.current_node = next_node
    return None, changed


def add_smart_proxy_switch_log(
    session: AsyncSession,
    proxy: SmartProxy,
    current_node: Any,
    *,
    reason: str,
) -> bool:
    log, changed = record_smart_proxy_current_node(proxy, current_node, reason=reason)
    if log is not None:
        session.add(log)
    return changed


async def smart_proxy_runtime_status(session: AsyncSession, proxy: SmartProxy, *, run_delay: bool = False) -> dict[str, Any]:
    core = await mihomo_core_status(session)
    group_name = runtime_group_name(proxy)
    endpoint = await public_endpoint_for(session, proxy)
    candidate_count = await smart_proxy_candidate_count(session, proxy)
    traffic_schedule = await traffic_schedule_for_proxy(session, proxy)
    traffic_payload = {
        "traffic_guard_enabled": traffic_schedule.enabled,
        "traffic_excluded_nodes": traffic_schedule.excluded_nodes,
        "traffic_risk_nodes": traffic_schedule.risk_nodes,
        "traffic_unknown_nodes": traffic_schedule.unknown_nodes,
        "traffic_snapshot_at": traffic_schedule.snapshot_at,
        "traffic_reasons": traffic_schedule.reasons,
    }
    stats_payload = _empty_connection_stats(proxy.id)
    stats_payload["switch_count"] = proxy.switch_count or 0
    if core["available"]:
        try:
            stats_payload.update((await smart_proxy_connection_stats(session, [proxy])).get(proxy.id, {}))
        except MihomoApiError:
            pass
    if not proxy.enabled:
        return {
            "proxy_id": proxy.id,
            "name": proxy.name,
            "endpoint": endpoint,
            "group_name": group_name,
            "enabled": False,
            "core_available": core["available"],
            "status": "stopped",
            "current_node": None,
            "candidate_nodes": candidate_count,
            "runtime_nodes": 0,
            "online_nodes": 0,
            "failed_nodes": 0,
            "average_delay": None,
            "best_node": None,
            "delay": None,
            "history": [],
            "error": None,
            **stats_payload,
            **traffic_payload,
        }
    if not core["available"]:
        return {
            "proxy_id": proxy.id,
            "name": proxy.name,
            "endpoint": endpoint,
            "group_name": group_name,
            "enabled": True,
            "core_available": False,
            "status": "core_unavailable",
            "current_node": None,
            "candidate_nodes": candidate_count,
            "runtime_nodes": 0,
            "online_nodes": 0,
            "failed_nodes": 0,
            "average_delay": None,
            "best_node": None,
            "delay": None,
            "history": [],
            "error": core["error"],
            **stats_payload,
            **traffic_payload,
        }
    try:
        proxies = await mihomo_proxy_map(session)
        group = proxies.get(group_name)
        if not isinstance(group, dict):
            return {
                "proxy_id": proxy.id,
                "name": proxy.name,
                "endpoint": endpoint,
                "group_name": group_name,
                "enabled": True,
                "core_available": True,
                "status": "degraded",
                "current_node": None,
                "candidate_nodes": candidate_count,
                "runtime_nodes": 0,
                "online_nodes": 0,
                "failed_nodes": 0,
                "average_delay": None,
                "best_node": None,
                "delay": None,
                "history": [],
                "error": "Mihomo runtime group is missing; reload runtime config",
                **stats_payload,
                **traffic_payload,
            }
        all_nodes = group.get("all") if isinstance(group.get("all"), list) else []
        delay = None
        if run_delay:
            try:
                delay = await mihomo_group_delay(session, group_name, url=proxy.health_check_url)
            except MihomoApiError:
                delay = None
        if run_delay:
            try:
                refreshed_proxies = await mihomo_proxy_map(session)
                refreshed_group = refreshed_proxies.get(group_name)
                if isinstance(refreshed_group, dict):
                    proxies = refreshed_proxies
                    group = refreshed_group
                    all_nodes = group.get("all") if isinstance(group.get("all"), list) else []
            except MihomoApiError:
                pass
        runtime_nodes = [str(item) for item in all_nodes if str(item).strip()]
        summary = _delay_summary(runtime_nodes, proxies)
        if delay is not None and summary["online_nodes"] == 0:
            current_node = str(group.get("now") or "")
            if current_node in runtime_nodes:
                summary["online_nodes"] = 1
                summary["failed_nodes"] = max(len(runtime_nodes) - 1, 0)
                summary["average_delay"] = delay
                summary["best_node"] = current_node
                summary["delay"] = delay
        runtime_status, runtime_error = _runtime_node_status(runtime_nodes, summary["online_nodes"])
        return {
            "proxy_id": proxy.id,
            "name": proxy.name,
            "endpoint": endpoint,
            "group_name": group_name,
            "enabled": True,
            "core_available": True,
            "status": runtime_status,
            "current_node": group.get("now"),
            "candidate_nodes": candidate_count,
            "runtime_nodes": len(runtime_nodes),
            "online_nodes": summary["online_nodes"],
            "failed_nodes": summary["failed_nodes"],
            "average_delay": summary["average_delay"],
            "best_node": summary["best_node"],
            "delay": delay or summary["delay"],
            "history": group.get("history") if isinstance(group.get("history"), list) else [],
            "error": runtime_error,
            **stats_payload,
            **traffic_payload,
        }
    except MihomoApiError as exc:
        return {
            "proxy_id": proxy.id,
            "name": proxy.name,
            "endpoint": endpoint,
            "group_name": group_name,
            "enabled": True,
            "core_available": True,
            "status": "degraded",
            "current_node": None,
            "candidate_nodes": candidate_count,
            "runtime_nodes": 0,
            "online_nodes": 0,
            "failed_nodes": 0,
            "average_delay": None,
            "best_node": None,
            "delay": None,
            "history": [],
            "error": str(exc),
            **stats_payload,
            **traffic_payload,
        }


async def check_smart_proxy_health(
    session: AsyncSession,
    proxy: SmartProxy,
    *,
    timeout_ms: int = 8000,
    include_scenario_checks: bool = True,
) -> dict[str, Any]:
    checked_at = now_china()
    group_name = runtime_group_name(proxy)
    result: dict[str, Any] = {
        "proxy_id": proxy.id,
        "name": proxy.name,
        "group_name": group_name,
        "checked_at": checked_at,
        "status": "unknown",
        "total_nodes": 0,
        "online_nodes": 0,
        "failed_nodes": 0,
        "average_delay": None,
        "best_node": None,
        "current_node": None,
        "nodes": [],
        "checks": [],
        "error": None,
    }
    if not proxy.enabled:
        result["status"] = "stopped"
        result["error"] = "Smart proxy is stopped"
        return result

    core = await mihomo_core_status(session)
    if not core["available"]:
        result["status"] = "core_unavailable"
        result["error"] = core["error"]
        return result

    try:
        proxies = await mihomo_proxy_map(session)
    except MihomoApiError as exc:
        result["status"] = "degraded"
        result["error"] = str(exc)
        return result

    group = proxies.get(group_name)
    if not isinstance(group, dict):
        result["status"] = "degraded"
        result["error"] = "Mihomo runtime group is missing; reload runtime config"
        return result

    runtime_nodes = [str(item) for item in group.get("all", []) if str(item).strip()]
    result["total_nodes"] = len(runtime_nodes)
    result["current_node"] = group.get("now")
    delays, delay_error = await mihomo_group_delay_map(
        session,
        group_name,
        url=proxy.health_check_url or TEST_URL,
        timeout_ms=timeout_ms,
    )
    aggregate_delay = delays.get(group_name)
    if aggregate_delay is not None and isinstance(result["current_node"], str):
        delays.setdefault(result["current_node"], aggregate_delay)

    node_ids = [node_id for node_id in (runtime_node_id(name) for name in runtime_nodes) if node_id is not None]
    nodes_by_id = {
        node.id: node
        for node in (await session.scalars(select(Node).where(Node.id.in_(node_ids)))).all()
        if node.id is not None
    }

    health_nodes: list[dict[str, Any]] = []
    online_delays: list[tuple[str, int]] = []
    for name in runtime_nodes:
        node_id = runtime_node_id(name)
        node = nodes_by_id.get(node_id) if node_id is not None else None
        delay = delays.get(name)
        online = delay is not None
        if node is not None:
            node.latency = delay if online else None
        if online:
            online_delays.append((name, delay))
        status_text = "online" if online else "failed"
        message = None if online else delay_error or "Delay check timed out"
        session.add(
            SmartProxyHealthLog(
                smart_proxy_id=proxy.id,
                node_id=node_id,
                node_name=node.name if node is not None else name,
                check_type="delay",
                status=status_text,
                latency=delay,
                message=message,
            )
        )
        health_nodes.append(
            {
                "node_id": node_id,
                "name": node.name if node is not None else name,
                "source": node.source_subscription_name if node is not None else None,
                "type": node.type if node is not None else None,
                "status": status_text,
                "delay": delay,
                "current": name == group.get("now"),
                "error": message,
            }
        )

    online_count = len(online_delays)
    failed_count = max(len(runtime_nodes) - online_count, 0)
    best = min(online_delays, key=lambda item: item[1]) if online_delays else None
    average = round(sum(delay for _, delay in online_delays) / online_count) if online_count else None
    health_status, default_health_error = _runtime_node_status(runtime_nodes, online_count)
    health_error = None if online_count else delay_error or default_health_error
    result.update(
        {
            "status": health_status,
            "online_nodes": online_count,
            "failed_nodes": failed_count,
            "average_delay": average,
            "best_node": best[0] if best else None,
            "nodes": health_nodes,
            "checks": [
                {
                    "check_type": "delay",
                    "status": "ok" if online_count else "failed",
                    "delay": best[1] if best else None,
                    "message": None if online_count else health_error or "All candidate nodes timed out",
                }
            ],
            "error": None if online_count else health_error or "All candidate nodes timed out",
        }
    )

    listener_status, listener_delay, listener_error = await smart_proxy_listener_probe(session, proxy, timeout_ms=timeout_ms)
    result["checks"].append(
        {
            "check_type": "listener",
            "status": listener_status,
            "delay": listener_delay,
            "message": listener_error,
        }
    )
    session.add(
        SmartProxyHealthLog(
            smart_proxy_id=proxy.id,
            node_id=None,
            node_name=None,
            check_type="listener",
            status=listener_status,
            latency=listener_delay,
            message=listener_error,
        )
    )
    if listener_status != "ok":
        result["status"] = "proxy_unavailable"
        result["error"] = listener_error or "Mihomo listener is unavailable"

    host_bind_check = _smart_proxy_bind_check()
    result["checks"].append(host_bind_check)
    session.add(
        SmartProxyHealthLog(
            smart_proxy_id=proxy.id,
            node_id=None,
            node_name=None,
            check_type=str(host_bind_check["check_type"]),
            status=str(host_bind_check["status"]),
            latency=None,
            message=str(host_bind_check["message"]) if host_bind_check.get("message") else None,
        )
    )

    if include_scenario_checks and proxy.scenario in SCENARIO_CHECKS:
        check_type, check_url = SCENARIO_CHECKS[proxy.scenario]
        scenario_delays, scenario_error = await mihomo_group_delay_map(
            session,
            group_name,
            url=check_url,
            timeout_ms=timeout_ms,
        )
        scenario_values = list(scenario_delays.values())
        scenario_delay = min(scenario_values) if scenario_values else None
        scenario_status = "ok" if scenario_delay is not None else "failed"
        result["checks"].append(
            {
                "check_type": check_type,
                "status": scenario_status,
                "delay": scenario_delay,
                "message": None if scenario_delay is not None else scenario_error or "Scenario check timed out",
            }
        )
        session.add(
            SmartProxyHealthLog(
                smart_proxy_id=proxy.id,
                node_id=None,
                node_name=None,
                check_type=check_type,
                status=scenario_status,
                latency=scenario_delay,
                message=None if scenario_delay is not None else scenario_error or "Scenario check timed out",
            )
        )

    proxy.status = str(result["status"])
    proxy.last_error = str(result["error"]) if result["error"] else None
    changed = add_smart_proxy_switch_log(session, proxy, result.get("current_node"), reason="健康检测发现当前节点变化")
    await prune_smart_proxy_health_logs(session, proxy.id)
    await session.commit()
    if changed:
        await apply_stability_priority_runtime(session, [proxy])
    return result


async def prune_smart_proxy_health_logs(session: AsyncSession, proxy_id: int, *, keep: int = 1000) -> None:
    ids = list(
        (
            await session.scalars(
                select(SmartProxyHealthLog.id)
                .where(SmartProxyHealthLog.smart_proxy_id == proxy_id)
                .order_by(SmartProxyHealthLog.id.desc())
                .offset(keep)
            )
        ).all()
    )
    if ids:
        await session.execute(delete(SmartProxyHealthLog).where(SmartProxyHealthLog.id.in_(ids)))


async def refresh_smart_proxy_statuses(session: AsyncSession) -> dict[str, Any]:
    proxies = list((await session.scalars(select(SmartProxy).order_by(SmartProxy.id.asc()))).all())
    stable_changed: list[SmartProxy] = []
    status_changes = 0
    current_node_changes = 0
    for proxy in proxies:
        previous_status = proxy.status
        previous_error = proxy.last_error
        status = await smart_proxy_runtime_status(session, proxy)
        proxy.status = status["status"]
        proxy.last_error = status["error"]
        if previous_status != proxy.status or previous_error != proxy.last_error:
            status_changes += 1
        changed = add_smart_proxy_switch_log(session, proxy, status.get("current_node"), reason="运行状态监控发现当前节点变化")
        if changed:
            current_node_changes += 1
        if changed and smart_proxy_stability_priority_enabled(proxy):
            stable_changed.append(proxy)
    await session.commit()
    if stable_changed:
        await apply_stability_priority_runtime(session, stable_changed)
    access_result: dict[str, Any] = {}
    try:
        access_result = await enforce_smart_proxy_access(session)
    except MihomoApiError:
        pass
    return {
        "proxies": len(proxies),
        "status_changes": status_changes,
        "current_node_changes": current_node_changes,
        "closed_connections": int(access_result.get("closed_connections") or 0),
    }
