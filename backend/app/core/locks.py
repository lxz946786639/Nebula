import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


_locks: dict[str, asyncio.Lock] = {}


def _lock_for(name: str) -> asyncio.Lock:
    lock = _locks.get(name)
    if lock is None:
        lock = asyncio.Lock()
        _locks[name] = lock
    return lock


@asynccontextmanager
async def exclusive_lock(name: str) -> AsyncIterator[None]:
    async with _lock_for(name):
        yield
