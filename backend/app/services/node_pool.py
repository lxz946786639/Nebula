from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.locks import exclusive_lock
from app.core.timezone import now_china
from app.models.node import Node
from app.models.subscription import Subscription
from app.services.audit import write_audit
from app.services.node_processor import detect_country, extract_clash_proxies, node_identity
from app.services.settings import get_node_filter_patterns, get_subconverter_url
from app.services.subconverter import ConvertRequest, SubconverterClient, SubconverterError
from app.utils.network import UrlValidationError, validate_subscription_url


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NodePoolSyncResult:
    total_nodes: int = 0
    cleared_nodes: int = 0
    synced_nodes: int = 0
    filtered_nodes: int = 0
    disabled_nodes: int = 0
    refreshed_subscriptions: int = 0
    failed_subscriptions: int = 0
    errors: list[str] = field(default_factory=list)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _unique_tags(*groups: list[str] | tuple[str | None, ...]) -> list[str]:
    tags: list[str] = []
    for group in groups:
        for item in group:
            text = _text(item)
            if text and text not in tags:
                tags.append(text)
    return tags


def _effective_pattern(pattern: str) -> str:
    return pattern if any(char in pattern for char in "*?[") else f"*{pattern}*"


def _is_filtered_node(raw: dict[str, Any], patterns: list[str]) -> bool:
    if not patterns:
        return False
    name = str(raw.get("name") or "").casefold()
    return any(fnmatchcase(name, _effective_pattern(pattern).casefold()) for pattern in patterns)


def _sync_scope_text(*, group: str | None = None, subscription_id: int | None = None) -> str:
    if subscription_id is not None:
        return f"订阅 ID {subscription_id}"
    if group:
        return f"分组「{group}」"
    return "全部订阅"


def node_pool_sync_audit_detail(
    result: NodePoolSyncResult,
    *,
    group: str | None = None,
    subscription_id: int | None = None,
    reason: str | None = None,
) -> str:
    status = "部分失败" if result.failed_subscriptions else "完成"
    scope = _sync_scope_text(group=group, subscription_id=subscription_id)
    reason_text = f"（{reason}）" if reason else ""
    parts = [
        f"节点池同步{status}{reason_text}：范围 {scope}",
        f"当前节点 {result.total_nodes} 个",
        f"清理旧节点 {result.cleared_nodes} 个",
        f"写入 {result.synced_nodes} 个",
        f"过滤 {result.filtered_nodes} 个",
        f"刷新订阅 {result.refreshed_subscriptions} 个",
        f"失败订阅 {result.failed_subscriptions} 个",
    ]
    if result.disabled_nodes:
        parts.append(f"跳过停用订阅 {result.disabled_nodes} 个")
    detail = "，".join(parts) + "。"
    if result.errors:
        detail += f"异常：{'；'.join(result.errors[:3])}。"
    return detail


async def _write_node_pool_sync_audit(
    session: AsyncSession,
    result: NodePoolSyncResult,
    *,
    actor: str,
    group: str | None = None,
    subscription_id: int | None = None,
    reason: str | None = None,
) -> None:
    await write_audit(
        session,
        actor=actor,
        action="sync",
        resource="node_pool",
        detail=node_pool_sync_audit_detail(result, group=group, subscription_id=subscription_id, reason=reason),
    )


def _node_tags(subscription: Subscription, raw: dict[str, Any], country_code: str | None) -> list[str]:
    return _unique_tags(
        subscription.tags or [],
        (
            subscription.group_name,
            _text(raw.get("type")),
            _text(raw.get("network")),
            country_code,
        ),
    )


