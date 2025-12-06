from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, AliasChoices


@dataclass(slots=True)
class Screw:
    screw_id: int
    timestamp: datetime
    frequency_torque: int


@dataclass(slots=True)
class RailSession:
    rail_id: int
    start_time: datetime
    end_time: datetime | None
    last_mm_along_rail: int
    last_timestamp: datetime


class Sensor1Values(BaseModel):
    encoder1: int
    encoder2: int
    encoder3: int
    encoder4: int

    mm_along_rail: int = Field(
        description="расстояние в мм от начала РШР",
        validation_alias=AliasChoices("mmAlongRail", "mm_along_rail"),
    )

    laser_on_rail_left: bool = Field(
        description="лазерная полоса попадает на левый рельс (для забега)",
        validation_alias=AliasChoices("laserOnRailLeft", "laser_on_rail_left"),
    )
    laser_on_rail_right: bool = Field(
        description="лазерная полоса попадает на правый рельс (для забега)",
        validation_alias=AliasChoices("laserOnRailRight", "laser_on_rail_right"),
    )
    laser_on_tie_left: bool = Field(
        description="лазерная полоса попадает на шпалу слева (для эпюры)",
        validation_alias=AliasChoices("laserOnTieLeft", "laser_on_tie_left"),
    )
    laser_on_tie_right: bool = Field(
        description="лазерная полоса попадает на шпалу справа (для эпюры)",
        validation_alias=AliasChoices("laserOnTieRight", "laser_on_tie_right"),
    )

    mm_gauge: float = Field(
        description="ширина колеи в мм",
        validation_alias=AliasChoices("mmGauge", "mm_gauge"),
    )
    mm_side_wear_left: float = Field(
        description="боковой износ левого рельса в мм",
        validation_alias=AliasChoices("mmSideWearLeft", "mm_side_wear_left"),
    )
    mm_side_wear_right: float = Field(
        description="боковой износ правого рельса в мм",
        validation_alias=AliasChoices("mmSideWearRight", "mm_side_wear_right"),
    )
    mm_vertical_wear_left: float = Field(
        description="вертикальный износ левого рельса в мм",
        validation_alias=AliasChoices("mmVerticalWearLeft", "mm_vertical_wear_left"),
    )
    mm_vertical_wear_right: float = Field(
        description="вертикальный износ правого рельса в мм",
        validation_alias=AliasChoices("mmVerticalWearRight", "mm_vertical_wear_right"),
    )

    rad_rail_tilt_left: float = Field(
        description="подуклонка левого рельса в рад",
        validation_alias=AliasChoices("radRailTiltLeft", "rad_rail_tilt_left"),
    )
    rad_rail_tilt_right: float = Field(
        description="подуклонка правого рельса в рад",
        validation_alias=AliasChoices("radRailTiltRight", "rad_rail_tilt_right"),
    )

    mm_bolt_height_left_inner: float = Field(
        description="высота внутреннего болта левого рельса в мм",
        validation_alias=AliasChoices("mmBoltHeightLeftInner", "mm_bolt_height_left_inner"),
    )
    mm_bolt_height_left_outer: float = Field(
        description="высота внешнего болта левого рельса в мм",
        validation_alias=AliasChoices("mmBoltHeightLeftOuter", "mm_bolt_height_left_outer"),
    )
    mm_bolt_height_right_inner: float = Field(
        description="высота внутреннего болта правого рельса в мм",
        validation_alias=AliasChoices("mmBoltHeightRightInner", "mm_bolt_height_right_inner"),
    )
    mm_bolt_height_right_outer: float = Field(
        description="высота внешнего болта правого рельса в мм",
        validation_alias=AliasChoices("mmBoltHeightRightOuter", "mm_bolt_height_right_outer"),
    )


class Sensor1Create(BaseModel):
    timestamp: datetime = Field(description="метка времени измерения")
    values: Sensor1Values = Field(description="Значения")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        dt = v
        if isinstance(v, str):
            try:
                dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.fromisoformat(v)
        if isinstance(dt, datetime):
            if getattr(dt, "tzinfo", None) is not None and dt.utcoffset() is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt


class Sensor2Values(BaseModel):
    resistance: float = Field(description="Сопротивление", validation_alias=AliasChoices("R", "resistance"))
    temperature: float = Field(description="Температура", validation_alias=AliasChoices("T", "temperature"))
    humidity: float = Field(description="Влажность %", validation_alias=AliasChoices("H", "humidity"))

    frequency_status_1: int = Field(description="Состояние ПЧ 1", validation_alias=AliasChoices("ST1", "frequency_status_1"))
    frequency_status_2: int = Field(description="Состояние ПЧ 2", validation_alias=AliasChoices("ST2", "frequency_status_2"))
    frequency_status_3: int = Field(description="Состояние ПЧ 3", validation_alias=AliasChoices("ST3", "frequency_status_3"))
    frequency_status_4: int = Field(description="Состояние ПЧ 4", validation_alias=AliasChoices("ST4", "frequency_status_4"))

    frequency_torque_1: int = Field(description="Момент ПЧ 1", validation_alias=AliasChoices("M1", "frequency_torque_1"))
    frequency_torque_2: int = Field(description="Момент ПЧ 2", validation_alias=AliasChoices("M2", "frequency_torque_2"))
    frequency_torque_3: int = Field(description="Момент ПЧ 3", validation_alias=AliasChoices("M3", "frequency_torque_3"))
    frequency_torque_4: int = Field(description="Момент ПЧ 4", validation_alias=AliasChoices("M4", "frequency_torque_4"))

    converter_frequency_1: int = Field(description="Частота ПЧ 1", validation_alias=AliasChoices("f1", "converter_frequency_1"))
    converter_frequency_2: int = Field(description="Частота ПЧ 2", validation_alias=AliasChoices("f2", "converter_frequency_2"))
    converter_frequency_3: int = Field(description="Частота ПЧ 3", validation_alias=AliasChoices("f3", "converter_frequency_3"))
    converter_frequency_4: int = Field(description="Частота ПЧ 4", validation_alias=AliasChoices("f4", "converter_frequency_4"))


class Sensor2Create(BaseModel):
    timestamp: datetime = Field(description="метка времени измерения")
    values: Sensor2Values = Field(description="Значения")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        dt = v
        if isinstance(v, str):
            try:
                dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.fromisoformat(v)
        if isinstance(dt, datetime):
            if getattr(dt, "tzinfo", None) is not None and dt.utcoffset() is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt


class ThresholdEntry(BaseModel):
    min_value: float
    max_value: float
    is_critical: bool


class Thresholds(BaseModel):
    thresholds: dict[str, ThresholdEntry]
