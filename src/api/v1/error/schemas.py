from datetime import datetime
from pydantic import BaseModel, Field


class ErrorRead(BaseModel):
    error_id: int
    rail_id: int
    screw_id: int | None = None
    value_name: str
    description: str | None = None
    unit_of_measurement: str | None = None
    value: float
    min_value: float
    max_value: float
    is_critical: bool
    is_fixed: bool
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class ErrorFixUpdate(BaseModel):
    is_fixed: bool
