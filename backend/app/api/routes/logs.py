from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogPage, AuditLogRead, AuditLogType


router = APIRouter()


RESOURCE_LABELS = {
    "auth": "认证",
    "subscription": "订阅",
    "node_pool": "节点池",
    "node": "节点",
    "smart_proxy": "智能代理",
    "smart_proxy_config": "智能代理配置",
    "settings": "系统配置",
    "rule_template": "规则模板",
    "config_template": "配置模板",
}

ACTION_LABELS = {
    "login": "登录",
    "create": "新增",
    "update": "修改",
    "delete": "删除",
    "refresh": "刷新",
    "refresh_failed": "刷新失败",
    "traffic_refresh": "刷新流量",
    "sync": "同步",
    "test_latency": "测速",
    "enable": "启用",
    "disable": "禁用",
    "start": "启动",
    "stop": "停止",
    "reload": "重新加载",
    "apply": "应用",
    "monitor": "监控",
    "health_check": "健康检查",
    "update_config": "更新配置",
    "access_enforce": "访问控制",
}

DETAIL_ACTIONS = {"traffic_refresh", "test_latency", "access_enforce", "health_check", "reload", "sync"}


def _resource_label(resource: str) -> str:
    return RESOURCE_LABELS.get(resource, resource)


def _action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _has_chinese_text(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _is_sentence_detail(value: str) -> bool:
    return _has_chinese_text(value) and any(mark in value for mark in "，。：；、")


def _build_title(item: AuditLog) -> str:
    type_label = _resource_label(item.resource)
    action_label = _action_label(item.action)
    detail = (item.detail or "").strip()
    if detail and not _is_sentence_detail(detail):
        return f"{type_label}{action_label}：{detail}"
    return f"{type_label}{action_label}"


def _build_description(item: AuditLog) -> str:
    type_label = _resource_label(item.resource)
    action_label = _action_label(item.action)
    detail = (item.detail or "").strip()
    actor = item.actor or "系统"

    if detail and _is_sentence_detail(detail):
        return detail
    if item.action == "login":
        return f"用户「{actor}」登录系统。"
    if detail:
        if item.action in DETAIL_ACTIONS:
            return f"用户「{actor}」执行{type_label}{action_label}：{detail}。"
        return f"用户「{actor}」{action_label}{type_label}「{detail}」。"
    return f"用户「{actor}」{action_label}{type_label}。"


def _log_read(item: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=item.id,
        actor=item.actor,
        action=item.action,
        action_label=_action_label(item.action),
        resource=item.resource,
        type=item.resource,
        type_label=_resource_label(item.resource),
        detail=item.detail,
        title=_build_title(item),
        description=_build_description(item),
        created_at=item.created_at,
        created_at_text=_format_datetime(item.created_at),
    )


@router.get("/types", response_model=list[AuditLogType])
async def list_log_types(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[AuditLogType]:
    resources = list((await session.scalars(select(AuditLog.resource).distinct().order_by(AuditLog.resource.asc()))).all())
    known = [AuditLogType(value=value, label=label) for value, label in RESOURCE_LABELS.items()]
    known_values = {item.value for item in known}
    extra = [AuditLogType(value=value, label=_resource_label(value)) for value in resources if value not in known_values]
    return known + extra


@router.get("", response_model=AuditLogPage)
async def list_logs(
    session: SessionDep,
    current_user: CurrentUser,
    log_type: str | None = Query(default=None, alias="type"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> AuditLogPage:
    conditions = []
    if log_type:
        conditions.append(AuditLog.resource == log_type)
    if start_at:
        conditions.append(AuditLog.created_at >= start_at)
    if end_at:
        conditions.append(AuditLog.created_at <= end_at)

    total_stmt = select(func.count()).select_from(AuditLog)
    stmt = select(AuditLog)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = await session.scalar(total_stmt) or 0
    items = list(
        (
            await session.scalars(
                stmt.order_by(desc(AuditLog.created_at), desc(AuditLog.id))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return AuditLogPage(total=total, page=page, page_size=page_size, items=[_log_read(item) for item in items])
