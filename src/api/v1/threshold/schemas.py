from datetime import datetime
from pydantic import BaseModel


class ThresholdRead(BaseModel):
    threshold_id: int
    value: str
    min_value: float
    max_value: float
    is_critical: bool
    unit_of_measurement: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
