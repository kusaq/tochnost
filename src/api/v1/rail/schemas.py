from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Literal


class RailRead(BaseModel):
    rail_id: int = Field(description="Идентификатор рельсы")
    name: str | None = Field(default=None, description="Название рельсы")
    scanned_name: str | None = Field(default=None, description="Считанный номер РШР")
    status: str = Field(description="Статус рельсы")
    side: str | None = Field(default=None, description="Сторона рельсы: левая/правая/центральная")
    object_name: str | None = Field(default=None, description="Название объекта")
    fastening_type: str | None = Field(default=None, description="Тип крепления")
    sleepers: int | None = Field(default=None, description="Количество шпал")
    sleeper_spacing_mm: int | None = Field(
        default=None, description="Эпюра: среднее расстояние между шпалами, мм"
    )
    start_time: datetime | None = Field(default=None, description="Время начала обработки рельсы")
    end_time: datetime | None = Field(default=None, description="Время окончания обработки рельсы")
    created_at: datetime | None = Field(default=None, description="Время создания записи")

    model_config = dict(from_attributes=True)


class RailUpdate(BaseModel):
    name: str | None = Field(default=None, description="Название рельсы")
    scanned_name: str | None = Field(default=None, max_length=255, description="Считанный номер РШР")
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


class DeleteRailsRequest(BaseModel):
    rail_ids: list[int] = Field(description="Список идентификаторов рельс для удаления")


class DeleteRailsResponse(BaseModel):
    deleted: int = Field(ge=0, description="Количество удалённых записей")
    not_found: list[int] = Field(default_factory=list, description="Идентификаторы не найденных рельс")


class RejectRailResponse(BaseModel):
    deleted: int = Field(ge=0, description="Количество удалённых записей (всегда 1 при успехе)")
    rail_id: int = Field(description="Идентификатор отбракованной рельсы")


class RailMetricRead(BaseModel):
    rail_id: int = Field(description="Идентификатор рельсы")
    name: str = Field(description="Название метрики")
    value: float | None = Field(default=None, description="Агрегированное значение или последнее фактическое")
    required: str | None = Field(default=None, description="Требуемое значение (если есть), например 'min..max [unit]'")
    values: list[tuple[datetime, Any]] = Field(
        default_factory=list,
        description="Список значений с датчиков в формате [timestamp, value]",
    )
    note: str | None = Field(default=None, description="Примечание")


class SensorSeriesRequest(BaseModel):
    rail_ids: list[int] = Field(description="Список идентификаторов рельс")
    source: Literal["sensor1", "sensor2"] = Field(
        default="sensor1",
        description="Источник данных: sensor1 или sensor2",
    )
    fields: list[str] = Field(
        description="Список полей (имен колонок в БД / атрибутов модели Sensor1/Sensor2), которые включить в ответ",
    )


class SensorPoint(BaseModel):
    timestamp: datetime = Field(description="Метка времени измерения")
    values: dict[str, Any] = Field(description="Значения выбранных полей для данного timestamp")


class RailSensorSeries(BaseModel):
    rail_id: int = Field(description="Идентификатор рельсы")
    points: list[SensorPoint] = Field(default_factory=list, description="Список точек по времени")
