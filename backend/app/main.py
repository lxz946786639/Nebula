import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.rate_limit import RateLimitMiddleware
from app.core.startup_checks import validate_startup_settings
from app.models.smart_proxy import SmartProxy
from app.services.bootstrap import bootstrap_defaults
from app.services.ant_proxy import ant_proxy_service
from app.services.smart_proxy import apply_mihomo_runtime
from app.tasks.scheduler import start_scheduler, stop_scheduler


settings = get_settings()
logger = logging.getLogger(__name__)


async def _restore_ant_smart_proxy_runtime() -> None:
    if not ant_proxy_service.nodes:
        return
    async with AsyncSessionLocal() as session:
        ant_proxy_id = await session.scalar(
            select(SmartProxy.id)
            .where(SmartProxy.enabled.is_(True), SmartProxy.data_source == "ant")
            .limit(1)
        )
        if not ant_proxy_id:
            return
        try:
            result = await apply_mihomo_runtime(session, reload_core=True)
            if result.error:
                logger.info("Ant smart proxy runtime restore skipped: %s", result.error)
        except Exception as exc:
            logger.info("Ant smart proxy runtime restore skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    validate_startup_settings(settings)
    await init_db()
    async with AsyncSessionLocal() as session:
        await bootstrap_defaults(session)
        await ant_proxy_service.restore(session)
    await _restore_ant_smart_proxy_runtime()
    start_scheduler()
    yield
    async with AsyncSessionLocal() as session:
        await ant_proxy_service.persist_traffic_totals(session)
    await ant_proxy_service.stop()
    stop_scheduler()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.1.2",
    description="Modern subscription aggregation and conversion platform powered by subconverter.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
