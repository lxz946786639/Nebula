from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import CurrentUser, SessionDep
from app.schemas.ant_proxy import (
    AntProxyLatencyRequest,
    AntProxyLatencyResult,
    AntProxyLoginRequest,
    AntProxyNodeList,
    AntProxyRefreshRequest,
    AntProxySelectRequest,
    AntProxyStartRequest,
    AntProxyStatus,
    AntProxyTestRequest,
    AntProxyTestResult,
)
from app.services.ant_proxy import AntProxyError, ant_proxy_service


router = APIRouter()


def _status() -> AntProxyStatus:
    return AntProxyStatus.model_validate(ant_proxy_service.status())


@router.get("/status", response_model=AntProxyStatus)
async def status(current_user: CurrentUser) -> AntProxyStatus:
    return _status()


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
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status()


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
        ant_proxy_service.load_db_bytes(content, file.filename or "ant.db", app_version=app_version)
        await ant_proxy_service.stop()
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status()


@router.post("/login", response_model=AntProxyStatus)
async def login(payload: AntProxyLoginRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        await ant_proxy_service.login(
            username=payload.username,
            password=payload.password,
            app_version=payload.app_version,
        )
        await ant_proxy_service.stop()
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status()


@router.post("/select", response_model=AntProxyStatus)
async def select_node(payload: AntProxySelectRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        ant_proxy_service.select_node(payload.node_id)
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status()


@router.post("/start", response_model=AntProxyStatus)
async def start(payload: AntProxyStartRequest, current_user: CurrentUser, session: SessionDep) -> AntProxyStatus:
    try:
        await ant_proxy_service.start(
            listen_host=payload.listen_host,
            listen_port=payload.listen_port,
            node_id=payload.node_id,
        )
        await ant_proxy_service.save_state(session)
    except AntProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _status()


@router.post("/stop", response_model=AntProxyStatus)
async def stop(current_user: CurrentUser) -> AntProxyStatus:
    await ant_proxy_service.stop()
    return _status()


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
