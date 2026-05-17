from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.models.subscription import Subscription
from app.models.traffic_snapshot import TrafficSnapshot
from app.schemas.common import Message
from app.schemas.subscription import SubscriptionCreate, SubscriptionRead, SubscriptionUpdate
from app.services.aggregator import refresh_subscription_source
from app.services.audit import write_audit
from app.services.node_pool import sync_node_pool_background
from app.services.subconverter import SubconverterError
from app.services.traffic import get_or_create_traffic_snapshot, poll_traffic_snapshot
from app.utils.network import UrlValidationError, validate_subscription_url


router = APIRouter()


FIELD_LABELS = {
    "name": "名称",
    "url": "URL",
    "enabled": "启用状态",
    "tags": "标签",
    "group_name": "分组",
    "remark": "备注",
    "update_interval": "更新间隔",
    "priority": "优先级",
}


def _schedule_node_pool_sync(background_tasks: BackgroundTasks, *, actor: str) -> None:
    background_tasks.add_task(sync_node_pool_background, emoji=True, actor=actor, reason="订阅配置变更后同步")


def _enabled_text(value: bool) -> str:
    return "启用" if value else "停用"


def _changed_fields_text(data: dict) -> str:
    labels = [FIELD_LABELS.get(key, key) for key in data]
    return "、".join(labels) if labels else "无字段变化"


def _mark_subscription_sync_state(item: Subscription) -> None:
    if item.enabled:
        item.last_status = "syncing"
        item.last_error = None
    else:
        item.last_status = "disabled"
        item.last_error = None
        item.last_updated_at = datetime.now(UTC)


def _traffic_by_subscription(snapshot: TrafficSnapshot | None) -> dict[int, dict]:
    if snapshot is None:
        return {}
    return {int(item.get("subscription_id") or 0): item for item in snapshot.items}