def _normalized_node_payload(
    *,
    raw: dict[str, Any],
    subscription: Subscription,
    identity: str,
    now: datetime,
) -> dict[str, Any]:
    name = _text(raw.get("name")) or f"{subscription.name}-{identity[:8]}"
    server = _text(raw.get("server"))
    country, country_code = detect_country(name, server)
    return {
        "identity": identity,
        "name": name,
        "server": server,
        "port": _text(raw.get("port")),
        "type": _text(raw.get("type")),
        "uuid": _text(raw.get("uuid")),
        "password": _text(raw.get("password")),
        "tls": _truthy(raw.get("tls")) or bool(raw.get("sni")),
        "network": _text(raw.get("network")),
        "country": country,
        "city": None,
        "country_code": country_code,
        "tags": _node_tags(subscription, raw, country_code),
        "latency": None,
        "source_subscription_id": subscription.id,
        "source_subscription_name": subscription.name,
        "source_group": subscription.group_name,
        "raw": deepcopy(raw),
        "last_seen_at": now,
    }


async def _enabled_subscriptions(
    session: AsyncSession,
    *,
    group: str | None = None,
    subscription_id: int | None = None,
) -> list[Subscription]:
    stmt = select(Subscription).where(Subscription.enabled.is_(True))
    if group:
        stmt = stmt.where(Subscription.group_name == group)
    if subscription_id is not None:
        stmt = stmt.where(Subscription.id == subscription_id)
    stmt = stmt.order_by(Subscription.priority.asc(), Subscription.id.asc())
    return list((await session.scalars(stmt)).all())


async def _clear_nodes(
    session: AsyncSession,
    *,
    group: str | None = None,
    subscription_id: int | None = None,
    keep_identities: set[str] | None = None,
) -> int:
    stmt = delete(Node)
    if subscription_id is not None:
        stmt = stmt.where(Node.source_subscription_id == subscription_id)
    elif group:
        stmt = stmt.where(Node.source_group == group)
    if keep_identities:
        stmt = stmt.where(Node.identity.notin_(keep_identities))
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def _replace_nodes(
    session: AsyncSession,
    payloads: list[dict[str, Any]],
    *,
    group: str | None = None,
    subscription_id: int | None = None,
) -> int:
    payload_identities = {str(payload["identity"]) for payload in payloads}
    existing_by_identity: dict[str, Node] = {}
    if payload_identities:
        existing_nodes = await session.scalars(select(Node).where(Node.identity.in_(payload_identities)))
        existing_by_identity = {node.identity: node for node in existing_nodes.all()}

    for payload in payloads:
        node = existing_by_identity.get(str(payload["identity"]))
        if node is None:
            session.add(Node(**payload, enabled=True))
            continue
        for key, value in payload.items():
            setattr(node, key, value)
        node.enabled = True
    cleared_nodes = await _clear_nodes(
        session,
        group=group,
        subscription_id=subscription_id,
        keep_identities=payload_identities,
    )
    return cleared_nodes


async def sync_node_pool(
    session: AsyncSession,
    *,
    group: str | None = None,
    subscription_id: int | None = None,
    emoji: bool = True,
    audit_actor: str = "system",
    audit_reason: str | None = None,
) -> NodePoolSyncResult:
    async with exclusive_lock("node_pool"):
        return await _sync_node_pool_unlocked(
            session,
            group=group,
            subscription_id=subscription_id,
            emoji=emoji,
            audit_actor=audit_actor,
            audit_reason=audit_reason,
        )


