from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NodeSnapshot(Base):
    __tablename__ = "node_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cache_key: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(80), index=True)
    total_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nodes: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
