from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, SessionDep
from app.models.rule_template import RuleTemplate
from app.schemas.common import Message
from app.schemas.rule import RuleTemplateCreate, RuleTemplateRead, RuleTemplateUpdate
from app.services.audit import write_audit


router = APIRouter()


@router.get("", response_model=list[RuleTemplateRead])
async def list_rules(session: SessionDep, current_user: CurrentUser) -> list[RuleTemplateRead]:
    items = (await session.scalars(select(RuleTemplate).order_by(RuleTemplate.id.asc()))).all()
    return [RuleTemplateRead.model_validate(item) for item in items]


@router.post("", response_model=RuleTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_rule(payload: RuleTemplateCreate, session: SessionDep, current_user: CurrentUser) -> RuleTemplateRead:
    if payload.is_default:
        await session.execute(update(RuleTemplate).values(is_default=False))
    item = RuleTemplate(**payload.model_dump())
    session.add(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="create",
        resource="rule_template",
        detail=f"新增规则模板「{item.name}」。",
    )
    await session.commit()
    await session.refresh(item)
    return RuleTemplateRead.model_validate(item)


@router.put("/{rule_id}", response_model=RuleTemplateRead)
async def update_rule(
    rule_id: int,
    payload: RuleTemplateUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> RuleTemplateRead:
    item = await session.get(RuleTemplate, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)
    if item.is_default:
        await session.execute(update(RuleTemplate).where(RuleTemplate.id != item.id).values(is_default=False))
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="rule_template",
        detail=f"修改规则模板「{item.name}」。",
    )
    await session.commit()
    await session.refresh(item)
    return RuleTemplateRead.model_validate(item)


@router.delete("/{rule_id}", response_model=Message)
async def delete_rule(rule_id: int, session: SessionDep, current_user: CurrentUser) -> Message:
    item = await session.get(RuleTemplate, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    name = item.name
    await session.delete(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="delete",
        resource="rule_template",
        detail=f"删除规则模板「{name}」。",
    )
    await session.commit()
    return Message(message="Rule deleted")
