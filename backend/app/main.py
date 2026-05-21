from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.rate_limit import RateLimitMiddleware
from app.core.startup_checks import validate_startup_settings
from app.services.bootstrap import bootstrap_defaults
from app.services.ant_proxy import ant_proxy_service
from app.tasks.scheduler import start_scheduler, stop_scheduler


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    validate_startup_settings(settings)
    await init_db()
    async with AsyncSessionLocal() as session:
        await bootstrap_defaults(session)
        await ant_proxy_service.restore(session)
    start_scheduler()
    yield
    await ant_proxy_service.stop()
    stop_scheduler()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.1.0",
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
