import logging
from asyncio import TimeoutError as AsyncTimeoutError

import aiohttp
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.cache import cache_delete_prefixes, get_redis
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.system_setting import SystemSetting
from app.schemas.common import HealthStatus
from app.schemas.settings import SettingBulkUpdate, SettingRead
from app.services.audit import write_audit
from app.services.history_cleanup import cleanup_history_data
from app.services.node_pool import sync_node_pool_background
from app.services.settings import (
    DEFAULT_HISTORY_CLEANUP_RETENTION_DAYS,
    HISTORY_CLEANUP_RETENTION_DAYS_KEY,
    HISTORY_RETENTION_ANT_PROXY_TRAFFIC_DAYS_KEY,
    HISTORY_RETENTION_AUDIT_LOG_DAYS_KEY,
    HISTORY_RETENTION_NODE_SNAPSHOT_DAYS_KEY,
    HISTORY_RETENTION_SETTING_KEYS,
    HISTORY_RETENTION_SMART_PROXY_HEALTH_LOG_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_STABILITY_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_SWITCH_LOG_DAYS_KEY,
    HISTORY_RETENTION_SMART_PROXY_TRAFFIC_DAYS_KEY,
    HISTORY_RETENTION_SUBSCRIPTION_TRAFFIC_DAYS_KEY,
    get_subconverter_url,
)
from app.services.smart_proxy import refresh_smart_proxy_statuses_if_due
from app.services.subconverter import SubconverterClient


router = APIRouter()
logger = logging.getLogger(__name__)
SMART_PROXY_SETTING_PREFIXES = ("smart_proxy_", "mihomo_")
HIDDEN_SETTING_KEYS = {"redis_url", "public_base_url", HISTORY_CLEANUP_RETENTION_DAYS_KEY}
DEVELOPMENT_READ_ONLY_SETTING_KEYS = {"subconverter_url", "mihomo_api_url", "mihomo_api_secret"}
SETTING_SCOPES = {
    "system": (
        "subscription_public_base_url",
        "proxy_public_base_url",
        "subconverter_url",
        "mihomo_api_url",
        "mihomo_api_secret",
        "acl4ssr_config_url",
        HISTORY_RETENTION_SMART_PROXY_TRAFFIC_DAYS_KEY,
        HISTORY_RETENTION_ANT_PROXY_TRAFFIC_DAYS_KEY,
        HISTORY_RETENTION_AUDIT_LOG_DAYS_KEY,
        HISTORY_RETENTION_SUBSCRIPTION_TRAFFIC_DAYS_KEY,
        HISTORY_RETENTION_SMART_PROXY_STABILITY_DAYS_KEY,
        HISTORY_RETENTION_SMART_PROXY_HEALTH_LOG_DAYS_KEY,
        HISTORY_RETENTION_SMART_PROXY_SWITCH_LOG_DAYS_KEY,
        HISTORY_RETENTION_NODE_SNAPSHOT_DAYS_KEY,
    ),
    "subscription": ("subscription_token", "cache_ttl_seconds", "traffic_poll_interval_minutes"),
    "node_pool": ("node_filter_patterns",),
    "node": ("node_filter_patterns",),
}
SETTING_SCOPE_KEYS = {scope: set(keys) for scope, keys in SETTING_SCOPES.items()}
SETTING_ORDER: dict[str, int] = {}
for keys in SETTING_SCOPES.values():
    for key in keys:
        SETTING_ORDER.setdefault(key, len(SETTING_ORDER))
