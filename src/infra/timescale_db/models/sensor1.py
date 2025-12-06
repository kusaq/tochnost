from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateTimestampMixin
from infra.timescale_db.models.base import Base


class Sensor1(Base, CreateTimestampMixin):
    __tablename__ = "sensor_1"

    sensor1_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    encoder1: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="значение энкодера 1")
    encoder2: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="значение энкодера 2")
    encoder3: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="значение энкодера 3")
    encoder4: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="значение энкодера 4")

    mm_along_rail: Mapped[int] = mapped_column("mmAlongRail", BigInteger, nullable=False, comment="расстояние в мм от начала РШР")

    laser_on_rail_left: Mapped[bool] = mapped_column("laserOnRailLeft", Boolean, nullable=False, comment="лазерная полоса попадает на левый рельс (для забега)")
    laser_on_rail_right: Mapped[bool] = mapped_column("laserOnRailRight", Boolean, nullable=False, comment="лазерная полоса попадает на правый рельс (для забега)")
    laser_on_tie_left: Mapped[bool] = mapped_column("laserOnTieLeft", Boolean, nullable=False, comment="лазерная полоса попадает на шпалу слева (для эпюры)")
    laser_on_tie_right: Mapped[bool] = mapped_column("laserOnTieRight", Boolean, nullable=False, comment="лазерная полоса попадает на шпалу справа (для эпюры)")

    mm_gauge: Mapped[float] = mapped_column("mmGauge", Float, nullable=False, comment="ширина колеи в мм")
    mm_side_wear_left: Mapped[float] = mapped_column("mmSideWearLeft", Float, nullable=False, comment="боковой износ левого рельса в мм")
    mm_side_wear_right: Mapped[float] = mapped_column("mmSideWearRight", Float, nullable=False, comment="боковой износ правого рельса в мм")
    mm_vertical_wear_left: Mapped[float] = mapped_column("mmVerticalWearLeft", Float, nullable=False, comment="вертикальный износ левого рельса в мм")
    mm_vertical_wear_right: Mapped[float] = mapped_column("mmVerticalWearRight", Float, nullable=False, comment="вертикальный износ правого рельса в мм")

    rad_rail_tilt_left: Mapped[float] = mapped_column("radRailTiltLeft", Float, nullable=False, comment="подуклонка левого рельса в рад")
    rad_rail_tilt_right: Mapped[float] = mapped_column("radRailTiltRight", Float, nullable=False, comment="подуклонка правого рельса в рад")

    mm_bolt_height_left_inner: Mapped[float] = mapped_column("mmBoltHeightLeftInner", Float, nullable=False, comment="высота внутреннего болта левого рельса в мм")
    mm_bolt_height_left_outer: Mapped[float] = mapped_column("mmBoltHeightLeftOuter", Float, nullable=False, comment="высота внешнего болта левого рельса в мм")
    mm_bolt_height_right_inner: Mapped[float] = mapped_column("mmBoltHeightRightInner", Float, nullable=False, comment="высота внутреннего болта правого рельса в мм")
    mm_bolt_height_right_outer: Mapped[float] = mapped_column("mmBoltHeightRightOuter", Float, nullable=False, comment="высота внешнего болта правого рельса в мм")

    timestamp: Mapped[datetime] = mapped_column(nullable=False, comment="метка времени измерения")

    rail_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rail.rail_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="идентификатор рельса",
    )
