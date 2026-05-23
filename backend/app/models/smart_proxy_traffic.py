from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_china


class SmartProxyTrafficSample(Base):
    __tablename__ = "smart_proxy_traffic_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    smart_proxy_id: Mapped[int] = mapped_column(ForeignKey("smart_proxies.id", ondelete="CASCADE"), index=True, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_china, index=True, nullable=False)
    upload_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upload_speed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_speed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    online_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_ip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unauthorized_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
