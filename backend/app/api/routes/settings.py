from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.cache import get_redis
from app.models.system_setting import SystemSetting
from app.schemas.common import HealthStatus
from app.schemas.settings import SettingBulkUpdate, SettingRead
from app.services.audit import write_audit
from app.services.settings import get_subconverter_url
from app.services.subconverter import SubconverterClient


router = APIRouter()
SMART_PROXY_SETTING_PREFIXES = ("smart_proxy_", "mihomo_")
SETTING_SCOPES = {
    "system": {"redis_url", "subconverter_url", "acl4ssr_config_url"},
    "subscription": {"subscription_token", "cache_ttl_seconds", "traffic_poll_interval_minutes"},
    "node": {"node_filter_patterns", "node_pool_sync_interval_minutes"},
}
SETTING_LABELS = {
    "redis_url": "Redis 地址",
    "redis_password": "Redis 密码",
    "subconverter_url": "Subconverter 地址",
    "acl4ssr_config_url": "ACL4SSR 远程规则地址",
    "subscription_token": "订阅访问 Token",
    "cache_ttl_seconds": "缓存有效期",
    "node_filter_patterns": "节点过滤通配符",
    "node_pool_sync_interval_minutes": "节点池同步频率",
    "traffic_poll_interval_minutes": "流量刷新频率",
}


@router.get("", response_model=list[SettingRead])
async def list_settings(
    session: SessionDep,
    current_user: CurrentUser,
    scope: str | None = Query(default=None),
) -> list[SettingRead]:
    scope_keys = None
    if scope:
        scope_keys = SETTING_SCOPES.get(scope)
        if scope_keys is None:
            raise HTTPException(status_code=400, detail="Unknown settings scope")
    items = (await session.scalars(select(SystemSetting).order_by(SystemSetting.key.asc()))).all()
    safe_items = []
    for item in items:
        if item.key.startswith(SMART_PROXY_SETTING_PREFIXES):
            continue
        if scope_keys is not None and item.key not in scope_keys:
            continue
        data = SettingRead.model_validate(item)
        if item.secret and item.value:
            data.value = "********"
        safe_items.append(data)
    return safe_items


@router.put("", response_model=list[SettingRead])
async def update_settings(
    payload: SettingBulkUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[SettingRead]:
    changed_keys: list[str] = []
    for key, value in payload.settings.items():
        item = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if item is None:
            item = SystemSetting(key=key, value=value, secret="token" in key.lower())
            session.add(item)
            changed_keys.append(key)
        elif value != "********":
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
    return await list_settings(session, current_user)


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
