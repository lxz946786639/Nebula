import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get_json, cache_get_text, cache_set_json, cache_set_text
from app.core.timezone import now_china
from app.models.config_template import ConfigTemplate
from app.models.node_snapshot import NodeSnapshot
from app.models.subscription import Subscription
from app.services.node_pool import sync_node_pool
from app.services.node_processor import process_clash_yaml
from app.services.settings import get_cache_ttl, get_subconverter_url
from app.services.subconverter import ConvertRequest, SubconverterClient, SubconverterError, Target
from app.utils.network import validate_subscription_url


TARGET_BY_API = {
    "clash": "clash",
    "mihomo": "clash",
    "clashmeta": "clash",
    "singbox": "singbox",
    "v2ray": "v2ray",
}


def build_cache_key(*parts: str | None) -> str:
    raw = "|".join(part or "" for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def list_source_urls(session: AsyncSession, group: str | None = None) -> list[str]:
    stmt = select(Subscription).where(Subscription.enabled.is_(True)).order_by(Subscription.priority.asc(), Subscription.id.asc())
    if group:
        stmt = stmt.where(Subscription.group_name == group)
    result = await session.scalars(stmt)
    subscriptions = result.all()
    urls: list[str] = []
    for subscription in subscriptions:
        await validate_subscription_url(subscription.url)
        urls.append(subscription.url)
    return urls


async def find_template_config_url(session: AsyncSession, template: str | None, target: str) -> str | None:
    stmt = select(ConfigTemplate).where(ConfigTemplate.target.in_([target, "clashmeta", "clash"]))
    if template:
        stmt = stmt.where(ConfigTemplate.name == template)
    else:
        stmt = stmt.where(ConfigTemplate.is_default.is_(True))
    item = await session.scalar(stmt.order_by(ConfigTemplate.id.asc()))
    return item.config_url if item is not None else None


async def convert_subscription(
    session: AsyncSession,
    *,
    api_target: str,
    group: str | None,
    template: str | None,
    emoji: bool,
    bypass_cache: bool = False,
) -> tuple[str, list[dict]]:
    target = TARGET_BY_API.get(api_target)
    if target is None:
        raise ValueError("Unsupported target")

    urls = await list_source_urls(session, group)
    config_url = await find_template_config_url(session, template, target)
    ttl = await get_cache_ttl(session)
    cache_key = build_cache_key(target, group, template, str(emoji), "|".join(urls), config_url)
    final_cache_key = f"sub:final:{cache_key}"
    nodes_cache_key = f"sub:nodes:{cache_key}"

    if not bypass_cache:
        cached = await cache_get_text(final_cache_key)
        cached_nodes = await cache_get_json(nodes_cache_key)
        if cached is not None and cached_nodes is not None:
            return cached, cached_nodes

    client = SubconverterClient(await get_subconverter_url(session))
    converted = await client.convert(ConvertRequest(target=target, urls=urls, config_url=config_url, emoji=emoji))  # type: ignore[arg-type]
    nodes: list[dict] = []

    if target in {"clash", "clashmeta"}:
        converted, nodes = process_clash_yaml(converted, emoji=emoji)

    await cache_set_text(final_cache_key, converted, ttl)
    await cache_set_json(nodes_cache_key, nodes, ttl)
    session.add(NodeSnapshot(cache_key=cache_key, target=target, group_name=group, total_nodes=len(nodes), nodes=nodes))
    await session.commit()
    return converted, nodes


async def refresh_subscription_source(
    session: AsyncSession,
    subscription: Subscription,
    *,
    audit_actor: str = "system",
) -> None:
    if not subscription.enabled:
        await validate_subscription_url(subscription.url)
        subscription.last_status = "disabled"
        subscription.last_error = None
        subscription.last_updated_at = now_china()
        await session.commit()
        return
    result = await sync_node_pool(
        session,
        subscription_id=subscription.id,
        audit_actor=audit_actor,
        audit_reason=f"刷新订阅「{subscription.name}」",
    )
    if result.failed_subscriptions:
        raise SubconverterError("; ".join(result.errors))
