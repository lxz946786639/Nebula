from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SmartProxySwitchLog(Base):
    __tablename__ = "smart_proxy_switch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    smart_proxy_id: Mapped[int] = mapped_column(ForeignKey("smart_proxies.id", ondelete="CASCADE"), index=True, nullable=False)
    from_node: Mapped[str | None] = mapped_column(String(255))
    to_node: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
