from datetime import datetime
from pydantic import BaseModel, Field


class RailRead(BaseModel):
    rail_id: int
    name: str | None = None
    status: str
    object_name: str | None = None
    fastening_type: str | None = None
    sleepers: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime | None = None

    model_config = dict(from_attributes=True)


class RailUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    object_name: str | None = None
    fastening_type: str | None = None
    sleepers: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class RailsListResponse(BaseModel):
    items: list[RailRead]
    total: int = Field(ge=0)


