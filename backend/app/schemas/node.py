from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str
    type: str | None = None
    server: str | None = None
    port: int | str | None = None
    country: str | None = None
    country_code: str | None = None
    tags: list[str] = Field(default_factory=list)
    latency: int | None = None
    alive: bool | None = None
    source: str | None = None
    source_subscription_id: int | None = None
    source_subscription_name: str | None = None
    source_subscription_status: str | None = None
    source_subscription_error: str | None = None
    source_group: str | None = None
    enabled: bool = True
    last_seen_at: datetime | None = None
    raw: dict


class NodeList(BaseModel):
    total: int
    items: list[NodeRead]


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    tags: list[str] | None = None
    enabled: bool | None = None


class NodeRefreshResult(BaseModel):
    total_nodes: int
    cleared_nodes: int = 0
    synced_nodes: int
    filtered_nodes: int = 0
    disabled_nodes: int
    refreshed_subscriptions: int
    failed_subscriptions: int
    errors: list[str] = Field(default_factory=list)


class NodeLatencyResult(BaseModel):
    total_nodes: int
    tested_nodes: int
    online_nodes: int
    failed_nodes: int
