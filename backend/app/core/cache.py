import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


settings = get_settings()
redis_client: Redis | None = None
logger = logging.getLogger(__name__)


def get_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis_client


async def cache_get_json(key: str) -> Any | None:
    try:
        value = await get_redis().get(key)
    except RedisError as exc:
        logger.warning("Redis cache read skipped for %s: %s", key, exc)
        return None
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


async def cache_set_json(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        await get_redis().set(key, json.dumps(value, ensure_ascii=False), ex=ttl or settings.CACHE_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("Redis cache write skipped for %s: %s", key, exc)


async def cache_get_text(key: str) -> str | None:
    try:
        return await get_redis().get(key)
    except RedisError as exc:
        logger.warning("Redis cache read skipped for %s: %s", key, exc)
        return None


async def cache_set_text(key: str, value: str, ttl: int | None = None) -> None:
    try:
        await get_redis().set(key, value, ex=ttl or settings.CACHE_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("Redis cache write skipped for %s: %s", key, exc)


async def cache_delete_prefixes(*prefixes: str) -> int:
    deleted = 0
    if not prefixes:
        return deleted
    try:
        redis = get_redis()
        for prefix in prefixes:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=f"{prefix}*", count=500)
                if keys:
                    deleted += await redis.delete(*keys)
                if cursor == 0:
                    break
    except RedisError as exc:
        logger.warning("Redis cache delete skipped for prefixes %s: %s", prefixes, exc)
    return deleted


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
