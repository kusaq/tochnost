from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, BigInteger, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class RailStatus(PyEnum):
        IN_PROGRESS = "В процессе"
        COMPLETED = "Завершено"
        FAILED = "Завершено с ошибкой"


class Rail(Base, CreateTimestampMixin):
    __tablename__ = "rail"

    rail_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[RailStatus] = mapped_column(
        Enum(RailStatus, name="rail_status", native_enum=False),
        nullable=False,
        default=RailStatus.IN_PROGRESS,
    )
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fastening_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sleepers: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(nullable=True)
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sensor1_records = relationship("Sensor1", back_populates="rail")
    sensor2_records = relationship("Sensor2", back_populates="rail")