SETTING_LABELS = {
    "redis_url": "Redis 地址",
    "redis_password": "Redis 密码",
    "subscription_public_base_url": "订阅公开访问地址",
    "proxy_public_base_url": "代理公开访问地址",
    "subconverter_url": "Subconverter 地址",
    "mihomo_api_url": "Mihomo API 地址",
    "mihomo_api_secret": "Mihomo API 密钥",
    "acl4ssr_config_url": "ACL4SSR 远程规则地址",
    "subscription_token": "订阅访问 Token",
    "cache_ttl_seconds": "缓存有效期",
    "node_filter_patterns": "节点过滤通配符",
    "traffic_poll_interval_minutes": "流量刷新频率",
    HISTORY_CLEANUP_RETENTION_DAYS_KEY: "历史数据保留天数",
    HISTORY_RETENTION_SMART_PROXY_TRAFFIC_DAYS_KEY: "智能代理流量保留天数",
    HISTORY_RETENTION_ANT_PROXY_TRAFFIC_DAYS_KEY: "蚂蚁流量保留天数",
    HISTORY_RETENTION_AUDIT_LOG_DAYS_KEY: "日志中心保留天数",
    HISTORY_RETENTION_SUBSCRIPTION_TRAFFIC_DAYS_KEY: "订阅流量快照保留天数",
    HISTORY_RETENTION_SMART_PROXY_STABILITY_DAYS_KEY: "智能代理稳定性保留天数",
    HISTORY_RETENTION_SMART_PROXY_HEALTH_LOG_DAYS_KEY: "健康检测日志保留天数",
    HISTORY_RETENTION_SMART_PROXY_SWITCH_LOG_DAYS_KEY: "节点切换历史保留天数",
    HISTORY_RETENTION_NODE_SNAPSHOT_DAYS_KEY: "节点转换快照保留天数",
}
SECRET_KEYWORDS = ("password", "secret", "token")


def _is_development() -> bool:
    return get_settings().APP_ENV == "development"


def _read_only_setting_keys() -> set[str]:
    return DEVELOPMENT_READ_ONLY_SETTING_KEYS if _is_development() else set()


def _is_secret_setting(key: str) -> bool:
    lowered = key.lower()
    return any(keyword in lowered for keyword in SECRET_KEYWORDS)


def _effective_setting_value(key: str, item: SystemSetting | None) -> str | None:
    settings = get_settings()
    if _is_development():
        if key == "subconverter_url":
            return settings.subconverter_base_url
        if key == "mihomo_api_url":
            return settings.MIHOMO_API_URL.rstrip("/")
        if key == "mihomo_api_secret":
            return settings.MIHOMO_API_SECRET
    return item.value if item is not None else None


def _display_value(key: str, item: SystemSetting) -> str | None:
    value = _effective_setting_value(key, item)
    if (item.secret or _is_secret_setting(key)) and value:
        return "********"
    return value


def _submitted_value(payload: SettingBulkUpdate, key: str, current: str | None) -> str | None:
    if key not in payload.settings:
        return current
    value = payload.settings[key]
    if value == "********":
        return current
    return value


async def _assert_subconverter_available(base_url: str) -> None:
    if not await SubconverterClient(base_url).health():
        raise HTTPException(status_code=400, detail=f"Subconverter 服务地址不可用：{base_url}")


async def _assert_mihomo_api_available(api_url: str, secret: str | None) -> None:
    url = api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
            async with http.get(f"{url}/version") as response:
                body = await response.text()
                if response.status >= 400:
                    raise HTTPException(status_code=400, detail=f"Mihomo API 地址不可用：HTTP {response.status} {body[:200]}")
    except HTTPException:
        raise
    except (aiohttp.ClientError, AsyncTimeoutError) as exc:
        raise HTTPException(status_code=400, detail=f"Mihomo API 地址不可用：{exc}") from exc


def _assert_read_only_settings_unchanged(
    payload: SettingBulkUpdate,
    items_by_key: dict[str, SystemSetting],
) -> None:
    for key in set(payload.settings) & _read_only_setting_keys():
        value = payload.settings[key]
        if value == "********":
            continue
        effective_value = _effective_setting_value(key, items_by_key.get(key))
        if (value or "") != (effective_value or ""):
            label = SETTING_LABELS.get(key, key)
            raise HTTPException(status_code=400, detail=f"{label} 在本地开发环境中由环境变量控制，不能在系统设置中修改")


