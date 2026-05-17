from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SmartProxy(Base):
    __tablename__ = "smart_proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    proxy_type: Mapped[str] = mapped_column(String(20), default="mixed", index=True, nullable=False)
    listen_host: Mapped[str] = mapped_column(String(64), default="127.0.0.1", nullable=False)
    port: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), default="fallback", index=True, nullable=False)
    stability_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scenario: Mapped[str] = mapped_column(String(40), default="general", index=True, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), default="all", index=True, nullable=False)
    subscription_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    country_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    node_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    strategy_node_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    protocol_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    health_check_url: Mapped[str] = mapped_column(String(255), default="http://www.gstatic.com/generate_204", nullable=False)
    health_check_interval: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    tolerance: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    username: Mapped[str | None] = mapped_column(String(80))
    password: Mapped[str | None] = mapped_column(String(120))
    access_token: Mapped[str | None] = mapped_column(String(120))
    ip_whitelist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    traffic_guard_enabled: Mapped[bool | None] = mapped_column(Boolean)
    min_remaining_mb: Mapped[int | None] = mapped_column(Integer)
    low_remaining_mb: Mapped[int | None] = mapped_column(Integer)
    expire_soon_days: Mapped[int | None] = mapped_column(Integer)
    exclude_unknown_traffic: Mapped[bool | None] = mapped_column(Boolean)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="stopped", index=True, nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(255))
    switch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
