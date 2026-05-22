import logging
from datetime import datetime, timedelta
from ipaddress import ip_network

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.timezone import as_china, now_china
from app.models.node import Node
from app.models.smart_proxy import SmartProxy
from app.models.smart_proxy_health import SmartProxyHealthLog
from app.models.smart_proxy_switch import SmartProxySwitchLog
from app.models.subscription import Subscription
from app.models.system_setting import SystemSetting
from app.schemas.common import Message
from app.schemas.smart_proxy import (
    MihomoCoreStatus,
    SmartProxyAccessEnforceResult,
    SmartProxyConfig,
    SmartProxyConfigUpdate,
    SmartProxyCreate,
    SmartProxyGlobalConfig,
    SmartProxyGlobalConfigUpdate,
    SmartProxyHealthLogRead,
    SmartProxyHealthResult,
    SmartProxyMetadata,
    SmartProxyPreset,
    SmartProxyRead,
    SmartProxyRuntime,
    SmartProxyStatus,
    SmartProxySwitchLogRead,
    SmartProxyUpdate,
)
from app.services.audit import write_audit
from app.services.node_pool import sync_node_pool
from app.services.smart_proxy import (
    SmartProxyError,
    MihomoApiError,
    allocate_smart_proxy_port,
    apply_mihomo_runtime,
    apply_stability_priority_runtime,
    check_smart_proxy_health,
    enforce_smart_proxy_access,
    add_smart_proxy_switch_log,
    ensure_unique_port,
    mihomo_core_status,
    normalize_data_source,
    normalize_proxy_type,
    normalize_strategy,
    public_endpoint_for,
    smart_proxy_traffic_policy,
    smart_proxy_uses_global_policy,
    smart_proxy_monitor_state,
    smart_proxy_runtime_status,
    smart_proxy_candidate_count,
    write_mihomo_runtime_config,
)
from app.services.settings import (
    get_mihomo_core_config_path,
    get_mihomo_runtime_config_path,
    get_smart_proxy_auto_apply_interval_minutes,
    get_smart_proxy_monitor_interval_minutes,
    get_smart_proxy_port_range,
)


router = APIRouter()
logger = logging.getLogger(__name__)
GLOBAL_CONFIG_KEYS = {
    "smart_proxy_auto_apply_interval_minutes",
    "smart_proxy_monitor_interval_minutes",
    "mihomo_runtime_config_path",
    "mihomo_core_config_path",
    "smart_proxy_traffic_guard_enabled",
    "smart_proxy_min_remaining_mb",
    "smart_proxy_low_remaining_mb",
    "smart_proxy_expire_soon_days",
    "smart_proxy_exclude_unknown_traffic",
}
GLOBAL_CONFIG_LABELS = {
    "traffic_guard_enabled": "流量保护开关",
    "min_remaining_mb": "最低剩余流量",
    "low_remaining_mb": "低剩余流量阈值",
    "expire_soon_days": "临近到期天数",
    "exclude_unknown_traffic": "排除未知流量订阅",
    "smart_proxy_auto_apply_interval_minutes": "按需应用检查频率",
    "smart_proxy_monitor_interval_minutes": "运行状态监控频率",
    "mihomo_runtime_config_path": "运行时配置路径",
    "mihomo_core_config_path": "核心配置路径",
    "smart_proxy_traffic_guard_enabled": "流量保护开关",
    "smart_proxy_min_remaining_mb": "最低剩余流量",
    "smart_proxy_low_remaining_mb": "低剩余流量阈值",
    "smart_proxy_expire_soon_days": "临近到期天数",
    "smart_proxy_exclude_unknown_traffic": "排除未知流量订阅",
}
SMART_PROXY_PRESETS = [
    SmartProxyPreset(
        key="hk_stable",
        name="香港稳定线路",
        description="适合日常浏览、低延迟和通用代理。",
        proxy_type="mixed",
        strategy="stable",
        scenario="latency",
        source_mode="all",
        country_codes=["HK"],
        health_check_url="http://www.gstatic.com/generate_204",
    ),
    SmartProxyPreset(
        key="jp_ai",
        name="日本 ChatGPT 专线",
        description="优先日本节点，附加 AI 场景检测。",
        proxy_type="mixed",
        strategy="fallback",
        scenario="ai",
        source_mode="all",
        country_codes=["JP"],
        health_check_url="https://chat.openai.com/cdn-cgi/trace",
    ),
    SmartProxyPreset(
        key="us_ai",
        name="美国 ChatGPT 专线",
        description="优先美国节点，适合 OpenAI、Claude 等 AI 服务。",
        proxy_type="mixed",
        strategy="fallback",
        scenario="ai",
        source_mode="all",
        country_codes=["US"],
        health_check_url="https://chat.openai.com/cdn-cgi/trace",
    ),
    SmartProxyPreset(
        key="streaming",
        name="流媒体线路",
        description="适合 Netflix、Disney+ 等流媒体场景。",
        proxy_type="mixed",
        strategy="url-test",
        scenario="streaming",
        source_mode="all",
        tags=["streaming"],
        health_check_url="https://www.netflix.com/title/80018499",
        tolerance=80,
    ),
    SmartProxyPreset(
        key="load_balance",
        name="多节点负载均衡",
        description="适合批量请求或多设备共享，按一致性哈希分流。",
        proxy_type="mixed",
        strategy="load-balance",
        scenario="general",
        source_mode="all",
        health_check_url="http://www.gstatic.com/generate_204",
    ),
]
APPLY_STATUS_TOLERANCE = timedelta(seconds=2)


