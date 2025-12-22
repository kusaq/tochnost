from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class RailRead(BaseModel):
    rail_id: int = Field(description="Идентификатор рельсы")
    name: str | None = Field(default=None, description="Название рельсы")
    status: str = Field(description="Статус рельсы")
    side: str | None = Field(default=None, description="Сторона рельсы: левая/правая/центральная")
    object_name: str | None = Field(default=None, description="Название объекта")
    fastening_type: str | None = Field(default=None, description="Тип крепления")
    sleepers: int | None = Field(default=None, description="Количество шпал")
    start_time: datetime | None = Field(default=None, description="Время начала обработки рельсы")
    end_time: datetime | None = Field(default=None, description="Время окончания обработки рельсы")
    created_at: datetime | None = Field(default=None, description="Время создания записи")

    model_config = dict(from_attributes=True)


class RailUpdate(BaseModel):
    name: str | None = Field(default=None, description="Название рельсы")
    status: str | None = Field(default=None, description="Статус рельсы")
    side: str | None = Field(default=None, description="Сторона рельсы: левая/правая/центральная")
    object_name: str | None = Field(default=None, description="Название объекта")
    fastening_type: str | None = Field(default=None, description="Тип крепления")
    sleepers: int | None = Field(default=None, description="Количество шпал")
    start_time: datetime | None = Field(default=None, description="Время начала обработки рельсы")
    end_time: datetime | None = Field(default=None, description="Время окончания обработки рельсы")


class RailsListResponse(BaseModel):
    items: list[RailRead] = Field(description="Список рельс")
    total: int = Field(ge=0, description="Общее количество записей")


class RailMetricRead(BaseModel):
    name: str = Field(description="Название метрики")
    value: float | None = Field(default=None, description="Агрегированное значение или пусто")
    required: str | None = Field(default=None, description="Требуемое значение (если есть), например 'min..max [unit]'")
    values: list[Any] = Field(default_factory=list, description="Список значений с датчиков")
    note: str | None = Field(default=None, description="Примечание")
