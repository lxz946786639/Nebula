from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SmartProxyBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    proxy_type: str = "mixed"
    listen_host: str = "127.0.0.1"
    port: int | None = None
    strategy: str = "fallback"
    stability_priority: bool = False
    scenario: str = "general"
    source_mode: str = "all"
    subscription_ids: list[int] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    node_ids: list[int] = Field(default_factory=list)
    strategy_node_ids: list[int] = Field(default_factory=list)
    protocol_types: list[str] = Field(default_factory=list)
    health_check_url: str = "http://www.gstatic.com/generate_204"
    health_check_interval: int = 300
    tolerance: int = 50
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    ip_whitelist: list[str] = Field(default_factory=list)
    traffic_guard_enabled: bool | None = None
    min_remaining_mb: int | None = None
    low_remaining_mb: int | None = None
    expire_soon_days: int | None = None
    exclude_unknown_traffic: bool | None = None
    enabled: bool = True


class SmartProxyCreate(SmartProxyBase):
    pass


class SmartProxyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    proxy_type: str | None = None
    listen_host: str | None = None
    port: int | None = None
    strategy: str | None = None
    stability_priority: bool | None = None
    scenario: str | None = None
    source_mode: str | None = None
    subscription_ids: list[int] | None = None
    country_codes: list[str] | None = None
    tags: list[str] | None = None
    node_ids: list[int] | None = None
    strategy_node_ids: list[int] | None = None
    protocol_types: list[str] | None = None
    health_check_url: str | None = None
    health_check_interval: int | None = None
    tolerance: int | None = None
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    ip_whitelist: list[str] | None = None
    traffic_guard_enabled: bool | None = None
    min_remaining_mb: int | None = None
    low_remaining_mb: int | None = None
    expire_soon_days: int | None = None
    exclude_unknown_traffic: bool | None = None
    enabled: bool | None = None