def _china(value: datetime | None) -> datetime | None:
    return as_china(value)


def _mark_config_changed(proxy: SmartProxy) -> None:
    proxy.config_updated_at = now_china()


async def _mark_all_configs_changed(session: SessionDep) -> None:
    now = now_china()
    proxies = list((await session.scalars(select(SmartProxy))).all())
    for proxy in proxies:
        proxy.config_updated_at = now


async def _ensure_unique_name(session: SessionDep, name: str, *, exclude_id: int | None = None) -> None:
    normalized = name.strip()
    stmt = select(SmartProxy).where(func.lower(SmartProxy.name) == normalized.lower())
    if exclude_id is not None:
        stmt = stmt.where(SmartProxy.id != exclude_id)
    existing = await session.scalar(stmt)
    if existing is not None:
        raise SmartProxyError(f"智能代理名称「{normalized}」已存在")


def _apply_status(proxy: SmartProxy) -> tuple[str, str | None]:
    if not proxy.enabled:
        return "disabled", "代理未启用，不会出现在 Mihomo 运行配置中。"

    config_updated_at = _china(proxy.config_updated_at) or _china(proxy.updated_at) or _china(proxy.created_at)
    last_applied_at = _china(proxy.last_applied_at)
    if last_applied_at is None:
        return "pending", "尚未应用到 Mihomo，请点击顶部“重新应用到 Mihomo”。"
    if config_updated_at and last_applied_at + APPLY_STATUS_TOLERANCE < config_updated_at:
        return "pending", "代理配置已变更，尚未重新应用到 Mihomo。"
    if proxy.status in {"degraded", "core_unavailable", "proxy_unavailable"} and proxy.last_error:
        return "failed", proxy.last_error
    return "applied", "当前配置已成功应用到 Mihomo。"


async def _read_proxy(
    session: SessionDep,
    proxy: SmartProxy,
    *,
    runtime_apply_error: str | None = None,
) -> SmartProxyRead:
    data = SmartProxyRead.model_validate(proxy)
    if proxy.strategy in {"select", "fallback"} and proxy.stability_priority:
        data.strategy = "stable"
    data.endpoint = await public_endpoint_for(session, proxy)
    data.candidate_nodes = await smart_proxy_candidate_count(session, proxy)
    data.runtime_apply_error = runtime_apply_error
    data.apply_status, data.apply_status_reason = _apply_status(proxy)
    return data


async def _ensure_node_pool_for_candidates(session: SessionDep, actor: str) -> None:
    smart_proxy_count = (
        await session.scalar(
            select(func.count())
            .select_from(SmartProxy)
            .where(SmartProxy.data_source != "ant")
        )
        or 0
    )
    if smart_proxy_count <= 0:
        return
    existing_nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
    if existing_nodes > 0:
        return
    enabled_subscriptions = (
        await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))) or 0
    )
    if enabled_subscriptions <= 0:
        return
    try:
        await sync_node_pool(
            session,
            emoji=True,
            audit_actor=actor,
            audit_reason="智能代理候选节点自动补齐",
        )
    except Exception as exc:
        logger.info("Smart proxy candidate node auto-sync skipped: %s", exc)


