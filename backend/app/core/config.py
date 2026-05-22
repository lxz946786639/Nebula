from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR / ".env.development"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Nebula Subscriptions"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api"
    ALLOW_INSECURE_DEFAULTS: bool = False

    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123456"
    SUBSCRIPTION_TOKEN: str = "nebula-sub-token"

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/nebula.db"
    SQL_ECHO: bool = False
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    CACHE_TTL_SECONDS: int = 600

    SUBCONVERTER_URL: AnyHttpUrl | str = "http://127.0.0.1:25500"
    SUBCONVERTER_TIMEOUT_SECONDS: int = 45
    ACL4SSR_CONFIG_URL: str = (
        "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/config/ACL4SSR_Online.ini"
    )
    MIHOMO_API_URL: str = "http://127.0.0.1:9090"
    MIHOMO_API_SECRET: str = ""
    MIHOMO_RUNTIME_CONFIG_PATH: str = "./data/mihomo-runtime.yaml"
    MIHOMO_CORE_CONFIG_PATH: str = "./data/mihomo-runtime.yaml"
    ANT_PROXY_STATE_PATH: str = "./data/ant-proxy-state.json"
    ANT_ADAPTER_BIND_HOST: str = ""
    ANT_ADAPTER_CONNECT_HOST: str = ""
    ANT_PROXY_AUTO_REFRESH_ENABLED: bool = True
    ANT_PROXY_AUTO_REFRESH_INTERVAL_MINUTES: int = 360
    SMART_PROXY_PORT_START: int = 37890
    SMART_PROXY_PORT_END: int = 37900
    SMART_PROXY_AUTO_APPLY_INTERVAL_MINUTES: int = 0
    SMART_PROXY_MONITOR_INTERVAL_MINUTES: int = 1
    SMART_PROXY_TRAFFIC_GUARD_ENABLED: bool = True
    SMART_PROXY_MIN_REMAINING_MB: int = 0
    SMART_PROXY_LOW_REMAINING_MB: int = 2048
    SMART_PROXY_EXPIRE_SOON_DAYS: int = 3
    SMART_PROXY_EXCLUDE_UNKNOWN_TRAFFIC: bool = False

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8088"
    URL_ALLOWLIST: str = ""
    URL_BLOCK_PRIVATE_NETWORKS: bool = True

    RATE_LIMIT_REQUESTS: int = 180
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = True

    @property
    def subconverter_base_url(self) -> str:
        return str(self.SUBCONVERTER_URL).rstrip("/")

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def url_allowlist_list(self) -> list[str]:
        return [item.strip().lower() for item in self.URL_ALLOWLIST.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
