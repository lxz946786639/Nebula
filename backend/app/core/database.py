from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.DATABASE_URL.startswith("sqlite"):
    db_path = settings.DATABASE_URL.rsplit("///", 1)[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            existing = {
                row[1]
                for row in (await conn.execute(text("PRAGMA table_info(smart_proxies)"))).all()
            }
            columns = {
                "traffic_guard_enabled": "BOOLEAN",
                "min_remaining_mb": "INTEGER",
                "low_remaining_mb": "INTEGER",
                "expire_soon_days": "INTEGER",
                "exclude_unknown_traffic": "BOOLEAN",
                "current_node": "VARCHAR(255)",
                "switch_count": "INTEGER DEFAULT 0 NOT NULL",
                "access_token": "VARCHAR(120)",
                "config_updated_at": "DATETIME",
                "strategy_node_ids": "JSON DEFAULT '[]' NOT NULL",
                "stability_priority": "BOOLEAN DEFAULT 0 NOT NULL",
            }
            for name, ddl_type in columns.items():
                if name not in existing:
                    await conn.execute(text(f"ALTER TABLE smart_proxies ADD COLUMN {name} {ddl_type}"))
                    if name == "config_updated_at":
                        await conn.execute(
                            text(
                                "UPDATE smart_proxies "
                                "SET config_updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
                            )
                        )
