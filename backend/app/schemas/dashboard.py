from pydantic import BaseModel


class TrafficItem(BaseModel):
    subscription_id: int
    name: str
    upload: int
    download: int
    used: int
    total: int
    remaining: int
    expire_at: str | None
    available: bool
    stale: bool = False
    error: str | None = None
    subscription_status: str | None = None
    subscription_error: str | None = None


class TrafficStats(BaseModel):
    upload: int
    download: int
    used: int
    total: int
    remaining: int
    expire_at: str | None
    polled_at: str | None = None
    items: list[TrafficItem]


class ClientSubscriptionUrl(BaseModel):
    label: str
    target: str
    path: str


class DashboardStats(BaseModel):
    subscriptions: int
    enabled_subscriptions: int
    nodes: int
    smart_proxies: int = 0
    enabled_smart_proxies: int = 0
    cache_keys: int
    redis_status: str
    subconverter_status: str
    mihomo_status: str = "unknown"
    mihomo_version: str | None = None
    last_updated_at: str | None
    public_base_url: str = ""
    subscription_public_base_url: str = ""
    proxy_public_base_url: str = ""
    traffic: TrafficStats
    client_subscriptions: list[ClientSubscriptionUrl]
