from datetime import datetime

from sqlalchemy import BigInteger, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class Sensor2(Base, CreateTimestampMixin):
    __tablename__ = "sensor_2"

    sensor2_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    screw_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("screw.screw_id", onupdate="CASCADE", ondelete="CASCADE",),
        nullable=False,
        comment="идентификатор гайки",
    )


    resistance: Mapped[float] = mapped_column(Float, nullable=False, comment="Сопротивление")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, comment="Температура")
    humidity: Mapped[float] = mapped_column(Float, nullable=False, comment="Влажность %")

    frequency_status_1: Mapped[int] = mapped_column(Integer, nullable=False, comment="Состояние ПЧ 1")
    frequency_status_2: Mapped[int] = mapped_column(Integer, nullable=False, comment="Состояние ПЧ 2")
    frequency_status_3: Mapped[int] = mapped_column(Integer, nullable=False, comment="Состояние ПЧ 3")
    frequency_status_4: Mapped[int] = mapped_column(Integer, nullable=False, comment="Состояние ПЧ 4")

    frequency_torque_1: Mapped[int] = mapped_column(Integer, nullable=False, comment="Момент ПЧ 1")
    frequency_torque_2: Mapped[int] = mapped_column(Integer, nullable=False, comment="Момент ПЧ 2")
    frequency_torque_3: Mapped[int] = mapped_column(Integer, nullable=False, comment="Момент ПЧ 3")
    frequency_torque_4: Mapped[int] = mapped_column(Integer, nullable=False, comment="Момент ПЧ 4")

    converter_frequency_1: Mapped[int] = mapped_column(Integer, nullable=False, comment="Частота ПЧ 1")
    converter_frequency_2: Mapped[int] = mapped_column(Integer, nullable=False, comment="Частота ПЧ 2")
    converter_frequency_3: Mapped[int] = mapped_column(Integer, nullable=False, comment="Частота ПЧ 3")
    converter_frequency_4: Mapped[int] = mapped_column(Integer, nullable=False, comment="Частота ПЧ 4")

    timestamp: Mapped[datetime] = mapped_column(nullable=False, comment="метка времени измерения")
