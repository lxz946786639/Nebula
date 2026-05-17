from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuleTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    remote_config_url: str | None = None
    yaml_content: str | None = None
    is_default: bool = False


class RuleTemplateCreate(RuleTemplateBase):
    pass


class RuleTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    remote_config_url: str | None = None
    yaml_content: str | None = None
    is_default: bool | None = None


class RuleTemplateRead(RuleTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
