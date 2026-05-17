from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_china


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    identity: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    server: Mapped[str | None] = mapped_column(String(255), index=True)
    port: Mapped[str | None] = mapped_column(String(32))
    type: Mapped[str | None] = mapped_column(String(64), index=True)
    uuid: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(255))
    tls: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    network: Mapped[str | None] = mapped_column(String(64), index=True)
    country: Mapped[str | None] = mapped_column(String(80), index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(16), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    latency: Mapped[int | None] = mapped_column(Integer)
    source_subscription_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source_subscription_name: Mapped[str | None] = mapped_column(String(120), index=True)
    source_group: Mapped[str | None] = mapped_column(String(80), index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_china, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_china, onupdate=now_china, nullable=False
    )
