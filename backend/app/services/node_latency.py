from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from collections.abc import Sequence

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
class NodeLatencyCheckResult(NodeLatencyTestResult):
    online_node_ids: list[int]
    failed_node_ids: list[int]


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
    result = await test_selected_node_latencies(
        session,
        nodes,
        timeout_ms=timeout_ms,
        concurrency=concurrency,
    )
    await session.commit()
    return NodeLatencyTestResult(
        total_nodes=result.total_nodes,
        tested_nodes=result.tested_nodes,
        online_nodes=result.online_nodes,
        failed_nodes=result.failed_nodes,
    )


async def test_selected_node_latencies(
    session: AsyncSession,
    nodes: Sequence[Node],
    *,
    timeout_ms: int = 3000,
    concurrency: int = 30,
) -> NodeLatencyCheckResult:
    targets: list[_LatencyTarget] = []
    for node in nodes:
        port = _parse_port(node.port)
        if node.server and port is not None:
            targets.append(_LatencyTarget(id=node.id, server=node.server, port=port))

    if not targets:
        failed_ids = [node.id for node in nodes if node.id is not None]
        return NodeLatencyCheckResult(
            total_nodes=len(nodes),
            tested_nodes=0,
            online_nodes=0,
            failed_nodes=len(nodes),
            online_node_ids=[],
            failed_node_ids=failed_ids,
        )

    timeout_seconds = max(300, min(timeout_ms, 15000)) / 1000
    sem = asyncio.Semaphore(max(1, min(concurrency, 100)))
    measurements = await asyncio.gather(*(_tcp_latency_ms(target, timeout_seconds, sem) for target in targets))
    latency_by_id = dict(measurements)

    online_nodes = 0
    online_node_ids: list[int] = []
    failed_node_ids: list[int] = []
    for node in nodes:
        if node.id in latency_by_id:
            node.latency = latency_by_id[node.id]
            if node.latency is not None:
                online_nodes += 1
                online_node_ids.append(node.id)
            else:
                failed_node_ids.append(node.id)
        else:
            node.latency = None
            if node.id is not None:
                failed_node_ids.append(node.id)

    return NodeLatencyCheckResult(
        total_nodes=len(nodes),
        tested_nodes=len(targets),
        online_nodes=online_nodes,
        failed_nodes=len(nodes) - online_nodes,
        online_node_ids=online_node_ids,
        failed_node_ids=failed_node_ids,
    )