async def _apply_runtime_after_change(session: SessionDep) -> str | None:
    result = await apply_mihomo_runtime(session, reload_core=True)
    return result.error


def _runtime_response(result) -> SmartProxyRuntime:  # type: ignore[no-untyped-def]
    return SmartProxyRuntime(
        config_path=result.config_path,
        enabled_services=result.enabled_services,
        proxies=result.proxies,
        proxy_groups=result.proxy_groups,
        listeners=result.listeners,
        reloaded=result.reloaded,
        error=result.error,
        content=result.content,
    )


def _prepare_payload(data: dict) -> dict:
    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise SmartProxyError("请填写代理名称")
    if "data_source" in data and data["data_source"] is not None:
        data["data_source"] = normalize_data_source(str(data["data_source"]))
    if "source_mode" in data and data["source_mode"] is not None:
        data["source_mode"] = str(data["source_mode"] or "all").strip() or "all"
    if "proxy_type" in data and data["proxy_type"] is not None:
        data["proxy_type"] = normalize_proxy_type(str(data["proxy_type"]))
    if "strategy" in data and data["strategy"] is not None:
        data["strategy"] = normalize_strategy(str(data["strategy"]))
    if "stability_priority" in data and data["stability_priority"] is not None:
        data["stability_priority"] = bool(data["stability_priority"])
    if "country_codes" in data and data["country_codes"] is not None:
        data["country_codes"] = [str(item).upper() for item in data["country_codes"] if str(item).strip()]
    for key in ("subscription_ids", "node_ids", "strategy_node_ids"):
        if key in data and data[key] is not None:
            try:
                data[key] = [int(item) for item in data[key] if str(item).strip()]
            except ValueError as exc:
                raise SmartProxyError(f"Invalid {key} item") from exc
    for key in ("ant_node_ids", "ant_strategy_node_ids"):
        if key in data and data[key] is not None:
            data[key] = [str(item).strip() for item in data[key] if str(item).strip()]
    if "protocol_types" in data and data["protocol_types"] is not None:
        data["protocol_types"] = [str(item).lower() for item in data["protocol_types"] if str(item).strip()]
    if "access_token" in data and data["access_token"] is not None:
        token = str(data["access_token"]).strip()
        data["access_token"] = token or None
    if "ip_whitelist" in data and data["ip_whitelist"] is not None:
        normalized_whitelist: list[str] = []
        for item in data["ip_whitelist"]:
            value = str(item).strip()
            if not value:
                continue
            if value != "*":
                try:
                    ip_network(value, strict=False)
                except ValueError as exc:
                    raise SmartProxyError(f"Invalid IP whitelist item: {value}") from exc
            normalized_whitelist.append(value)
        data["ip_whitelist"] = normalized_whitelist
    if data.get("strategy") == "stable":
        data["stability_priority"] = True
    elif data.get("strategy") and data.get("strategy") not in {"select", "fallback"}:
        data["stability_priority"] = False
    if data.get("data_source") == "ant":
        data["subscription_ids"] = []
        data["node_ids"] = []
        data["strategy_node_ids"] = []
    elif data.get("data_source") == "subscription":
        if data.get("source_mode") in {"country", "tag"}:
            data["source_mode"] = "all"
        data["ant_node_ids"] = []
        data["ant_strategy_node_ids"] = []
    return data


def _validate_strategy_config(
    strategy: str,
    data_source: str,
    source_mode: str,
    node_ids: list[int] | None,
    strategy_node_ids: list[int] | None,
    ant_node_ids: list[str] | None,
    ant_strategy_node_ids: list[str] | None,
) -> None:
    if data_source == "ant":
        source_nodes = ant_node_ids or []
        strategy_nodes = ant_strategy_node_ids or []
    else:
        source_nodes = node_ids or []
        strategy_nodes = strategy_node_ids or []
    if source_mode == "manual" and not source_nodes:
        raise SmartProxyError("手动节点模式请至少选择一个节点")
    known_candidate_count = len(strategy_nodes) if strategy_nodes else (len(source_nodes) if source_mode == "manual" else None)
    if strategy == "relay" and strategy_nodes and len(strategy_nodes) < 2:
        raise SmartProxyError("链式代理请按顺序选择至少 2 个节点")
    if strategy == "round-robin" and strategy_nodes and len(strategy_nodes) < 2:
        raise SmartProxyError("轮询策略请至少选择 2 个策略节点")
    if strategy == "relay" and known_candidate_count is not None and known_candidate_count < 2:
        raise SmartProxyError("链式代理请至少使用 2 个候选节点")
    if strategy == "round-robin" and known_candidate_count is not None and known_candidate_count < 2:
        raise SmartProxyError("轮询策略请至少使用 2 个候选节点")


