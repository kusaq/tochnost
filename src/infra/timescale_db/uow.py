from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.timescale_db.ts_db import get_db
from infra.timescale_db.storage.user import UserStorage


class TimeScaleDBUnitOfWork:
    """
    A single entry point for working with storages.
    Manages access to data storages using the provided database session.
    """
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user = UserStorage(db)


async def get_uow() -> AsyncIterator[TimeScaleDBUnitOfWork]:
    async with get_db() as db:
        yield TimeScaleDBUnitOfWork(db)


TimeScaleDBUnitOfWorkDep = Annotated[TimeScaleDBUnitOfWork, Depends(get_uow)]
