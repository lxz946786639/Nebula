from pydantic import BaseModel, ConfigDict


class SettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str | None
    secret: bool
    description: str | None
    read_only: bool = False


class SettingUpdate(BaseModel):
    value: str | None


class SettingBulkUpdate(BaseModel):
    settings: dict[str, str | None]
