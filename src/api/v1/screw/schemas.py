from datetime import datetime
from pydantic import BaseModel

from infra.timescale_db.models.screw import ScrewStatus
from api.v1.error.schemas import ErrorRead


class ScrewRead(BaseModel):
    screw_id: int
    rail_id: int
    serial_id: int
    status: ScrewStatus


class Sensor2Snapshot(BaseModel):
    timestamp: datetime
    resistance: float
    temperature: float
    humidity: float
    frequency_status: int
    frequency_torque: int
    converter_frequency: int


class ScrewDetail(BaseModel):
    screw: ScrewRead
    sensor2: list[Sensor2Snapshot] = []
    errors: list[ErrorRead] = []
