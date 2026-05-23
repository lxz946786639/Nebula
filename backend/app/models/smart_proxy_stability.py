from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_china


class SmartProxyStabilitySample(Base):
    __tablename__ = "smart_proxy_stability_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    smart_proxy_id: Mapped[int] = mapped_column(ForeignKey("smart_proxies.id", ondelete="CASCADE"), index=True, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_china, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="unknown", index=True, nullable=False)
    core_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    listener_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    state_synced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(255))
    mihomo_current_node: Mapped[str | None] = mapped_column(String(255))
    candidate_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runtime_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    online_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay: Mapped[int | None] = mapped_column(Integer)
    average_delay: Mapped[int | None] = mapped_column(Integer)
    upload_speed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_speed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    switch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    traffic_excluded_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    traffic_risk_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    traffic_unknown_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