def _validate_source_config(
    data_source: str,
    source_mode: str,
    subscription_ids: list[int] | None,
    country_codes: list[str] | None,
    tags: list[str] | None,
    node_ids: list[int] | None,
    ant_node_ids: list[str] | None,
) -> None:
    del country_codes, tags
    if source_mode == "subscription" and data_source == "ant":
        raise SmartProxyError("蚂蚁节点暂不支持指定订阅来源")
    if source_mode == "manual" and data_source == "ant" and not (ant_node_ids or []):
        raise SmartProxyError("手动节点模式请至少选择一个蚂蚁节点")
    if data_source == "ant":
        return
    if source_mode == "manual" and data_source != "ant" and not (node_ids or []):
        raise SmartProxyError("手动节点模式请至少选择一个节点")
    if source_mode == "subscription" and data_source != "ant" and not (subscription_ids or []):
        raise SmartProxyError("指定订阅模式请至少选择一个订阅来源")


def _validate_proxy_strategy(proxy: SmartProxy) -> None:
    data_source = normalize_data_source(str(getattr(proxy, "data_source", "") or "subscription"))
    _validate_source_config(
        data_source,
        proxy.source_mode,
        proxy.subscription_ids,
        proxy.country_codes,
        proxy.tags,
        proxy.node_ids,
        proxy.ant_node_ids,
    )
    _validate_strategy_config(
        proxy.strategy,
        data_source,
        proxy.source_mode,
        proxy.node_ids,
        proxy.strategy_node_ids,
        proxy.ant_node_ids,
        proxy.ant_strategy_node_ids,
    )


async def _set_setting(session: SessionDep, key: str, value: str) -> None:
    item = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if item is None:
        item = SystemSetting(key=key, value=value, secret="secret" in key.lower())
        session.add(item)
    elif value != "********":
        item.value = value


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


async def _global_config(session: SessionDep) -> SmartProxyGlobalConfig:
    port_start, port_end = await get_smart_proxy_port_range(session)
    policy = await smart_proxy_traffic_policy(session)
    settings = get_settings()
    return SmartProxyGlobalConfig(
        smart_proxy_port_start=port_start,
        smart_proxy_port_end=port_end,
        smart_proxy_bind_host=settings.SMART_PROXY_BIND_HOST.strip() or "127.0.0.1",
        smart_proxy_auto_apply_interval_minutes=await get_smart_proxy_auto_apply_interval_minutes(session),
        smart_proxy_monitor_interval_minutes=await get_smart_proxy_monitor_interval_minutes(session),
        smart_proxy_monitor_state=await smart_proxy_monitor_state(session),
        mihomo_runtime_config_path=await get_mihomo_runtime_config_path(session),
        mihomo_core_config_path=await get_mihomo_core_config_path(session),
        traffic_guard_enabled=policy.traffic_guard_enabled,
        min_remaining_mb=policy.min_remaining_mb,
        low_remaining_mb=policy.low_remaining_mb,
        expire_soon_days=policy.expire_soon_days,
        exclude_unknown_traffic=policy.exclude_unknown_traffic,
    )


async def _proxy_config(session: SessionDep, proxy: SmartProxy) -> SmartProxyConfig:
    policy = await smart_proxy_traffic_policy(session, proxy)
    return SmartProxyConfig(
        proxy_id=proxy.id,
        use_global_traffic_policy=smart_proxy_uses_global_policy(proxy),
        traffic_guard_enabled=proxy.traffic_guard_enabled,
        min_remaining_mb=proxy.min_remaining_mb,
        low_remaining_mb=proxy.low_remaining_mb,
        expire_soon_days=proxy.expire_soon_days,
        exclude_unknown_traffic=proxy.exclude_unknown_traffic,
        effective_traffic_guard_enabled=policy.traffic_guard_enabled,
        effective_min_remaining_mb=policy.min_remaining_mb,
        effective_low_remaining_mb=policy.low_remaining_mb,
        effective_expire_soon_days=policy.expire_soon_days,
        effective_exclude_unknown_traffic=policy.exclude_unknown_traffic,
    )


