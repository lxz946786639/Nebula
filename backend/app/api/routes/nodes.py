from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models.node import Node
from app.models.subscription import Subscription
from app.schemas.node import NodeLatencyResult, NodeList, NodeRead, NodeRefreshResult, NodeUpdate
from app.services.audit import write_audit
from app.services.node_latency import test_node_latencies
from app.services.node_pool import NodePoolSyncResult, sync_node_pool
from app.services.subconverter import SubconverterError


router = APIRouter()


def _node_read(node: Node, subscription: Subscription | None = None) -> NodeRead:
    return NodeRead(
        id=node.id,
        name=node.name,
        type=node.type,
        server=node.server,
        port=node.port,
        country=node.country,
        country_code=node.country_code,
        tags=node.tags or [],
        latency=node.latency,
        alive=node.latency is not None,
        source=node.source_subscription_name,
        source_subscription_id=node.source_subscription_id,
        source_subscription_name=node.source_subscription_name,
        source_subscription_status=subscription.last_status if subscription else None,
        source_subscription_error=subscription.last_error if subscription else None,
        source_group=node.source_group,
        enabled=node.enabled,
        last_seen_at=node.last_seen_at,
        raw=node.raw or {},
    )


def _refresh_result(result: NodePoolSyncResult) -> NodeRefreshResult:
    return NodeRefreshResult(
        total_nodes=result.total_nodes,
        cleared_nodes=result.cleared_nodes,
        synced_nodes=result.synced_nodes,
        filtered_nodes=result.filtered_nodes,
        disabled_nodes=result.disabled_nodes,
        refreshed_subscriptions=result.refreshed_subscriptions,
        failed_subscriptions=result.failed_subscriptions,
        errors=result.errors,
    )


@router.get("", response_model=NodeList)
async def list_nodes(
    session: SessionDep,
    current_user: CurrentUser,
    group: str | None = None,
    q: str | None = Query(default=None),
    country: str | None = None,
    enabled: bool | None = Query(default=None),
    emoji: bool = True,
) -> NodeList:
    existing_stmt = select(func.count()).select_from(Node)
    enabled_subscription_stmt = select(func.count()).select_from(Subscription).where(Subscription.enabled.is_(True))
    if group:
        existing_stmt = existing_stmt.where(Node.source_group == group)
        enabled_subscription_stmt = enabled_subscription_stmt.where(Subscription.group_name == group)
    existing_nodes = await session.scalar(existing_stmt) or 0
    enabled_subscriptions = await session.scalar(enabled_subscription_stmt) or 0
    if existing_nodes == 0 and enabled_subscriptions > 0:
        result = await sync_node_pool(
            session,
            group=group,
            emoji=emoji,
            audit_actor=current_user.username,
            audit_reason="节点管理自动补齐",
        )
        if result.synced_nodes == 0 and result.errors:
            raise HTTPException(status_code=502, detail="; ".join(result.errors[:3]))

    stmt = select(Node)
    if group:
        stmt = stmt.where(Node.source_group == group)
    if enabled is not None:
        stmt = stmt.where(Node.enabled.is_(enabled))
    if q:
        keyword = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Node.name).like(keyword)
            | func.lower(Node.server).like(keyword)
            | func.lower(Node.source_subscription_name).like(keyword)
        )
    if country:
        country_keyword = f"%{country.lower()}%"
        stmt = stmt.where(
            func.lower(Node.country).like(country_keyword) | func.lower(Node.country_code).like(country_keyword)
        )
    stmt = stmt.order_by(Node.country_code.is_(None), Node.country_code.asc(), Node.name.asc(), Node.id.asc())
    nodes = list((await session.scalars(stmt)).all())
    subscription_ids = {node.source_subscription_id for node in nodes if node.source_subscription_id is not None}
    subscriptions: dict[int, Subscription] = {}
    if subscription_ids:
        source_items = (await session.scalars(select(Subscription).where(Subscription.id.in_(subscription_ids)))).all()
        subscriptions = {item.id: item for item in source_items}
    return NodeList(total=len(nodes), items=[_node_read(node, subscriptions.get(node.source_subscription_id or 0)) for node in nodes])


@router.post("/refresh", response_model=NodeRefreshResult)
async def refresh_nodes(
    session: SessionDep,
    current_user: CurrentUser,
    group: str | None = None,
    emoji: bool = True,
) -> NodeRefreshResult:
    try:
        result = await sync_node_pool(
            session,
            group=group,
            emoji=emoji,
            audit_actor=current_user.username,
            audit_reason="手动同步",
        )
    except SubconverterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _refresh_result(result)


@router.post("/test-latency", response_model=NodeLatencyResult)
async def test_latencies(
    session: SessionDep,
    current_user: CurrentUser,
    group: str | None = None,
    enabled: bool | None = Query(default=True),
    timeout_ms: int = Query(default=3000, ge=300, le=15000),
    concurrency: int = Query(default=30, ge=1, le=100),
) -> NodeLatencyResult:
    result = await test_node_latencies(
        session,
        group=group,
        enabled=enabled,
        timeout_ms=timeout_ms,
        concurrency=concurrency,
    )
    await write_audit(
        session,
        actor=current_user.username,
        action="test_latency",
        resource="node",
        detail=(
            f"一键测速完成：共 {result.total_nodes} 个节点，测试 {result.tested_nodes} 个，"
            f"在线 {result.online_nodes} 个，失败 {result.failed_nodes} 个。"
        ),
    )
    await session.commit()
    return NodeLatencyResult(
        total_nodes=result.total_nodes,
        tested_nodes=result.tested_nodes,
        online_nodes=result.online_nodes,
        failed_nodes=result.failed_nodes,
    )


@router.put("/{node_id}", response_model=NodeRead)
async def update_node(
    node_id: int,
    payload: NodeUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> NodeRead:
    node = await session.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(node, key, value)
    if "enabled" in data:
        action = "enable" if node.enabled else "disable"
        detail = f"{'启用' if node.enabled else '禁用'}节点「{node.name}」。"
    else:
        action = "update"
        detail = f"修改节点「{node.name}」。"
    await write_audit(session, actor=current_user.username, action=action, resource="node", detail=detail)
    await session.commit()
    await session.refresh(node)
    return _node_read(node)
