from datetime import datetime

from sqlalchemy import String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class Rail(Base, CreateTimestampMixin):
    __tablename__ = "rail"

    rail_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fastening_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sleepers: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(nullable=True)

    sensor1_records = relationship("Sensor1", back_populates="rail")
