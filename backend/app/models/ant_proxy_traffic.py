from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_china


class AntProxyTrafficSample(Base):
    __tablename__ = "ant_proxy_traffic_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_china, index=True, nullable=False)
    upload_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    download_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    upload_speed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    download_speed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    active_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_ip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
