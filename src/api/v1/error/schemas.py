from datetime import datetime
from pydantic import BaseModel, Field


class ErrorRead(BaseModel):
    error_id: int = Field(description="Идентификатор ошибки")
    rail_id: int = Field(description="Идентификатор рельсы")
    screw_id: int | None = Field(default=None, description="Идентификатор гайки (если применимо)")
    value_name: str = Field(description="Имя метрики, по которой выявлена ошибка")
    description: str | None = Field(default=None, description="Человекочитаемое описание ошибки")
    unit_of_measurement: str | None = Field(default=None, description="Единица измерения метрики")
    value: float = Field(description="Фактическое значение метрики")
    min_value: float = Field(description="Минимально допустимое значение")
    max_value: float = Field(description="Максимально допустимое значение")
    is_critical: bool = Field(description="Признак критической ошибки")
    is_fixed: bool = Field(description="Признак, что ошибка исправлена")
    created_at: datetime | None = Field(default=None, description="Время создания записи")
    updated_at: datetime | None = Field(default=None, description="Время обновления записи")


class ErrorFixUpdate(BaseModel):
    is_fixed: bool = Field(description="Новый статус: исправлено (true) или нет (false)")
