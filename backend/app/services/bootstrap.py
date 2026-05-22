from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.config_template import ConfigTemplate
from app.models.rule_template import RuleTemplate
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.settings import public_host_base_from_base_url


async def bootstrap_defaults(session: AsyncSession) -> None:
    settings = get_settings()

    user = await session.scalar(select(User).where(User.username == settings.ADMIN_USERNAME))
    if user is None:
        session.add(
            User(
                username=settings.ADMIN_USERNAME,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
        )

    default_rule = await session.scalar(select(RuleTemplate).where(RuleTemplate.name == "ACL4SSR Online"))
    if default_rule is None:
        session.add(
            RuleTemplate(
                name="ACL4SSR Online",
                description="Default ACL4SSR remote profile used by subconverter.",
                remote_config_url=settings.ACL4SSR_CONFIG_URL,
                is_default=True,
            )
        )

    default_template = await session.scalar(select(ConfigTemplate).where(ConfigTemplate.name == "Default Mihomo"))
    if default_template is None:
        session.add(
            ConfigTemplate(
                name="Default Mihomo",
                target="clashmeta",
                config_url=settings.ACL4SSR_CONFIG_URL,
                is_default=True,
            )
        )

    legacy_public_base_url = await session.scalar(select(SystemSetting).where(SystemSetting.key == "public_base_url"))
    legacy_public_base_url_value = legacy_public_base_url.value if legacy_public_base_url is not None else ""
    legacy_proxy_public_base_url_value = public_host_base_from_base_url(legacy_public_base_url_value)

    defaults = {
        "redis_url": (settings.REDIS_URL, False, "Redis connection URL"),
        "subscription_public_base_url": (
            legacy_public_base_url_value or "",
            False,
            "Public base URL used for displayed subscription addresses",
        ),
        "proxy_public_base_url": (
            legacy_proxy_public_base_url_value,
            False,
            "Public host or base URL used for displayed smart proxy addresses",
        ),
        "subconverter_url": (settings.subconverter_base_url, False, "subconverter HTTP API base URL"),
        "acl4ssr_config_url": (settings.ACL4SSR_CONFIG_URL, False, "Default ACL4SSR remote config URL"),
        "subscription_token": (settings.SUBSCRIPTION_TOKEN, True, "Token used by public subscription endpoints"),
        "cache_ttl_seconds": (str(settings.CACHE_TTL_SECONDS), False, "Final config cache TTL"),
        "node_filter_patterns": ("", False, "Comma-separated wildcard patterns used to skip pseudo nodes by name"),
        "traffic_poll_interval_minutes": ("30", False, "Subscription traffic polling interval in minutes; 0 disables it"),
        "ant_proxy_auto_refresh_enabled": (
            "true" if settings.ANT_PROXY_AUTO_REFRESH_ENABLED else "false",
            False,
            "Whether Ant account nodes should refresh in the background",
        ),
        "ant_proxy_auto_refresh_interval_minutes": (
            str(settings.ANT_PROXY_AUTO_REFRESH_INTERVAL_MINUTES),
            False,
            "Ant account node background refresh interval in minutes",
        ),
        "smart_proxy_auto_apply_interval_minutes": (
            str(settings.SMART_PROXY_AUTO_APPLY_INTERVAL_MINUTES),
            False,
            "Optional scheduled full Mihomo runtime re-apply interval in minutes; 0 disables it",
        ),
        "smart_proxy_monitor_interval_minutes": (
            str(settings.SMART_PROXY_MONITOR_INTERVAL_MINUTES),
            False,
            "Interval for syncing smart proxy runtime status from Mihomo; 0 disables it",
        ),
        "smart_proxy_traffic_guard_enabled": (
            "true" if settings.SMART_PROXY_TRAFFIC_GUARD_ENABLED else "false",
            False,
            "Whether smart proxies exclude expired/exhausted subscription nodes during runtime generation",
        ),
        "smart_proxy_min_remaining_mb": (
            str(settings.SMART_PROXY_MIN_REMAINING_MB),
            False,
            "Minimum remaining subscription traffic in MB before nodes are excluded",
        ),
        "smart_proxy_low_remaining_mb": (
            str(settings.SMART_PROXY_LOW_REMAINING_MB),
            False,
            "Remaining traffic threshold in MB for deprioritizing smart proxy nodes",
        ),
        "smart_proxy_expire_soon_days": (
            str(settings.SMART_PROXY_EXPIRE_SOON_DAYS),
            False,
            "Days before subscription expiry for deprioritizing smart proxy nodes",
        ),
        "smart_proxy_exclude_unknown_traffic": (
            "true" if settings.SMART_PROXY_EXCLUDE_UNKNOWN_TRAFFIC else "false",
            False,
            "Whether smart proxies exclude nodes from subscriptions without traffic headers",
        ),
        "mihomo_api_url": (settings.MIHOMO_API_URL, False, "Mihomo external controller API URL"),
        "mihomo_api_secret": (settings.MIHOMO_API_SECRET, True, "Mihomo external controller API bearer token"),
        "mihomo_runtime_config_path": (settings.MIHOMO_RUNTIME_CONFIG_PATH, False, "Path where Nebula writes Mihomo runtime config"),
        "mihomo_core_config_path": (
            settings.MIHOMO_CORE_CONFIG_PATH,
            False,
            "Path of the same runtime config as seen by the Mihomo process/container",
        ),
        "mihomo_proxy_server_nameservers": (
            settings.MIHOMO_PROXY_SERVER_NAMESERVERS,
            False,
            "Comma-separated DNS servers for resolving Mihomo proxy server hostnames",
        ),
    }
    dev_synced_keys = {
        "redis_url",
        "subconverter_url",
        "mihomo_api_url",
        "mihomo_runtime_config_path",
        "mihomo_core_config_path",
        "mihomo_proxy_server_nameservers",
    }
    for key, (value, secret, description) in defaults.items():
        existing = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if existing is None:
            session.add(SystemSetting(key=key, value=value, secret=secret, description=description))
        elif settings.APP_ENV == "development" and key in dev_synced_keys:
            existing.value = value
            existing.description = description

    await session.commit()
