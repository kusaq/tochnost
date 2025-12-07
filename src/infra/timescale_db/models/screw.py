from enum import Enum as PyEnum

from sqlalchemy import BigInteger, ForeignKey, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class ScrewStatus(PyEnum):
    IN_PROGRESS = "В процессе"
    COMPLETED = "Завершено"


class Screw(Base, CreateTimestampMixin):
    __tablename__ = "screw"

    screw_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    serial_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="Порядковый номер гайки в рельсе")
    status: Mapped[ScrewStatus] = mapped_column(
        Enum(ScrewStatus, name="screw_status", native_enum=False),
        nullable=False,
        default=ScrewStatus.IN_PROGRESS,
    )
    rail_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rail.rail_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        comment="идентификатор рельса",
    )
