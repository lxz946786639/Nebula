from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node import Node


@dataclass(slots=True)
class NodeLatencyTestResult:
    total_nodes: int
    tested_nodes: int
    online_nodes: int
    failed_nodes: int


@dataclass(slots=True)
class _LatencyTarget:
    id: int
    server: str
    port: int


def _parse_port(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 0 < port < 65536 else None


async def _tcp_latency_ms(target: _LatencyTarget, timeout_seconds: float, sem: asyncio.Semaphore) -> tuple[int, int | None]:
    async with sem:
        start = time.perf_counter()
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target.server, target.port),
                timeout=timeout_seconds,
            )
            writer.close()
            await writer.wait_closed()
        except Exception:
            return target.id, None
        latency = max(1, int((time.perf_counter() - start) * 1000))
        return target.id, latency


async def test_node_latencies(
    session: AsyncSession,
    *,
    group: str | None = None,
    enabled: bool | None = True,
    timeout_ms: int = 3000,
    concurrency: int = 30,
) -> NodeLatencyTestResult:
    stmt = select(Node)
    if group:
        stmt = stmt.where(Node.source_group == group)
    if enabled is not None:
        stmt = stmt.where(Node.enabled.is_(enabled))
    nodes = list((await session.scalars(stmt.order_by(Node.id.asc()))).all())

    targets: list[_LatencyTarget] = []
    for node in nodes:
        port = _parse_port(node.port)
        if node.server and port is not None:
            targets.append(_LatencyTarget(id=node.id, server=node.server, port=port))

    if not targets:
        return NodeLatencyTestResult(total_nodes=len(nodes), tested_nodes=0, online_nodes=0, failed_nodes=len(nodes))

    timeout_seconds = max(300, min(timeout_ms, 15000)) / 1000
    sem = asyncio.Semaphore(max(1, min(concurrency, 100)))
    measurements = await asyncio.gather(*(_tcp_latency_ms(target, timeout_seconds, sem) for target in targets))
    latency_by_id = dict(measurements)

    online_nodes = 0
    for node in nodes:
        if node.id in latency_by_id:
            node.latency = latency_by_id[node.id]
            if node.latency is not None:
                online_nodes += 1
        else:
            node.latency = None

    await session.commit()
    return NodeLatencyTestResult(
        total_nodes=len(nodes),
        tested_nodes=len(targets),
        online_nodes=online_nodes,
        failed_nodes=len(nodes) - online_nodes,
    )
