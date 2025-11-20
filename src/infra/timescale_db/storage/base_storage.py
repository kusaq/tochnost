from typing import Generic, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from infra.timescale_db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class PostgresStorage(Generic[ModelT]):

    model_cls: Type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def add(self, obj: ModelT) -> ModelT:
        self._db.add(obj)
        await self._db.flush()
        return obj

    async def add_many(self, objs: list[ModelT]) -> list[ModelT]:
        self._db.add_all(objs)
        await self._db.flush()
        return objs

    async def get_by_id(self, obj_id) -> ModelT | None:
        return await self._db.get(self.model_cls, obj_id)

    async def exists_by_id(self, obj_id) -> bool:
        return await self._db.get(self.model_cls, obj_id) is not None

    async def update(self, obj: ModelT) -> ModelT:
        """Обновляет объект в базе данных"""
        await self._db.flush()
        await self._db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        """Удаляет объект из базы данных"""
        await self._db.delete(obj)
        await self._db.flush()
