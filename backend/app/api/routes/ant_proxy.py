from datetime import timedelta

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.timezone import as_china
from app.models.system_setting import SystemSetting
from app.schemas.ant_proxy import (
    AntProxyLatencyRequest,
    AntProxyLatencyResult,
    AntProxyLoginRequest,
    AntProxyNodeList,
    AntProxyRefreshRequest,
    AntProxyScheduleConfig,
    AntProxyScheduleUpdate,
    AntProxySelectRequest,
    AntProxyStartRequest,
    AntProxyStatus,
    AntProxyTestRequest,
    AntProxyTestResult,
    AntProxyTrafficSummary,
)
from app.services.audit import write_audit
from app.services.ant_proxy import DEFAULT_ANT_LISTEN_PORT, AntProxyError, ant_proxy_service, ant_proxy_traffic_summary
from app.services.settings import get_ant_proxy_auto_refresh_enabled, get_ant_proxy_auto_refresh_interval_minutes
from app.services.smart_proxy import (
    SmartProxyError,
    allocate_runtime_proxy_port,
    ant_adapter_hosts,
    apply_mihomo_runtime,
    ensure_runtime_proxy_port_available,
)


router = APIRouter()


async def _set_setting(session: SessionDep, key: str, value: str) -> None:
    item = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if item is None:
        item = SystemSetting(key=key, value=value, secret=False)
        session.add(item)
    else:
        item.value = value


async def _schedule_config(session: SessionDep) -> AntProxyScheduleConfig:
    enabled = await get_ant_proxy_auto_refresh_enabled(session)
    interval_minutes = await get_ant_proxy_auto_refresh_interval_minutes(session)
    last_refreshed_at = as_china(ant_proxy_service.last_loaded_at) if ant_proxy_service.source_type == "account" else None
    next_refresh_at = None
    if enabled and interval_minutes > 0 and last_refreshed_at is not None:
        next_refresh_at = last_refreshed_at + timedelta(minutes=interval_minutes)
    return AntProxyScheduleConfig(
        enabled=enabled,
        interval_minutes=interval_minutes,
        last_refreshed_at=last_refreshed_at,
        next_refresh_at=next_refresh_at,
    )


async def _status(session: SessionDep) -> AntProxyStatus:
    await ant_proxy_service.record_traffic_sample_if_due(session)
    return AntProxyStatus.model_validate(ant_proxy_service.status())


async def _apply_ant_mihomo_runtime(session: SessionDep, *, strict: bool = False) -> None:
    result = await apply_mihomo_runtime(session, reload_core=True)
    ant_proxy_service.last_error = result.error
    if strict and result.error:
        raise AntProxyError(result.error)


async def _restart_ant_adapters_if_running(session: SessionDep) -> None:
    if not ant_proxy_service.running:
        return
    status = ant_proxy_service.status()
    adapter_bind_host, adapter_connect_host = await ant_adapter_hosts(session)
    await ant_proxy_service.start(
        listen_host=str(status.get("listen_host") or "127.0.0.1"),
        listen_port=int(status.get("listen_port") or DEFAULT_ANT_LISTEN_PORT),
        adapter_bind_host=adapter_bind_host,
        adapter_connect_host=adapter_connect_host,
        health_check_url=str(status.get("health_check_url") or ""),
        health_check_interval=int(status.get("health_check_interval") or 300),
        tolerance=int(status.get("tolerance") or 100),
    )
    await _apply_ant_mihomo_runtime(session, strict=True)


async def _resolve_ant_listen_port(session: SessionDep, requested_port: int | None) -> int:
    current_port = int(ant_proxy_service.status().get("listen_port") or 0) if ant_proxy_service.running else None
    if requested_port is None:
        return await allocate_runtime_proxy_port(session, allow_port=current_port)
    await ensure_runtime_proxy_port_available(session, requested_port, allow_port=current_port)
    return requested_port


