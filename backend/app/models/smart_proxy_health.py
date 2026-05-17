from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SmartProxyHealthLog(Base):
    __tablename__ = "smart_proxy_health_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    smart_proxy_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    node_id: Mapped[int | None] = mapped_column(Integer, index=True)
    node_name: Mapped[str | None] = mapped_column(String(255), index=True)
    check_type: Mapped[str] = mapped_column(String(40), default="delay", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="unknown", index=True, nullable=False)
    latency: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