def _subscription_read(item: Subscription, traffic: dict | None = None, traffic_updated_at: str | None = None) -> SubscriptionRead:
    traffic = traffic or {}
    upload = int(traffic.get("upload") or 0)
    download = int(traffic.get("download") or 0)
    total = int(traffic.get("total") or 0)
    used = int(traffic.get("used") or (upload + download))
    remaining = int(traffic.get("remaining") or max(total - used, 0))
    return SubscriptionRead(
        id=item.id,
        name=item.name,
        url=item.url,
        enabled=item.enabled,
        tags=item.tags or [],
        group_name=item.group_name,
        remark=item.remark,
        update_interval=item.update_interval,
        priority=item.priority,
        last_status=item.last_status,
        last_error=item.last_error,
        last_updated_at=item.last_updated_at,
        traffic_upload=upload,
        traffic_download=download,
        traffic_used=used,
        traffic_total=total,
        traffic_remaining=remaining,
        traffic_expire_at=traffic.get("expire_at"),
        traffic_available=bool(traffic.get("available", False)),
        traffic_stale=bool(traffic.get("stale", False)),
        traffic_error=traffic.get("error"),
        traffic_updated_at=traffic_updated_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _subscription_reads(session: AsyncSession, items: list[Subscription]) -> list[SubscriptionRead]:
    snapshot = await get_or_create_traffic_snapshot(session)
    traffic_items = _traffic_by_subscription(snapshot)
    traffic_updated_at = snapshot.created_at.isoformat() if snapshot else None
    return [_subscription_read(item, traffic_items.get(item.id), traffic_updated_at) for item in items]


@router.get("", response_model=list[SubscriptionRead])
async def list_subscriptions(
    session: SessionDep,
    current_user: CurrentUser,
    group: str | None = Query(default=None),
) -> list[SubscriptionRead]:
    stmt = select(Subscription).order_by(Subscription.priority.asc(), Subscription.id.asc())
    if group:
        stmt = stmt.where(Subscription.group_name == group)
    items = (await session.scalars(stmt)).all()
    return await _subscription_reads(session, list(items))


@router.post("/traffic/refresh", response_model=list[SubscriptionRead])
async def refresh_subscription_traffic(session: SessionDep, current_user: CurrentUser) -> list[SubscriptionRead]:
    snapshot = await poll_traffic_snapshot(session)
    failed = sum(1 for item in snapshot.items if item.get("error"))
    await write_audit(
        session,
        actor=current_user.username,
        action="traffic_refresh",
        resource="subscription",
        detail=f"手动刷新订阅流量完成：共 {len(snapshot.items)} 个订阅，异常 {failed} 个。",
    )
    await session.commit()
    items = (await session.scalars(select(Subscription).order_by(Subscription.priority.asc(), Subscription.id.asc()))).all()
    return await _subscription_reads(session, list(items))


@router.post("", response_model=SubscriptionRead, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    payload: SubscriptionCreate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> SubscriptionRead:
    try:
        await validate_subscription_url(str(payload.url))
    except UrlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = Subscription(**payload.model_dump(mode="json"))
    item.url = str(payload.url)
    _mark_subscription_sync_state(item)
    session.add(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="create",
        resource="subscription",
        detail=f"新增订阅「{item.name}」，分组「{item.group_name}」，状态：{_enabled_text(item.enabled)}。",
    )
    await session.commit()
    await session.refresh(item)
    _schedule_node_pool_sync(background_tasks, actor=current_user.username)
    return _subscription_read(item)


@router.get("/{subscription_id}", response_model=SubscriptionRead)
async def get_subscription(subscription_id: int, session: SessionDep, current_user: CurrentUser) -> SubscriptionRead:
    item = await session.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    snapshot = await get_or_create_traffic_snapshot(session)
    traffic_items = _traffic_by_subscription(snapshot)
    traffic_updated_at = snapshot.created_at.isoformat() if snapshot else None
    return _subscription_read(item, traffic_items.get(item.id), traffic_updated_at)


@router.put("/{subscription_id}", response_model=SubscriptionRead)
async def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> SubscriptionRead:
    item = await session.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    data = payload.model_dump(exclude_unset=True, mode="json")
    if "url" in data:
        try:
            await validate_subscription_url(str(data["url"]))
        except UrlValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        data["url"] = str(data["url"])
    for key, value in data.items():
        setattr(item, key, value)
    _mark_subscription_sync_state(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="subscription",
        detail=f"修改订阅「{item.name}」，变更字段：{_changed_fields_text(data)}，当前状态：{_enabled_text(item.enabled)}。",
    )
    await session.commit()
    await session.refresh(item)
    _schedule_node_pool_sync(background_tasks, actor=current_user.username)
    return _subscription_read(item)


@router.delete("/{subscription_id}", response_model=Message)
async def delete_subscription(
    subscription_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    item = await session.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    name = item.name
    await session.delete(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="delete",
        resource="subscription",
        detail=f"删除订阅「{name}」。",
    )
    await session.commit()
    _schedule_node_pool_sync(background_tasks, actor=current_user.username)
    return Message(message="Subscription deleted")


@router.post("/{subscription_id}/refresh", response_model=SubscriptionRead)
async def refresh_subscription(subscription_id: int, session: SessionDep, current_user: CurrentUser) -> SubscriptionRead:
    item = await session.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        await refresh_subscription_source(session, item, audit_actor=current_user.username)
    except UrlValidationError as exc:
        item.last_status = "failed"
        item.last_error = str(exc)
        await write_audit(
            session,
            actor=current_user.username,
            action="refresh_failed",
            resource="subscription",
            detail=f"刷新订阅「{item.name}」失败：{exc}。",
        )
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SubconverterError as exc:
        item.last_status = "failed"
        item.last_error = str(exc)
        await write_audit(
            session,
            actor=current_user.username,
            action="refresh_failed",
            resource="subscription",
            detail=f"刷新订阅「{item.name}」失败：{exc}。",
        )
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await write_audit(
        session,
        actor=current_user.username,
        action="refresh",
        resource="subscription",
        detail=f"手动刷新订阅「{item.name}」完成，当前状态：{item.last_status or '未知'}。",
    )
    await session.commit()
    await session.refresh(item)
    return _subscription_read(item)
