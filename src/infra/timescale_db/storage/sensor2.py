from typing import Sequence

from sqlalchemy import select

from infra.timescale_db.models import Sensor2
from infra.timescale_db.storage.base_storage import PostgresStorage


class Sensor2Storage(PostgresStorage[Sensor2]):
    model_cls = Sensor2
