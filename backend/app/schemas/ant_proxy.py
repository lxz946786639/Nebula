from datetime import datetime

from pydantic import BaseModel, Field


class AntProxyUser(BaseModel):
    logged_in: bool = False
    oauth_id: str = ""
    uuid: str = ""
    bind_phone: str = ""
    username: str = ""
    aff_present: bool = False
    vip_day: int = 0
    expire_description: str = ""
    is_sign: int = 0
    website_url: str = ""
    ip: str = ""


class AntProxyNode(BaseModel):
    id: str
    source: str
    group: str
    name: str
    city: str = ""
    country: str = ""
    country_code: str = ""
    pay_type: str = ""
    line_type: str = "free"
    line_label: str = "免费专线"
    online_connections: int | None = None
    status: int | None = None
    latency_ms: int | None = None
    server: str
    port: int
    cipher: str
    transport: str
    tls: bool
    selected: bool = False


class AntProxyStatus(BaseModel):
    db_path: str
    db_exists: bool
    db_filename: str = ""
    source_type: str = "none"
    source_label: str = "未加载"
    client_id: str = ""
    api_url: str = ""
    app_version: str = "2.0.9"
    loaded: bool
    logged_in: bool
    user: AntProxyUser = Field(default_factory=AntProxyUser)
    node_count: int = 0
    free_node_count: int = 0
    paid_node_count: int = 0
    selected_node: AntProxyNode | None = None
    running: bool = False
    listen_host: str = "127.0.0.1"
    listen_port: int = 37890
    endpoint: str = "socks5://127.0.0.1:37890"
    runtime_mode: str = "mihomo"
    mihomo_group: str = ""
    adapter_count: int = 0
    health_check_url: str = "http://www.gstatic.com/generate_204"
    health_check_interval: int = 300
    tolerance: int = 100
    active_connections: int = 0
    total_connections: int = 0
    source_ip_count: int = 0
    upload_bytes: int = 0
    download_bytes: int = 0
    started_at: datetime | None = None
    last_loaded_at: datetime | None = None
    last_latency_tested_at: datetime | None = None
    persisted: bool = False
    last_persisted_at: datetime | None = None
    last_error: str | None = None


class AntProxyNodeList(BaseModel):
    total: int
    free_total: int = 0
    paid_total: int = 0
    items: list[AntProxyNode] = Field(default_factory=list)


class AntProxyRefreshRequest(BaseModel):
    db_path: str | None = None
    line_type: str | None = None


class AntProxyScheduleConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = 360
    last_refreshed_at: datetime | None = None
    next_refresh_at: datetime | None = None


class AntProxyScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=0, le=43200)


class AntProxyTrafficPeriod(BaseModel):
    key: str
    label: str
    upload: int = 0
    download: int = 0
    total: int = 0


class AntProxyTrafficBucket(BaseModel):
    at: datetime
    label: str
    upload: int = 0
    download: int = 0
    total: int = 0


class AntProxyTrafficSummary(BaseModel):
    upload_total: int = 0
    download_total: int = 0
    total: int = 0
    current_upload_speed: int = 0
    current_download_speed: int = 0
    peak_upload_speed: int = 0
    peak_download_speed: int = 0
    active_connections: int = 0
    total_connections: int = 0
    source_ip_count: int = 0
    sample_count: int = 0
    sampled_from: datetime | None = None
    sampled_to: datetime | None = None
    periods: list[AntProxyTrafficPeriod] = Field(default_factory=list)
    trend_granularity: str = "hour"
    trend: list[AntProxyTrafficBucket] = Field(default_factory=list)


class AntProxyLoginRequest(BaseModel):
    username: str
    password: str
    app_version: str = "2.0.9"


class AntProxySelectRequest(BaseModel):
    node_id: str


class AntProxyStartRequest(BaseModel):
    node_id: str | None = None
    listen_host: str = "127.0.0.1"
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    health_check_url: str = "http://www.gstatic.com/generate_204"
    health_check_interval: int = Field(default=300, ge=30, le=86400)
    tolerance: int = Field(default=100, ge=0, le=10000)


class AntProxyTestRequest(BaseModel):
    url: str = "http://www.gstatic.com/generate_204"
    timeout: float = Field(default=15, ge=1, le=60)


class AntProxyTestResult(BaseModel):
    ok: bool
    status_code: int = 0
    first_line: str = ""
    elapsed_ms: int = 0


class AntProxyLatencyRequest(BaseModel):
    line_type: str | None = None
    timeout_ms: int = Field(default=5000, ge=300, le=15000)
    concurrency: int = Field(default=20, ge=1, le=100)


class AntProxyLatencyResult(BaseModel):
    total: int
    online: int
    failed: int
    elapsed_ms: int = 0
    items: list[AntProxyNode] = Field(default_factory=list)
