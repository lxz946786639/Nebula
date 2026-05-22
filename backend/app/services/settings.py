from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.system_setting import SystemSetting

LEGACY_PUBLIC_BASE_URL_KEY = "public_base_url"
SUBSCRIPTION_PUBLIC_BASE_URL_KEY = "subscription_public_base_url"
PROXY_PUBLIC_BASE_URL_KEY = "proxy_public_base_url"


def normalize_public_base_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return raw.rstrip("/")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return raw.rstrip("/")
    host = parsed.hostname
    if not host:
        return raw.rstrip("/")
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        port = parsed.port
    except ValueError:
        return raw.rstrip("/")
    netloc = f"{host_part}:{port}" if port else host_part
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def public_host_port_from_base_url(value: str | None) -> tuple[str | None, int | None]:
    normalized = normalize_public_base_url(value)
    if not normalized:
        return None, None
    try:
        parsed = urlsplit(normalized)
        return parsed.hostname, parsed.port
    except ValueError:
        return None, None


def public_host_base_from_base_url(value: str | None) -> str:
    normalized = normalize_public_base_url(value)
    if not normalized:
        return ""
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        return ""
    host = parsed.hostname
    if not host:
        return ""
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return urlunsplit((parsed.scheme, host_part, "", "", ""))


async def get_setting(session: AsyncSession, key: str, fallback: str | None = None) -> str | None:
    item = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return item.value if item is not None else fallback


async def get_public_base_url(session: AsyncSession) -> str:
    return await get_subscription_public_base_url(session)


async def get_subscription_public_base_url(session: AsyncSession) -> str:
    value = await get_setting(session, SUBSCRIPTION_PUBLIC_BASE_URL_KEY, "")
    if not str(value or "").strip():
        value = await get_setting(session, LEGACY_PUBLIC_BASE_URL_KEY, "")
    return normalize_public_base_url(value)


async def get_proxy_public_base_url(session: AsyncSession) -> str:
    value = await get_setting(session, PROXY_PUBLIC_BASE_URL_KEY, "")
    if not str(value or "").strip():
        value = await get_setting(session, LEGACY_PUBLIC_BASE_URL_KEY, "")
        return public_host_base_from_base_url(value)
    return normalize_public_base_url(value)


async def get_subconverter_url(session: AsyncSession) -> str:
    settings = get_settings()
    if settings.APP_ENV == "development":
        return settings.subconverter_base_url
    value = await get_setting(session, "subconverter_url", settings.subconverter_base_url)
    return (value or settings.subconverter_base_url).rstrip("/")


async def get_subscription_token(session: AsyncSession) -> str:
    settings = get_settings()
    return await get_setting(session, "subscription_token", settings.SUBSCRIPTION_TOKEN) or settings.SUBSCRIPTION_TOKEN


async def get_cache_ttl(session: AsyncSession) -> int:
    settings = get_settings()
    value = await get_setting(session, "cache_ttl_seconds", str(settings.CACHE_TTL_SECONDS))
    try:
        return int(value or settings.CACHE_TTL_SECONDS)
    except ValueError:
        return settings.CACHE_TTL_SECONDS


async def get_node_filter_patterns(session: AsyncSession) -> list[str]:
    value = await get_setting(session, "node_filter_patterns", "")
    return [item.strip() for item in (value or "").split(",") if item.strip()]


async def get_traffic_poll_interval_minutes(session: AsyncSession) -> int:
    value = await get_setting(session, "traffic_poll_interval_minutes", "30")
    try:
        interval = int(value or "30")
    except ValueError:
        return 30
    return max(interval, 0)


async def get_int_setting(session: AsyncSession, key: str, fallback: int) -> int:
    value = await get_setting(session, key, str(fallback))
    try:
        return int(value or fallback)
    except ValueError:
        return fallback


async def get_bool_setting(session: AsyncSession, key: str, fallback: bool) -> bool:
    value = await get_setting(session, key, "true" if fallback else "false")
    if value is None:
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


async def get_smart_proxy_port_range(session: AsyncSession) -> tuple[int, int]:
    settings = get_settings()
    start = settings.SMART_PROXY_PORT_START
    end = settings.SMART_PROXY_PORT_END
    if end < start:
        return settings.SMART_PROXY_PORT_START, settings.SMART_PROXY_PORT_END
    return start, end


