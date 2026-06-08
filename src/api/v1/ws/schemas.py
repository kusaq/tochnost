from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EmptyPayload(BaseModel):
    """Пустой объект данных (когда активной рельсы нет)."""
    pass


class DashboardErrorData(BaseModel):
    timestamp: datetime = Field(description="Время события (ISO 8601)")
    description: str = Field(description="Описание ошибки для человека")
    value_name: str = Field(description="Имя метрики, по которой зафиксирована ошибка")
    value: float = Field(description="Фактическое значение метрики в момент ошибки")


class DashboardErrorsEnvelope(BaseModel):
    channel: Literal["dashboard:errors"] = Field(description="Канал сообщения", default="dashboard:errors")
    data: DashboardErrorData = Field(description="Данные события ошибки")


class DashboardStagesData(BaseModel):
    errors_count: int = Field(description="Количество ошибок по текущей рельсе")
    mmAlongRail: int = Field(description="Текущее положение вдоль рельсы (мм) от начала РШР")
    mm_side_wear_left: float = Field(description="Износ левого рельса (мм)")
    mm_side_wear_left_ok: bool = Field(description="Значение износа слева в норме")
    mm_side_wear_right: float = Field(description="Износ правого рельса (мм)")
    mm_side_wear_right_ok: bool = Field(description="Значение износа справа в норме")
    mm_vertical_wear_left: float = Field(description="Вертикальный износ левого рельса (мм)")
    mm_vertical_wear_left_ok: bool = Field(description="Вертикальный износ слева в норме")
    mm_vertical_wear_right: float = Field(description="Вертикальный износ правого рельса (мм)")
    mm_vertical_wear_right_ok: bool = Field(description="Вертикальный износ справа в норме")
    screws_completed: int = Field(description="Количество завершённых гаек в текущей рельсе")
    resistance: float = Field(description="Текущее сопротивление между рельсами")
    resistance_ok: bool = Field(description="Сопротивление в норме")
    mm_gauge: float = Field(description="Текущая ширина колеи (мм)")
    mm_gauge_ok: bool = Field(description="Ширина колеи в норме")
    mm_gauge_avg: float = Field(description="Средняя ширина колеи (мм) по текущей рельсе")


class DashboardStagesEnvelope(BaseModel):
    channel: Literal["dashboard:stages"] = Field(description="Канал сообщения", default="dashboard:stages")
    data: DashboardStagesData | EmptyPayload = Field(
        description="Данные этапов сборки по активной рельсе или пустой объект, если активной рельсы нет"
    )


class DashboardStatusData(BaseModel):
    rail_id: int = Field(description="Идентификатор активной рельсы")
    name: str | None = Field(default=None, description="Имя рельсы")
    scanned_name: str | None = Field(default=None, description="Считанный номер РШР")
    status: str = Field(description="Статус рельсы (значение enum, строка)")
    object_name: str | None = Field(default=None, description="Название объекта")
    fastening_type: str | None = Field(default=None, description="Тип скрепления")
    start_time: datetime | None = Field(default=None, description="Время начала (ISO 8601)")
    end_time: datetime | None = Field(default=None, description="Время окончания (ISO 8601)")


class DashboardStatusEnvelope(BaseModel):
    channel: Literal["dashboard:status"] = Field(description="Канал сообщения", default="dashboard:status")
    data: DashboardStatusData | EmptyPayload = Field(
        description="Информация об активной рельсе или пустой объект, если активной рельсы нет"
    )


class DashboardStatsData(BaseModel):
    temperature_current: float | str = Field(description="Текущая температура или 'N/A' если нет данных")
    humidity_current: float | str = Field(description="Текущая влажность (%) или 'N/A' если нет данных")
    errors_count: int = Field(description="Количество ошибок с начала текущих суток")
    rails_today: int = Field(description="Количество завершённых рельс с начала суток")
    rails_per_hour: int = Field(description="Количество завершённых рельс за последний час")
    avg_speed_per_hour: float = Field(description="Средняя скорость сборки (рельс/час) за текущие сутки")


class DashboardStatsEnvelope(BaseModel):
    channel: Literal["dashboard:stats"] = Field(description="Канал сообщения", default="dashboard:stats")
    data: DashboardStatsData = Field(description="Агрегированная статистика дашборда")


class ErrorsDistributionBucket(BaseModel):
    hour: datetime = Field(description="Начало часа (ISO 8601, UTC)")
    count: int = Field(description="Количество ошибок за этот час")


class ErrorsDistributionData(BaseModel):
    from_: datetime = Field(alias="from", description="Начало интервала (ISO 8601, UTC)")
    to: datetime = Field(description="Конец интервала (ISO 8601, UTC)")
    buckets: list[ErrorsDistributionBucket] = Field(description="Распределение по часам")
    total: int = Field(description="Общее количество ошибок за период")

    class Config:
        populate_by_name = True


class ErrorsDistributionEnvelope(BaseModel):
    channel: Literal["dashboard:errors_distribution"] = Field(
        description="Канал сообщения", default="dashboard:errors_distribution"
    )
    data: ErrorsDistributionData = Field(description="Одноразовая сводка распределения ошибок за сегодня")


class WSDocsOverview(BaseModel):
    url: str = Field(example="/api/v1/ws/dashboard", description="Путь для установления WebSocket-соединения")
    channels: list[str] = Field(
        default_factory=lambda: [
            "dashboard:stats",
            "dashboard:status",
            "dashboard:errors",
            "dashboard:stages",
            "dashboard:errors_distribution",
        ],
        description="Поддерживаемые каналы сообщений",
    )
    notes: list[str] = Field(
        default_factory=lambda: [
            "Datetime сериализуется в ISO 8601 (UTC).",
            "Enum-значения сериализуются строками.",
            "При отсутствии активной рельсы в каналах status/stages возвращается пустой объект {}.",
            "Температура/влажность могут быть числом или строкой 'N/A'.",
        ],
        description="Особенности сериализации и поведения",
    )