@router.get("", response_model=list[SmartProxyRead])
async def list_smart_proxies(session: SessionDep, current_user: CurrentUser) -> list[SmartProxyRead]:
    await _ensure_node_pool_for_candidates(session, current_user.username)
    proxies = list((await session.scalars(select(SmartProxy).order_by(SmartProxy.id.asc()))).all())
    return [await _read_proxy(session, item) for item in proxies]


@router.post("", response_model=SmartProxyRead, status_code=status.HTTP_201_CREATED)
async def create_smart_proxy(
    payload: SmartProxyCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> SmartProxyRead:
    try:
        data = _prepare_payload(payload.model_dump())
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.get("port") is None:
        data["port"] = await allocate_smart_proxy_port(session)
    try:
        _validate_source_config(
            str(data.get("data_source") or "subscription"),
            str(data.get("source_mode") or "all"),
            data.get("subscription_ids") or [],
            data.get("country_codes") or [],
            data.get("tags") or [],
            data.get("node_ids") or [],
            data.get("ant_node_ids") or [],
        )
        _validate_strategy_config(
            str(data.get("strategy") or "fallback"),
            str(data.get("data_source") or "subscription"),
            str(data.get("source_mode") or "all"),
            data.get("node_ids") or [],
            data.get("strategy_node_ids") or [],
            data.get("ant_node_ids") or [],
            data.get("ant_strategy_node_ids") or [],
        )
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await _ensure_unique_name(session, str(data["name"]))
        await ensure_unique_port(session, int(data["port"]))
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    proxy = SmartProxy(**data, status="stopped", config_updated_at=now_china())
    session.add(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="create",
        resource="smart_proxy",
        detail=f"新增智能代理「{proxy.name}」，端口 {proxy.port}，策略 {proxy.strategy}。",
    )
    await session.commit()
    await session.refresh(proxy)
    return await _read_proxy(session, proxy)


@router.post("/reload", response_model=SmartProxyRuntime)
async def reload_runtime(
    session: SessionDep,
    current_user: CurrentUser,
    reload_core: bool = Query(default=False),
    include_content: bool = Query(default=False),
) -> SmartProxyRuntime:
    result = await apply_mihomo_runtime(session, reload_core=reload_core)
    await write_audit(
        session,
        actor=current_user.username,
        action="reload",
        resource="smart_proxy",
        detail=(
            f"重新加载智能代理运行时配置：配置文件 {result.config_path}"
            + (f"，核心重载{'成功' if result.reloaded else '未执行'}" if reload_core else "")
            + (f"，错误：{result.error}" if result.error else "")
            + "。"
        ),
    )
    await session.commit()
    if not include_content:
        result.content = None
    return _runtime_response(result)


@router.get("/runtime", response_model=SmartProxyRuntime)
async def preview_runtime(
    session: SessionDep,
    current_user: CurrentUser,
    include_content: bool = Query(default=True),
) -> SmartProxyRuntime:
    result = await write_mihomo_runtime_config(session)
    await write_audit(
        session,
        actor=current_user.username,
        action="preview",
        resource="smart_proxy",
        detail=f"预览智能代理运行时配置：配置文件 {result.config_path}，监听器 {result.listeners} 个。",
    )
    await session.commit()
    if not include_content:
        result.content = None
    return _runtime_response(result)


@router.get("/core/status", response_model=MihomoCoreStatus)
async def core_status(session: SessionDep, current_user: CurrentUser) -> MihomoCoreStatus:
    return MihomoCoreStatus(**await mihomo_core_status(session))


@router.get("/presets", response_model=list[SmartProxyPreset])
async def list_smart_proxy_presets(session: SessionDep, current_user: CurrentUser) -> list[SmartProxyPreset]:
    return SMART_PROXY_PRESETS


@router.get("/metadata", response_model=SmartProxyMetadata)
async def smart_proxy_metadata(session: SessionDep, current_user: CurrentUser) -> SmartProxyMetadata:
    country_rows = (
        await session.execute(
            select(Node.country_code, Node.country, func.count(Node.id))
            .where(Node.enabled.is_(True), Node.country_code.is_not(None))
            .group_by(Node.country_code, Node.country)
            .order_by(Node.country_code.asc())
        )
    ).all()
    countries = [
        {"code": row[0], "name": row[1], "nodes": row[2]}
        for row in country_rows
        if row[0]
    ]

    subscription_rows = (
        await session.execute(
            select(Subscription.id, Subscription.name, Subscription.group_name, Subscription.enabled, func.count(Node.id))
            .join(Node, Node.source_subscription_id == Subscription.id, isouter=True)
            .group_by(Subscription.id, Subscription.name, Subscription.group_name, Subscription.enabled)
            .order_by(Subscription.priority.asc(), Subscription.id.asc())
        )
    ).all()
    subscriptions = [
        {"id": row[0], "name": row[1], "group_name": row[2], "enabled": row[3], "nodes": row[4]}
        for row in subscription_rows
    ]

    nodes = list((await session.execute(select(Node.tags, Node.type).where(Node.enabled.is_(True)))).all())
    tag_set: set[str] = set()
    protocol_set: set[str] = set()
    for tags, protocol in nodes:
        for tag in tags or []:
            if str(tag).strip():
                tag_set.add(str(tag).strip())
        if protocol:
            protocol_set.add(str(protocol).strip())

    from app.services.ant_proxy import ant_proxy_service

    ant_country_counts: dict[tuple[str, str], int] = {}
    ant_tag_counts: dict[tuple[str, str], int] = {}
    ant_protocol_set: set[str] = set()
    for node in ant_proxy_service.nodes:
        if node.country_code:
            key = (str(node.country_code).upper(), str(node.country or node.city or ""))
            ant_country_counts[key] = ant_country_counts.get(key, 0) + 1
        if node.line_type:
            key = (f"line:{node.line_type}", node.line_label or node.line_type)
            ant_tag_counts[key] = ant_tag_counts.get(key, 0) + 1
        if node.transport:
            ant_protocol_set.add(str(node.transport).strip().lower())

    return SmartProxyMetadata(
        countries=countries,
        subscriptions=subscriptions,
        tags=sorted(tag_set),
        protocol_types=sorted(protocol_set),
        ant_loaded=bool(ant_proxy_service.nodes),
        ant_countries=[
            {"code": code, "name": name, "nodes": count}
            for (code, name), count in sorted(ant_country_counts.items(), key=lambda item: item[0][0])
        ],
        ant_tags=[
            {"value": value, "label": label, "nodes": count}
            for (value, label), count in sorted(ant_tag_counts.items(), key=lambda item: item[0][1])
        ],
        ant_protocol_types=sorted(ant_protocol_set),
        presets=SMART_PROXY_PRESETS,
    )


@router.post("/access/enforce", response_model=SmartProxyAccessEnforceResult)
async def enforce_smart_proxy_access_control(
    session: SessionDep,
    current_user: CurrentUser,
) -> SmartProxyAccessEnforceResult:
    try:
        result = await enforce_smart_proxy_access(session)
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MihomoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await write_audit(
        session,
        actor=current_user.username,
        action="access_enforce",
        resource="smart_proxy",
        detail=f"执行智能代理访问控制完成：关闭 {result.get('closed_connections', 0)} 个不符合规则的连接。",
    )
    await session.commit()
    return SmartProxyAccessEnforceResult(**result)


@router.get("/config/global", response_model=SmartProxyGlobalConfig)
async def get_global_config(session: SessionDep, current_user: CurrentUser) -> SmartProxyGlobalConfig:
    return await _global_config(session)


@router.put("/config/global", response_model=SmartProxyGlobalConfig)
async def update_global_config(
    payload: SmartProxyGlobalConfigUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> SmartProxyGlobalConfig:
    data = payload.model_dump(exclude_unset=True)
    key_map = {
        "traffic_guard_enabled": "smart_proxy_traffic_guard_enabled",
        "min_remaining_mb": "smart_proxy_min_remaining_mb",
        "low_remaining_mb": "smart_proxy_low_remaining_mb",
        "expire_soon_days": "smart_proxy_expire_soon_days",
        "exclude_unknown_traffic": "smart_proxy_exclude_unknown_traffic",
    }
    for key, value in data.items():
        setting_key = key_map.get(key, key)
        if setting_key not in GLOBAL_CONFIG_KEYS or value is None:
            continue
        if isinstance(value, bool):
            await _set_setting(session, setting_key, _bool_text(value))
        else:
            await _set_setting(session, setting_key, str(value))
    if data:
        await _mark_all_configs_changed(session)
    changed = "、".join(GLOBAL_CONFIG_LABELS.get(key, key) for key in data) if data else "无字段变化"
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="smart_proxy_config",
        detail=f"更新智能代理全局配置，变更字段：{changed}。",
    )
    await session.commit()
    apply_error = await _apply_runtime_after_change(session)
    config = await _global_config(session)
    config.runtime_apply_error = apply_error
    return config


@router.get("/{proxy_id}", response_model=SmartProxyRead)
async def get_smart_proxy(proxy_id: int, session: SessionDep, current_user: CurrentUser) -> SmartProxyRead:
    await _ensure_node_pool_for_candidates(session, current_user.username)
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    return await _read_proxy(session, proxy)


@router.get("/{proxy_id}/status", response_model=SmartProxyStatus)
async def get_smart_proxy_status(
    proxy_id: int,
    session: SessionDep,
    current_user: CurrentUser,
    delay: bool = Query(default=False),
    sync: bool = Query(default=False),
) -> SmartProxyStatus:
    await _ensure_node_pool_for_candidates(session, current_user.username)
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    status_payload = await smart_proxy_runtime_status(session, proxy, run_delay=delay)
    status_payload["mihomo_current_node"] = status_payload.get("current_node")
    changed = False
    if sync:
        proxy.status = status_payload["status"]
        proxy.last_error = status_payload["error"]
        failover_node = status_payload.get("stable_failover_node")
        changed = add_smart_proxy_switch_log(
            session,
            proxy,
            failover_node or status_payload.get("current_node"),
            reason="稳定优先检测到当前节点不可用，切换到可用节点" if failover_node else "手动运行状态诊断同步当前节点",
        )
        await session.commit()
    status_payload["switch_count"] = proxy.switch_count or 0
    status_payload["current_node"] = proxy.current_node or status_payload.get("mihomo_current_node")
    status_payload["state_synced"] = (
        not status_payload.get("mihomo_current_node") or status_payload.get("mihomo_current_node") == proxy.current_node
    )
    if changed:
        await apply_stability_priority_runtime(session, [proxy])
    return SmartProxyStatus(**status_payload)


@router.get("/{proxy_id}/config", response_model=SmartProxyConfig)
async def get_smart_proxy_config(proxy_id: int, session: SessionDep, current_user: CurrentUser) -> SmartProxyConfig:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    return await _proxy_config(session, proxy)


@router.put("/{proxy_id}/config", response_model=SmartProxyConfig)
async def update_smart_proxy_config(
    proxy_id: int,
    payload: SmartProxyConfigUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> SmartProxyConfig:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    if payload.use_global_traffic_policy:
        proxy.traffic_guard_enabled = None
        proxy.min_remaining_mb = None
        proxy.low_remaining_mb = None
        proxy.expire_soon_days = None
        proxy.exclude_unknown_traffic = None
    else:
        proxy.traffic_guard_enabled = bool(payload.traffic_guard_enabled)
        proxy.min_remaining_mb = max(int(payload.min_remaining_mb or 0), 0)
        proxy.low_remaining_mb = max(int(payload.low_remaining_mb or 0), 0)
        proxy.expire_soon_days = max(int(payload.expire_soon_days or 0), 0)
        proxy.exclude_unknown_traffic = bool(payload.exclude_unknown_traffic)
    _mark_config_changed(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="update_config",
        resource="smart_proxy",
        detail=f"更新智能代理「{proxy.name}」流量保护配置。",
    )
    await session.commit()
    await session.refresh(proxy)
    return await _proxy_config(session, proxy)


@router.post("/{proxy_id}/health-check", response_model=SmartProxyHealthResult)
async def run_smart_proxy_health_check(
    proxy_id: int,
    session: SessionDep,
    current_user: CurrentUser,
    timeout_ms: int = Query(default=8000, ge=1000, le=30000),
    scenario_checks: bool = Query(default=True),
) -> SmartProxyHealthResult:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    result = await check_smart_proxy_health(
        session,
        proxy,
        timeout_ms=timeout_ms,
        include_scenario_checks=scenario_checks,
    )
    await write_audit(
        session,
        actor=current_user.username,
        action="health_check",
        resource="smart_proxy",
        detail=(
            f"智能代理「{proxy.name}」健康检查完成：状态 {result.get('status') or '未知'}"
            + (f"，错误：{result.get('error')}" if result.get("error") else "")
            + "。"
        ),
    )
    await session.commit()
    return SmartProxyHealthResult(**result)


@router.get("/{proxy_id}/health-logs", response_model=list[SmartProxyHealthLogRead])
async def list_smart_proxy_health_logs(
    proxy_id: int,
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SmartProxyHealthLogRead]:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    logs = list(
        (
            await session.scalars(
                select(SmartProxyHealthLog)
                .where(SmartProxyHealthLog.smart_proxy_id == proxy_id)
                .order_by(desc(SmartProxyHealthLog.created_at), desc(SmartProxyHealthLog.id))
                .limit(limit)
            )
        ).all()
    )
    return [SmartProxyHealthLogRead.model_validate(item) for item in logs]


@router.get("/{proxy_id}/switch-logs", response_model=list[SmartProxySwitchLogRead])
async def list_smart_proxy_switch_logs(
    proxy_id: int,
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SmartProxySwitchLogRead]:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    logs = list(
        (
            await session.scalars(
                select(SmartProxySwitchLog)
                .where(SmartProxySwitchLog.smart_proxy_id == proxy_id)
                .order_by(desc(SmartProxySwitchLog.created_at), desc(SmartProxySwitchLog.id))
                .limit(limit)
            )
        ).all()
    )
    return [SmartProxySwitchLogRead.model_validate(item) for item in logs]


@router.put("/{proxy_id}", response_model=SmartProxyRead)
async def update_smart_proxy(
    proxy_id: int,
    payload: SmartProxyUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> SmartProxyRead:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    try:
        data = _prepare_payload(payload.model_dump(exclude_unset=True))
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        if "port" in data and data["port"] is not None:
            await ensure_unique_port(session, int(data["port"]), exclude_id=proxy.id)
        if "name" in data and data["name"] is not None:
            await _ensure_unique_name(session, str(data["name"]), exclude_id=proxy.id)
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        for key, value in data.items():
            setattr(proxy, key, value)
        if proxy.strategy == "stable":
            proxy.stability_priority = True
        elif proxy.strategy not in {"select", "fallback"}:
            proxy.stability_priority = False
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _validate_proxy_strategy(proxy)
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _mark_config_changed(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="smart_proxy",
        detail=f"修改智能代理「{proxy.name}」。",
    )
    await session.commit()
    await session.refresh(proxy)
    return await _read_proxy(session, proxy)


@router.delete("/{proxy_id}", response_model=Message)
async def delete_smart_proxy(proxy_id: int, session: SessionDep, current_user: CurrentUser) -> Message:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    name = proxy.name
    await session.delete(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="delete",
        resource="smart_proxy",
        detail=f"删除智能代理「{name}」。",
    )
    await session.commit()
    await _apply_runtime_after_change(session)
    return Message(message="Smart proxy deleted")


@router.post("/{proxy_id}/start", response_model=SmartProxyRead)
async def start_smart_proxy(proxy_id: int, session: SessionDep, current_user: CurrentUser) -> SmartProxyRead:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    proxy.enabled = True
    _mark_config_changed(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="start",
        resource="smart_proxy",
        detail=f"启动智能代理「{proxy.name}」。",
    )
    await session.commit()
    await session.refresh(proxy)
    apply_error = await _apply_runtime_after_change(session)
    await session.refresh(proxy)
    return await _read_proxy(session, proxy, runtime_apply_error=apply_error)


@router.post("/{proxy_id}/stop", response_model=SmartProxyRead)
async def stop_smart_proxy(proxy_id: int, session: SessionDep, current_user: CurrentUser) -> SmartProxyRead:
    proxy = await session.get(SmartProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Smart proxy not found")
    proxy.enabled = False
    proxy.status = "stopped"
    _mark_config_changed(proxy)
    await write_audit(
        session,
        actor=current_user.username,
        action="stop",
        resource="smart_proxy",
        detail=f"停止智能代理「{proxy.name}」。",
    )
    await session.commit()
    await session.refresh(proxy)
    apply_error = await _apply_runtime_after_change(session)
    await session.refresh(proxy)
    return await _read_proxy(session, proxy, runtime_apply_error=apply_error)
