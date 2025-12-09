from datetime import datetime
from pydantic import BaseModel, Field


class ThresholdRead(BaseModel):
    threshold_id: int = Field(description="Идентификатор порога")
    value: str = Field(description="Имя метрики порога")
    min_value: float = Field(description="Минимально допустимое значение")
    max_value: float = Field(description="Максимально допустимое значение")
    is_critical: bool = Field(description="Критичность порога")
    unit_of_measurement: str | None = Field(default=None, description="Единица измерения")
    created_at: datetime | None = Field(default=None, description="Время создания")
    updated_at: datetime | None = Field(default=None, description="Время обновления")