class SmartProxyRead(SmartProxyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    port: int
    status: str
    current_node: str | None = None
    switch_count: int = 0
    last_error: str | None = None
    last_applied_at: datetime | None = None
    config_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    endpoint: str = ""
    candidate_nodes: int = 0
    runtime_apply_error: str | None = None
    apply_status: str = "pending"
    apply_status_reason: str | None = None


class SmartProxyRuntime(BaseModel):
    config_path: str
    enabled_services: int
    proxies: int
    proxy_groups: int
    listeners: int
    reloaded: bool = False
    error: str | None = None
    content: str | None = None


class SmartProxyGlobalConfig(BaseModel):
    smart_proxy_port_start: int
    smart_proxy_port_end: int
    smart_proxy_auto_apply_interval_minutes: int
    smart_proxy_monitor_interval_minutes: int
    mihomo_api_url: str
    mihomo_api_secret: str = ""
    mihomo_runtime_config_path: str
    mihomo_core_config_path: str
    traffic_guard_enabled: bool
    min_remaining_mb: int
    low_remaining_mb: int
    expire_soon_days: int
    exclude_unknown_traffic: bool
    runtime_apply_error: str | None = None


class SmartProxyGlobalConfigUpdate(BaseModel):
    smart_proxy_auto_apply_interval_minutes: int | None = None
    smart_proxy_monitor_interval_minutes: int | None = None
    mihomo_api_url: str | None = None
    mihomo_api_secret: str | None = None
    mihomo_runtime_config_path: str | None = None
    mihomo_core_config_path: str | None = None
    traffic_guard_enabled: bool | None = None
    min_remaining_mb: int | None = None
    low_remaining_mb: int | None = None
    expire_soon_days: int | None = None
    exclude_unknown_traffic: bool | None = None


class SmartProxyPreset(BaseModel):
    key: str
    name: str
    description: str
    proxy_type: str = "mixed"
    strategy: str = "fallback"
    stability_priority: bool = False
    scenario: str = "general"
    source_mode: str = "country"
    country_codes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    protocol_types: list[str] = Field(default_factory=list)
    health_check_url: str = "http://www.gstatic.com/generate_204"
    health_check_interval: int = 300
    tolerance: int = 50


class SmartProxyCountryOption(BaseModel):
    code: str
    name: str | None = None
    nodes: int = 0


class SmartProxySubscriptionOption(BaseModel):
    id: int
    name: str
    group_name: str
    enabled: bool
    nodes: int = 0


class SmartProxyMetadata(BaseModel):
    countries: list[SmartProxyCountryOption] = Field(default_factory=list)
    subscriptions: list[SmartProxySubscriptionOption] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    protocol_types: list[str] = Field(default_factory=list)
    presets: list[SmartProxyPreset] = Field(default_factory=list)


class SmartProxyConfig(BaseModel):
    proxy_id: int
    use_global_traffic_policy: bool = True
    traffic_guard_enabled: bool | None = None
    min_remaining_mb: int | None = None
    low_remaining_mb: int | None = None
    expire_soon_days: int | None = None
    exclude_unknown_traffic: bool | None = None
    effective_traffic_guard_enabled: bool
    effective_min_remaining_mb: int
    effective_low_remaining_mb: int
    effective_expire_soon_days: int
    effective_exclude_unknown_traffic: bool
    runtime_apply_error: str | None = None


class SmartProxyConfigUpdate(BaseModel):
    use_global_traffic_policy: bool = True
    traffic_guard_enabled: bool | None = None
    min_remaining_mb: int | None = None
    low_remaining_mb: int | None = None
    expire_soon_days: int | None = None
    exclude_unknown_traffic: bool | None = None


class MihomoCoreStatus(BaseModel):
    api_url: str
    available: bool
    version: str | None = None
    active_connections: int = 0
    download_total: int = 0
    upload_total: int = 0
    download_speed: int = 0
    upload_speed: int = 0
    memory: int | None = None
    error: str | None = None


class SmartProxyStatus(BaseModel):
    proxy_id: int
    name: str
    endpoint: str
    group_name: str
    enabled: bool
    core_available: bool
    status: str
    current_node: str | None = None
    candidate_nodes: int = 0
    runtime_nodes: int = 0
    online_nodes: int = 0
    failed_nodes: int = 0
    average_delay: int | None = None
    best_node: str | None = None
    active_connections: int = 0
    online_users: int = 0
    source_ips: list[str] = Field(default_factory=list)
    upload_total: int = 0
    download_total: int = 0
    upload_speed: int = 0
    download_speed: int = 0
    unauthorized_connections: int = 0
    switch_count: int = 0
    traffic_guard_enabled: bool = False
    traffic_excluded_nodes: int = 0
    traffic_risk_nodes: int = 0
    traffic_unknown_nodes: int = 0
    traffic_snapshot_at: datetime | None = None
    traffic_reasons: list[str] = Field(default_factory=list)
    delay: int | None = None
    history: list[dict] = Field(default_factory=list)
    error: str | None = None


class SmartProxyAccessViolation(BaseModel):
    proxy_id: int
    proxy_name: str
    connection_id: str
    source_ip: str | None = None
    destination: str | None = None


class SmartProxyAccessEnforceResult(BaseModel):
    checked_connections: int = 0
    closed_connections: int = 0
    violations: list[SmartProxyAccessViolation] = Field(default_factory=list)


class SmartProxyNodeHealth(BaseModel):
    node_id: int | None = None
    name: str
    source: str | None = None
    type: str | None = None
    status: str
    delay: int | None = None
    current: bool = False
    error: str | None = None


class SmartProxyHealthCheck(BaseModel):
    check_type: str
    status: str
    delay: int | None = None
    message: str | None = None


class SmartProxyHealthResult(BaseModel):
    proxy_id: int
    name: str
    group_name: str
    checked_at: datetime
    status: str
    total_nodes: int
    online_nodes: int
    failed_nodes: int
    average_delay: int | None = None
    best_node: str | None = None
    current_node: str | None = None
    nodes: list[SmartProxyNodeHealth] = Field(default_factory=list)
    checks: list[SmartProxyHealthCheck] = Field(default_factory=list)
    error: str | None = None


class SmartProxyHealthLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    smart_proxy_id: int
    node_id: int | None = None
    node_name: str | None = None
    check_type: str
    status: str
    latency: int | None = None
    message: str | None = None
    created_at: datetime


class SmartProxySwitchLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    smart_proxy_id: int
    from_node: str | None = None
    to_node: str
    reason: str | None = None
    created_at: datetime
