from sqlalchemy import select

from infra.timescale_db.models import User
from infra.timescale_db.storage.base_storage import PostgresStorage


class UserStorage(PostgresStorage[User]):
    model_cls = User

    async def get_by_username(self, username: str) -> User | None:
        """Получает пользователя по username"""
        stmt = select(User).where(User.username == username)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
