from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: str
    action_label: str
    resource: str
    type: str
    type_label: str
    detail: str | None
    title: str
    description: str
    created_at: datetime
    created_at_text: str


class AuditLogType(BaseModel):
    value: str
    label: str


class AuditLogPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogRead]
