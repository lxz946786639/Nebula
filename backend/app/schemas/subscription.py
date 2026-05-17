from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SubscriptionBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    group_name: str = Field(default="default", max_length=80)
    remark: str | None = None
    update_interval: int = Field(default=3600, ge=60)
    priority: int = Field(default=100, ge=0)


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: HttpUrl | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    group_name: str | None = Field(default=None, max_length=80)
    remark: str | None = None
    update_interval: int | None = Field(default=None, ge=60)
    priority: int | None = Field(default=None, ge=0)


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    enabled: bool
    tags: list[str]
    group_name: str
    remark: str | None
    update_interval: int
    priority: int
    last_status: str | None
    last_error: str | None
    last_updated_at: datetime | None
    traffic_upload: int = 0
    traffic_download: int = 0
    traffic_used: int = 0
    traffic_total: int = 0
    traffic_remaining: int = 0
    traffic_expire_at: str | None = None
    traffic_available: bool = False
    traffic_stale: bool = False
    traffic_error: str | None = None
    traffic_updated_at: str | None = None
    created_at: datetime
    updated_at: datetime
