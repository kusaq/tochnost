from datetime import datetime
from pydantic import BaseModel, Field


class Sensor1Base(BaseModel):
    encoder1: int
    encoder2: int
    encoder3: int
    encoder4: int

    mm_along_rail: int = Field(description="расстояние в мм от начала РШР")

    laser_on_rail_left: bool = Field(description="лазерная полоса попадает на левый рельс (для забега)")
    laser_on_rail_right: bool = Field(description="лазерная полоса попадает на правый рельс (для забега)")
    laser_on_tie_left: bool = Field(description="лазерная полоса попадает на шпалу слева (для эпюры)")
    laser_on_tie_right: bool = Field(description="лазерная полоса попадает на шпалу справа (для эпюры)")

    mm_gauge: float = Field(description="ширина колеи в мм")
    mm_side_wear_left: float = Field(description="боковой износ левого рельса в мм")
    mm_side_wear_right: float = Field(description="боковой износ правого рельса в мм")
    mm_vertical_wear_left: float = Field(description="вертикальный износ левого рельса в мм")
    mm_vertical_wear_right: float = Field(description="вертикальный износ правого рельса в мм")

    rad_rail_tilt_left: float = Field(description="подуклонка левого рельса в рад")
    rad_rail_tilt_right: float = Field(description="подуклонка правого рельса в рад")

    mm_bolt_height_left_inner: float = Field(description="высота внутреннего болта левого рельса в мм")
    mm_bolt_height_left_outer: float = Field(description="высота внешнего болта левого рельса в мм")
    mm_bolt_height_right_inner: float = Field(description="высота внутреннего болта правого рельса в мм")
    mm_bolt_height_right_outer: float = Field(description="высота внешнего болта правого рельса в мм")

    timestamp: datetime = Field(description="метка времени измерения")
    rail_id: int = Field(description="идентификатор рельса")


class Sensor1Create(Sensor1Base):
    pass


class Sensor1Read(Sensor1Base):
    sensor1_id: int
    created_at: datetime | None = None

    model_config = dict(from_attributes=True)


class Sensor2Base(BaseModel):
    resistance_1: float = Field(description="Сопротивление 1")
    resistance_2: float = Field(description="Сопротивление 2 (<=4)")

    moment_pc: int = Field(description="Момент ПЧ")
    moment_percent: int = Field(description="Момент %")
    moment_amperage_percent: int = Field(description="Момент (т) %")
    turnover: int = Field(description="Обороты ПЧ")
    amperage: int = Field(description="Ток ПЧ")
    phase_amperage: int = Field(description="Фазный ток")
    revolutions_pc_alt: int = Field(description="Обороты ПЧ alt")
    status_pc: int = Field(description="Статус ПЧ")

    timestamp: datetime = Field(description="метка времени измерения")
    rail_id: int = Field(description="идентификатор рельса")


class Sensor2Create(Sensor2Base):
    pass


class Sensor2Read(Sensor2Base):
    sensor2_id: int
    created_at: datetime | None = None

    model_config = dict(from_attributes=True)
