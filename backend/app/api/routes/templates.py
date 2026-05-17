from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, SessionDep
from app.models.config_template import ConfigTemplate
from app.schemas.common import Message
from app.schemas.template import ConfigTemplateCreate, ConfigTemplateRead, ConfigTemplateUpdate
from app.services.audit import write_audit


router = APIRouter()


@router.get("", response_model=list[ConfigTemplateRead])
async def list_templates(session: SessionDep, current_user: CurrentUser) -> list[ConfigTemplateRead]:
    items = (await session.scalars(select(ConfigTemplate).order_by(ConfigTemplate.id.asc()))).all()
    return [ConfigTemplateRead.model_validate(item) for item in items]


@router.post("", response_model=ConfigTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ConfigTemplateCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConfigTemplateRead:
    if payload.is_default:
        await session.execute(update(ConfigTemplate).where(ConfigTemplate.target == payload.target).values(is_default=False))
    item = ConfigTemplate(**payload.model_dump())
    session.add(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="create",
        resource="config_template",
        detail=f"新增配置模板「{item.name}」，目标客户端：{item.target}。",
    )
    await session.commit()
    await session.refresh(item)
    return ConfigTemplateRead.model_validate(item)


@router.put("/{template_id}", response_model=ConfigTemplateRead)
async def update_template(
    template_id: int,
    payload: ConfigTemplateUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConfigTemplateRead:
    item = await session.get(ConfigTemplate, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(item, key, value)
    if item.is_default:
        await session.execute(
            update(ConfigTemplate)
            .where(ConfigTemplate.target == item.target, ConfigTemplate.id != item.id)
            .values(is_default=False)
        )
    await write_audit(
        session,
        actor=current_user.username,
        action="update",
        resource="config_template",
        detail=f"修改配置模板「{item.name}」，目标客户端：{item.target}。",
    )
    await session.commit()
    await session.refresh(item)
    return ConfigTemplateRead.model_validate(item)


@router.delete("/{template_id}", response_model=Message)
async def delete_template(template_id: int, session: SessionDep, current_user: CurrentUser) -> Message:
    item = await session.get(ConfigTemplate, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found")
    name = item.name
    target = item.target
    await session.delete(item)
    await write_audit(
        session,
        actor=current_user.username,
        action="delete",
        resource="config_template",
        detail=f"删除配置模板「{name}」，目标客户端：{target}。",
    )
    await session.commit()
    return Message(message="Template deleted")
