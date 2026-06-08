from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, BigInteger, Enum, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class RailStatus(PyEnum):
        IN_PROGRESS = "В процессе"
        COMPLETED = "Завершено"

class RailSide(PyEnum):
        LEFT = "Левая"
        RIGHT = "Правая"
        CENTER = "Центральная"


class Rail(Base, CreateTimestampMixin):
    __tablename__ = "rail"

    rail_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scanned_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Считанный номер РШР (OCR/нейросеть)"
    )
    status: Mapped[RailStatus] = mapped_column(
        Enum(RailStatus, name="rail_status", native_enum=False),
        nullable=False,
        default=RailStatus.IN_PROGRESS,
    )
    side: Mapped[RailSide | None] = mapped_column(
        Enum(RailSide, name="rail_side", native_enum=False),
        nullable=True,
        comment="Сторона рельса: левая/правая/центральная",
    )
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fastening_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sleepers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Метка мягкого удаления; NULL — запись активна",
    )
    length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Длина РШР, мм")
    resistance_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