@router.get("/status", response_model=AntProxyStatus)
async def status(current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    return await _status(session)


@router.get("/schedule", response_model=AntProxyScheduleConfig)
async def schedule_config(current_user: CurrentUser, session: SessionDep) -> AntProxyScheduleConfig:
    return await _schedule_config(session)


@router.get("/traffic", response_model=AntProxyTrafficSummary)
async def traffic_summary(
    current_user: CurrentUser,
    session: SessionDep,
    granularity: str = Query(default="hour", pattern="^(hour|day)$"),
) -> AntProxyTrafficSummary:
    return AntProxyTrafficSummary(**await ant_proxy_traffic_summary(session, granularity=granularity))


@router.put("/schedule", response_model=AntProxyScheduleConfig)
async def update_schedule_config(
    payload: AntProxyScheduleUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> AntProxyScheduleConfig:
    current_interval = await get_ant_proxy_auto_refresh_interval_minutes(session)
    enabled = await get_ant_proxy_auto_refresh_enabled(session) if payload.enabled is None else payload.enabled
    interval_minutes = current_interval if payload.interval_minutes is None else payload.interval_minutes
    if enabled and interval_minutes <= 0:
        raise HTTPException(status_code=400, detail="启用自动刷新时，刷新间隔必须大于 0 分钟")

    await _set_setting(session, "ant_proxy_auto_refresh_enabled", "true" if enabled else "false")
    await _set_setting(session, "ant_proxy_auto_refresh_interval_minutes", str(interval_minutes))
    await write_audit(
        session,
        actor=current_user.username,
        action="update_config",
        resource="ant_proxy",
        detail=f"更新蚂蚁代理后台刷新配置：{'启用' if enabled else '关闭'}，间隔 {interval_minutes} 分钟。",
    )
    await session.commit()
    return await _schedule_config(session)


@router.get("/nodes", response_model=AntProxyNodeList)
async def nodes(current_user: CurrentUser, line_type: str | None = None) -> AntProxyNodeList:
    try:
        ant_proxy_service.ensure_loaded()
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if line_type:
        normalized = line_type.lower()
        if normalized in {"1", "vip", "freegroup", "免费", "免费专线"}:
            normalized = "free"
        if normalized in {"2", "charge", "paidgroup", "付费", "付费专线"}:
            normalized = "paid"
        if normalized not in {"free", "paid"}:
            raise HTTPException(status_code=400, detail="线路类型只支持 free 或 paid")
        items = [node for node in ant_proxy_service.nodes if node.line_type == normalized]
    else:
        items = ant_proxy_service.nodes
    return AntProxyNodeList(
        total=len(items),
        free_total=len([node for node in ant_proxy_service.nodes if node.line_type == "free"]),
        paid_total=len([node for node in ant_proxy_service.nodes if node.line_type == "paid"]),
        items=[ant_proxy_service.public_node(node) for node in items],
    )


@router.post("/refresh", response_model=AntProxyStatus)
async def refresh(payload: AntProxyRefreshRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        await ant_proxy_service.refresh_account_nodes(line_type=payload.line_type)
        await _restart_ant_adapters_if_running(session)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _status(session)


@router.post("/upload", response_model=AntProxyStatus)
async def upload_db(
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),
    app_version: str = Form("2.0.9"),
) -> AntProxyStatus:
    try:
        content = await file.read()
        if len(content) > 8 * 1024 * 1024:
            raise AntProxyError("ant.db 文件过大")
        was_running = ant_proxy_service.running
        ant_proxy_service.load_db_bytes(content, file.filename or "ant.db", app_version=app_version)
        await ant_proxy_service.stop()
        if was_running:
            await _apply_ant_mihomo_runtime(session)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _status(session)


@router.post("/login", response_model=AntProxyStatus)
async def login(payload: AntProxyLoginRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        was_running = ant_proxy_service.running
        await ant_proxy_service.login(
            username=payload.username,
            password=payload.password,
            app_version=payload.app_version,
        )
        await ant_proxy_service.stop()
        if was_running:
            await _apply_ant_mihomo_runtime(session)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _status(session)


@router.post("/select", response_model=AntProxyStatus)
async def select_node(payload: AntProxySelectRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        ant_proxy_service.select_node(payload.node_id)
        await _restart_ant_adapters_if_running(session)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _status(session)


@router.post("/start", response_model=AntProxyStatus)
async def start(payload: AntProxyStartRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        adapter_bind_host, adapter_connect_host = await ant_adapter_hosts(session)
        listen_port = await _resolve_ant_listen_port(session, payload.listen_port)
    except SmartProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        await ant_proxy_service.start(
            listen_host=payload.listen_host,
            listen_port=listen_port,
            node_id=payload.node_id,
            adapter_bind_host=adapter_bind_host,
            adapter_connect_host=adapter_connect_host,
            health_check_url=payload.health_check_url,
            health_check_interval=payload.health_check_interval,
            tolerance=payload.tolerance,
        )
        await _apply_ant_mihomo_runtime(session, strict=True)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        await ant_proxy_service.stop()
        await _apply_ant_mihomo_runtime(session)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _status(session)


@router.post("/stop", response_model=AntProxyStatus)
async def stop(current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    await ant_proxy_service.persist_traffic_totals(session)
    await ant_proxy_service.stop()
    await _apply_ant_mihomo_runtime(session)
    return await _status(session)


@router.post("/test", response_model=AntProxyTestResult)
async def test(payload: AntProxyTestRequest, current_user: CurrentUser) -> AntProxyTestResult:
    try:
        result = await ant_proxy_service.test(payload.url, payload.timeout)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AntProxyTestResult.model_validate(result)


@router.post("/latencies", response_model=AntProxyLatencyResult)
async def latencies(payload: AntProxyLatencyRequest, current_user: CurrentUser) -> AntProxyLatencyResult:
    try:
        result = await ant_proxy_service.refresh_latencies(
            line_type=payload.line_type,
            timeout_ms=payload.timeout_ms,
            concurrency=payload.concurrency,
        )
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AntProxyLatencyResult.model_validate(result)
