from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConfigTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target: str = "clashmeta"
    config_url: str | None = None
    yaml_content: str | None = None
    is_default: bool = False


class ConfigTemplateCreate(ConfigTemplateBase):
    pass


class ConfigTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target: str | None = None
    config_url: str | None = None
    yaml_content: str | None = None
    is_default: bool | None = None


class ConfigTemplateRead(ConfigTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