async def _sync_node_pool_unlocked(
    session: AsyncSession,
    *,
    group: str | None = None,
    subscription_id: int | None = None,
    emoji: bool = True,
    audit_actor: str = "system",
    audit_reason: str | None = None,
) -> NodePoolSyncResult:
    subscriptions = await _enabled_subscriptions(session, group=group, subscription_id=subscription_id)
    result = NodePoolSyncResult()
    if not subscriptions:
        result.cleared_nodes = await _clear_nodes(session, group=group, subscription_id=subscription_id)
        result.total_nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
        await _write_node_pool_sync_audit(
            session,
            result,
            actor=audit_actor,
            group=group,
            subscription_id=subscription_id,
            reason=audit_reason or "没有可用订阅",
        )
        await session.commit()
        return result

    client = SubconverterClient(await get_subconverter_url(session))
    filter_patterns = await get_node_filter_patterns(session)
    now = now_china()
    seen_identities: set[str] = set()
    staged_payloads: list[dict[str, Any]] = []

    for subscription in subscriptions:
        try:
            await validate_subscription_url(subscription.url)
            proxies: list[dict[str, Any]] = []
            convert_error: SubconverterError | None = None
            try:
                converted = await client.convert(
                    ConvertRequest(target="clash", urls=[subscription.url], config_url=None, emoji=emoji)
                )
                proxies = extract_clash_proxies(converted)
            except SubconverterError as exc:
                # subconverter 抓取失败（多为机场 WAF 拦截）时，先记下来继续尝试原文抓取。
                convert_error = exc
            # 原始订阅解析兜底：tindy2013/subconverter（C++ v0.9）无法解析 Clash YAML
            # 中的 vless 等节点类型会直接丢弃，这里用同一组 UA 回退抓取订阅原文补全
            # 缺失节点；subconverter 整体失败时原文抓取是唯一来源（非 Clash 格式订阅
            # 没有 proxies 字段，天然不产生影响）。
            try:
                raw_text = await client.fetch_raw(subscription.url)
                raw_proxies = extract_clash_proxies(raw_text)
            except SubconverterError as exc:
                logger.info("订阅 %s 原文抓取失败：%s", subscription.name, exc)
                raw_proxies = []
            known_identities = {node_identity(item) for item in proxies}
            for item in raw_proxies:
                identity = node_identity(item)
                if identity not in known_identities:
                    proxies.append(item)
                    known_identities.add(identity)
            if not proxies and convert_error is not None:
                raise convert_error
            for raw in proxies:
                if _is_filtered_node(raw, filter_patterns):
                    result.filtered_nodes += 1
                    continue
                identity = node_identity(raw)
                if not raw.get("server") or not raw.get("port") or identity in seen_identities:
                    continue
                payload = _normalized_node_payload(raw=raw, subscription=subscription, identity=identity, now=now)
                staged_payloads.append(payload)
                seen_identities.add(identity)

            subscription.last_status = "ok"
            subscription.last_error = None
            subscription.last_updated_at = now
            result.refreshed_subscriptions += 1
        except (UrlValidationError, SubconverterError) as exc:
            subscription.last_status = "failed"
            subscription.last_error = str(exc)
            subscription.last_updated_at = now
            result.failed_subscriptions += 1
            result.errors.append(f"{subscription.name}: {exc}")

    if result.failed_subscriptions:
        result.total_nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
        await _write_node_pool_sync_audit(
            session,
            result,
            actor=audit_actor,
            group=group,
            subscription_id=subscription_id,
            reason=audit_reason,
        )
        await session.commit()
        return result

    result.cleared_nodes = await _replace_nodes(
        session,
        staged_payloads,
        group=group,
        subscription_id=subscription_id,
    )
    result.synced_nodes = len(staged_payloads)
    result.total_nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
    await _write_node_pool_sync_audit(
        session,
        result,
        actor=audit_actor,
        group=group,
        subscription_id=subscription_id,
        reason=audit_reason,
    )
    await session.commit()
    return result


async def sync_node_pool_background(
    *,
    group: str | None = None,
    subscription_id: int | None = None,
    emoji: bool = True,
    actor: str = "system",
    reason: str | None = "后台同步",
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await sync_node_pool(
                session,
                group=group,
                subscription_id=subscription_id,
                emoji=emoji,
                audit_actor=actor,
                audit_reason=reason,
            )
        except Exception as exc:
            logger.info("Background node pool sync skipped: %s", exc)


async def enabled_node_count(session: AsyncSession, *, group: str | None = None) -> int:
    stmt = select(func.count()).select_from(Node).where(Node.enabled.is_(True))
    if group:
        stmt = stmt.where(Node.source_group == group)
    return await session.scalar(stmt) or 0