async def get_ant_proxy_auto_refresh_enabled(session: AsyncSession) -> bool:
    settings = get_settings()
    return await get_bool_setting(session, "ant_proxy_auto_refresh_enabled", settings.ANT_PROXY_AUTO_REFRESH_ENABLED)


async def get_ant_proxy_auto_refresh_interval_minutes(session: AsyncSession) -> int:
    settings = get_settings()
    return max(
        await get_int_setting(
            session,
            "ant_proxy_auto_refresh_interval_minutes",
            settings.ANT_PROXY_AUTO_REFRESH_INTERVAL_MINUTES,
        ),
        0,
    )


async def get_mihomo_api_url(session: AsyncSession) -> str:
    settings = get_settings()
    if settings.APP_ENV == "development":
        return settings.MIHOMO_API_URL.rstrip("/")
    value = await get_setting(session, "mihomo_api_url", settings.MIHOMO_API_URL)
    return (value or settings.MIHOMO_API_URL).rstrip("/")


async def get_mihomo_api_secret(session: AsyncSession) -> str:
    settings = get_settings()
    if settings.APP_ENV == "development":
        return settings.MIHOMO_API_SECRET
    return await get_setting(session, "mihomo_api_secret", settings.MIHOMO_API_SECRET) or settings.MIHOMO_API_SECRET


async def get_mihomo_runtime_config_path(session: AsyncSession) -> str:
    settings = get_settings()
    return (
        await get_setting(session, "mihomo_runtime_config_path", settings.MIHOMO_RUNTIME_CONFIG_PATH)
        or settings.MIHOMO_RUNTIME_CONFIG_PATH
    )


async def get_mihomo_core_config_path(session: AsyncSession) -> str:
    settings = get_settings()
    return await get_setting(session, "mihomo_core_config_path", settings.MIHOMO_CORE_CONFIG_PATH) or settings.MIHOMO_CORE_CONFIG_PATH


async def get_mihomo_proxy_server_nameservers(session: AsyncSession) -> list[str]:
    settings = get_settings()
    value = await get_setting(
        session,
        "mihomo_proxy_server_nameservers",
        settings.MIHOMO_PROXY_SERVER_NAMESERVERS,
    )
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


async def get_smart_proxy_auto_apply_interval_minutes(session: AsyncSession) -> int:
    settings = get_settings()
    return max(
        await get_int_setting(
            session,
            "smart_proxy_auto_apply_interval_minutes",
            settings.SMART_PROXY_AUTO_APPLY_INTERVAL_MINUTES,
        ),
        0,
    )


async def get_smart_proxy_monitor_interval_minutes(session: AsyncSession) -> int:
    settings = get_settings()
    return max(
        await get_int_setting(
            session,
            "smart_proxy_monitor_interval_minutes",
            settings.SMART_PROXY_MONITOR_INTERVAL_MINUTES,
        ),
        0,
    )


async def get_smart_proxy_traffic_guard_enabled(session: AsyncSession) -> bool:
    settings = get_settings()
    return await get_bool_setting(session, "smart_proxy_traffic_guard_enabled", settings.SMART_PROXY_TRAFFIC_GUARD_ENABLED)


async def get_smart_proxy_min_remaining_mb(session: AsyncSession) -> int:
    settings = get_settings()
    return max(await get_int_setting(session, "smart_proxy_min_remaining_mb", settings.SMART_PROXY_MIN_REMAINING_MB), 0)


async def get_smart_proxy_low_remaining_mb(session: AsyncSession) -> int:
    settings = get_settings()
    return max(await get_int_setting(session, "smart_proxy_low_remaining_mb", settings.SMART_PROXY_LOW_REMAINING_MB), 0)


async def get_smart_proxy_expire_soon_days(session: AsyncSession) -> int:
    settings = get_settings()
    return max(await get_int_setting(session, "smart_proxy_expire_soon_days", settings.SMART_PROXY_EXPIRE_SOON_DAYS), 0)


async def get_smart_proxy_exclude_unknown_traffic(session: AsyncSession) -> bool:
    settings = get_settings()
    return await get_bool_setting(
        session,
        "smart_proxy_exclude_unknown_traffic",
        settings.SMART_PROXY_EXCLUDE_UNKNOWN_TRAFFIC,
    )
