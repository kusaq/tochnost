from datetime import datetime

from sqlalchemy import BigInteger, Float
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class Sensor2(Base, CreateTimestampMixin):
    __tablename__ = "sensor_2"

    sensor2_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    resistance_1: Mapped[float] = mapped_column(Float, nullable=False, comment="Сопротивление 1")
    resistance_2: Mapped[float] = mapped_column("resistance_2", Float, nullable=False, comment="Сопротивление 2 (<=4)")

    moment_pc: Mapped[int] = mapped_column("moment_PC", BigInteger, nullable=False, comment="Момент ПЧ")
    moment_percent: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Момент %")
    moment_amperage_percent: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Момент (т) %")
    turnover: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Обороты ПЧ")
    amperage: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Ток ПЧ")
    phase_amperage: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Фазный ток")
    revolutions_pc_alt: Mapped[int] = mapped_column("revolutions_PC_alt", BigInteger, nullable=False, comment="Обороты ПЧ alt")
    status_pc: Mapped[int] = mapped_column("status_PC", BigInteger, nullable=False, comment="Статус ПЧ")

    timestamp: Mapped[datetime] = mapped_column(nullable=False, comment="метка времени измерения")