def _normalize_history_retention_settings(payload: SettingBulkUpdate) -> None:
    for key in set(payload.settings) & set(HISTORY_RETENTION_SETTING_KEYS):
        raw_value = payload.settings[key]
        text = str(raw_value or "").strip()
        if not text:
            payload.settings[key] = str(DEFAULT_HISTORY_CLEANUP_RETENTION_DAYS)
            continue
        try:
            days = int(text)
        except ValueError as exc:
            label = SETTING_LABELS.get(key, key)
            raise HTTPException(status_code=400, detail=f"{label}必须是整数") from exc
        if days < 0 or days > 3650:
            label = SETTING_LABELS.get(key, key)
            raise HTTPException(status_code=400, detail=f"{label}必须在 0 到 3650 天之间")
        payload.settings[key] = str(days)


async def _refresh_smart_proxy_statuses_background(actor: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            summary = await refresh_smart_proxy_statuses_if_due(session, force=True)
            await write_audit(
                session,
                actor=actor,
                action="monitor",
                resource="smart_proxy",
                detail=(
                    "Mihomo API 配置变更后刷新智能代理运行状态完成："
                    f"状态变化 {summary.get('status_changes', 0)} 个，"
                    f"当前节点变化 {summary.get('current_node_changes', 0)} 个，"
                    f"关闭未授权连接 {summary.get('closed_connections', 0)} 个。"
                ),
            )
            await session.commit()
        except Exception as exc:
            logger.info("Smart proxy status refresh after settings change skipped: %s", exc)


async def _cleanup_history_background(actor: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await cleanup_history_data(session, actor=actor, write_log=True)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.info("History cleanup after settings change skipped: %s", exc)


async def _validate_connection_changes(
    payload: SettingBulkUpdate,
    items_by_key: dict[str, SystemSetting],
) -> tuple[bool, bool]:
    settings = get_settings()
    read_only_keys = _read_only_setting_keys()
    current_subconverter = (items_by_key.get("subconverter_url").value if items_by_key.get("subconverter_url") else None) or settings.subconverter_base_url
    next_subconverter = (_submitted_value(payload, "subconverter_url", current_subconverter) or settings.subconverter_base_url).rstrip("/")
    subconverter_changed = (
        "subconverter_url" in payload.settings
        and "subconverter_url" not in read_only_keys
        and next_subconverter != current_subconverter.rstrip("/")
    )
    if subconverter_changed:
        await _assert_subconverter_available(next_subconverter)

    current_mihomo_url = (items_by_key.get("mihomo_api_url").value if items_by_key.get("mihomo_api_url") else None) or settings.MIHOMO_API_URL
    current_mihomo_secret = (
        (items_by_key.get("mihomo_api_secret").value if items_by_key.get("mihomo_api_secret") else None)
        or settings.MIHOMO_API_SECRET
    )
    next_mihomo_url = (_submitted_value(payload, "mihomo_api_url", current_mihomo_url) or settings.MIHOMO_API_URL).rstrip("/")
    next_mihomo_secret = _submitted_value(payload, "mihomo_api_secret", current_mihomo_secret) or ""
    mihomo_url_changed = (
        "mihomo_api_url" in payload.settings
        and "mihomo_api_url" not in read_only_keys
        and next_mihomo_url != str(current_mihomo_url).rstrip("/")
    )
    mihomo_secret_changed = (
        "mihomo_api_secret" in payload.settings
        and "mihomo_api_secret" not in read_only_keys
        and next_mihomo_secret != (current_mihomo_secret or "")
    )
    mihomo_changed = mihomo_url_changed or mihomo_secret_changed
    if mihomo_changed:
        await _assert_mihomo_api_available(next_mihomo_url, next_mihomo_secret)
    return subconverter_changed, mihomo_changed


async def _setting_reads(session: SessionDep, scope: str | None = None) -> list[SettingRead]:
    scope_keys = None
    scope_order: dict[str, int] | None = None
    if scope:
        scoped_keys = SETTING_SCOPES.get(scope)
        scope_keys = SETTING_SCOPE_KEYS.get(scope)
        if scope_keys is None:
            raise HTTPException(status_code=400, detail="Unknown settings scope")
        scope_order = {key: index for index, key in enumerate(scoped_keys or ())}
    items = (await session.scalars(select(SystemSetting).order_by(SystemSetting.key.asc()))).all()
    safe_items = []
    for item in items:
        if item.key in HIDDEN_SETTING_KEYS:
            continue
        if item.key.startswith(SMART_PROXY_SETTING_PREFIXES) and item.key not in SETTING_ORDER:
            continue
        if scope_keys is not None and item.key not in scope_keys:
            continue
        data = SettingRead.model_validate(item)
        data.secret = item.secret or _is_secret_setting(item.key)
        data.value = _display_value(item.key, item)
        data.read_only = item.key in _read_only_setting_keys()
        safe_items.append(data)
    order_map = scope_order or SETTING_ORDER
    safe_items.sort(key=lambda item: (order_map.get(item.key, len(order_map)), item.key))
    return safe_items


@router.get("", response_model=list[SettingRead])
async def list_settings(
    session: SessionDep,
    current_user: CurrentUser,
    scope: str | None = Query(default=None),
) -> list[SettingRead]:
    return await _setting_reads(session, scope)


@router.put("", response_model=list[SettingRead])
async def update_settings(
    payload: SettingBulkUpdate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[SettingRead]:
    _normalize_history_retention_settings(payload)
    keys = set(payload.settings)
    keys.update({"subconverter_url", "mihomo_api_url", "mihomo_api_secret"})
    items = (await session.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys)))).all()
    items_by_key = {item.key: item for item in items}
    _assert_read_only_settings_unchanged(payload, items_by_key)
    subconverter_changed, mihomo_changed = await _validate_connection_changes(payload, items_by_key)

    changed_keys: list[str] = []
    read_only_keys = _read_only_setting_keys()
    for key, value in payload.settings.items():
        if key in read_only_keys:
            continue
        item = items_by_key.get(key)
        if item is None:
            item = SystemSetting(key=key, value=value, secret=_is_secret_setting(key))
            session.add(item)
            changed_keys.append(key)
            items_by_key[key] = item
        elif value != "********" and item.value != value:
            item.value = value
            changed_keys.append(key)
    changed = "、".join(SETTING_LABELS.get(key, key) for key in changed_keys) if changed_keys else "无字段变化"
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="settings",
        detail=f"更新系统配置，变更字段：{changed}。",
    )
    await session.commit()
    if subconverter_changed:
        await cache_delete_prefixes("sub:final:", "sub:nodes:")
        background_tasks.add_task(
            sync_node_pool_background,
            emoji=True,
            actor=current_user.username,
            reason="Subconverter 服务地址变更后同步",
        )
    if mihomo_changed:
        background_tasks.add_task(_refresh_smart_proxy_statuses_background, current_user.username)
    if "node_filter_patterns" in changed_keys:
        background_tasks.add_task(
            sync_node_pool_background,
            emoji=True,
            actor=current_user.username,
            reason="节点过滤配置变更后同步",
        )
    if set(changed_keys) & set(HISTORY_RETENTION_SETTING_KEYS):
        background_tasks.add_task(_cleanup_history_background, current_user.username)
    return await _setting_reads(session)


@router.get("/health", response_model=HealthStatus)
async def health(session: SessionDep, current_user: CurrentUser) -> HealthStatus:
    client = SubconverterClient(await get_subconverter_url(session))
    subconverter_status = "ok" if await client.health() else "unavailable"
    try:
        await get_redis().ping()
        redis_status = "ok"
    except Exception:
        redis_status = "unavailable"
    return HealthStatus(status="ok", redis=redis_status, subconverter=subconverter_status)
