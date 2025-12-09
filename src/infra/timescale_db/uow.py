from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.timescale_db.ts_db import get_db
from infra.timescale_db.storage.user import UserStorage
from infra.timescale_db.storage.rail import RailStorage
from infra.timescale_db.storage.sensor1 import Sensor1Storage
from infra.timescale_db.storage.sensor2 import Sensor2Storage
from infra.timescale_db.storage.threshold import ThresholdStorage
from infra.timescale_db.storage.screw import ScrewStorage
from infra.timescale_db.storage.error import ErrorStorage


class TimeScaleDBUnitOfWork:
    """
    A single entry point for working with storages.
    Manages access to data storages using the provided database session.
    """
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user = UserStorage(db)
        self.rail = RailStorage(db)
        self.sensor1 = Sensor1Storage(db)
        self.sensor2 = Sensor2Storage(db)
        self.threshold = ThresholdStorage(db)
        self.screw = ScrewStorage(db)
        self.error = ErrorStorage(db)


async def get_uow() -> AsyncIterator[TimeScaleDBUnitOfWork]:
    async with get_db() as db:
        yield TimeScaleDBUnitOfWork(db)


TimeScaleDBUnitOfWorkDep = Annotated[TimeScaleDBUnitOfWork, Depends(get_uow)]
