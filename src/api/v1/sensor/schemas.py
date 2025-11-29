from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, AliasChoices


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
    resistance_1: float = Field(description="Сопротивление 1")
    resistance_2: float = Field(description="Сопротивление 2 (<=4)")

    moment_pc: int = Field(
        description="Момент ПЧ",
        validation_alias=AliasChoices("moment_PC", "moment_pc"),
    )
    moment_percent: int = Field(
        description="Момент %",
        validation_alias=AliasChoices("momentPercent", "moment_percent"),
    )
    moment_amperage_percent: int = Field(
        description="Момент (т) %",
        validation_alias=AliasChoices("momentAmperagePercent", "moment_amperage_percent"),
    )
    turnover: int = Field(
        description="Обороты ПЧ",
        validation_alias=AliasChoices("turnover", "rpm", "revolutions"),
    )
    amperage: int = Field(
        description="Ток ПЧ",
        validation_alias=AliasChoices("amperage", "current"),
    )
    phase_amperage: int = Field(
        description="Фазный ток",
        validation_alias=AliasChoices("phaseAmperage", "phase_amperage"),
    )
    revolutions_pc_alt: int = Field(
        description="Обороты ПЧ alt",
        validation_alias=AliasChoices("revolutions_PC_alt", "revolutions_pc_alt"),
    )
    status_pc: int = Field(
        description="Статус ПЧ",
        validation_alias=AliasChoices("status_PC", "status_pc"),
    )


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
