from datetime import datetime
from pydantic import BaseModel, Field

from infra.timescale_db.models.screw import ScrewStatus
from api.v1.error.schemas import ErrorRead


class ScrewRead(BaseModel):
    screw_id: int = Field(description="Идентификатор гайки")
    rail_id: int = Field(description="Идентификатор рельсы")
    serial_id: int = Field(description="Порядковый номер гайки в рельсе")
    status: ScrewStatus = Field(description="Статус гайки")


class Sensor2Snapshot(BaseModel):
    timestamp: datetime = Field(description="Метка времени измерения")
    resistance: float = Field(description="Сопротивление")
    temperature: float = Field(description="Температура")
    humidity: float = Field(description="Влажность %")
    frequency_status: int = Field(description="Состояние ПЧ (для текущей гайки)")
    frequency_torque: int = Field(description="Момент ПЧ (для текущей гайки)")
    converter_frequency: int = Field(description="Частота ПЧ (для текущей гайки)")


class ScrewDetail(BaseModel):
    screw: ScrewRead = Field(description="Информация о гайке")
    sensor2: list[Sensor2Snapshot] = Field(default_factory=list, description="Список замеров Sensor2 по каналу гайки")
    errors: list[ErrorRead] = Field(default_factory=list, description="Ошибки, связанные с гайкой")


class ScrewWithLastSensor(BaseModel):
    screw: ScrewRead = Field(description="Информация о гайке")
    last_sensor2: Sensor2Snapshot | None = Field(default=None, description="Последний замер Sensor2 по каналу гайки")
