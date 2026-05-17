import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = get_settings()
        self.buckets: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        if self.settings.RATE_LIMIT_TRUST_PROXY_HEADERS:
            real_ip = request.headers.get("x-real-ip")
            if real_ip:
                return real_ip.strip()
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                return forwarded_for.split(",", 1)[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in {"/health", "/api/health"}:
            return await call_next(request)

        now = time.monotonic()
        client_ip = self._client_ip(request)
        key = f"{client_ip}:{request.url.path.split('/')[1:3]}"
        bucket = self.buckets[key]
        window = self.settings.RATE_LIMIT_WINDOW_SECONDS

        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= self.settings.RATE_LIMIT_REQUESTS:
            return Response("Too many requests", status_code=429)

        bucket.append(now)
        return await call_next(request)
