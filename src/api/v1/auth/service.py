from datetime import timedelta, datetime, timezone
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from fastapi import HTTPException, status
from pydantic import ValidationError

from api.v1.auth.exceptions import credentials_exception
from api.v1.auth.schemas import UserData, UserTokenData, LoginRequest
from api.v1.base.service import BaseService
from core.config import settings


class AuthService(BaseService):
    async def login(self, login_data: LoginRequest) -> dict:
        user = await self.uow.user.get_by_username(login_data.username)
        if not user or user.password != login_data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный логин или пароль"
            )

        token = self.create_token(
            user.user_id,
            user.username,
            settings.access_token_expire_minutes * 60,
        )
        return {
            "access_token": token,
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def get_user(self, token: str) -> UserData:
        """Получает текущего пользователя"""
        # Проверяем, не заблокирован ли токен
        if await self.is_token_blacklisted(token):
            raise credentials_exception

        cache_key = f"auth:user:by_token:{token}"
        cached = await self.redis.get(cache_key)
        if cached:
            user_data = UserData.model_validate_json(cached)
            return user_data

        user = await self.verify_token(token)

        # Сохраняем в кэш до истечения токена
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            ttl = int((datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds())
            if ttl > 0:
                await self.redis.set(cache_key, user.model_dump_json(), expire=ttl)
        return user

    async def blacklist_token(self, token: str) -> None:
        """Добавляет токен в blacklist"""
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        exp_timestamp = payload["exp"]

        # Вычисляем время жизни токена
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        ttl = int((exp_datetime - datetime.now(timezone.utc)).total_seconds())

        if ttl > 0:
            await self.redis.set(
                key=f"blacklist:{token}",
                value="1",
                expire=ttl
            )

    async def is_token_blacklisted(self, token: str) -> bool:
        """Проверяет, заблокирован ли токен"""
        result = await self.redis.get(f"blacklist:{token}")
        return result is not None

    async def logout(self, token: str):
        """Выход пользователя из системы"""
        await self.blacklist_token(token)
        await self.redis.delete(f"auth:user:by_token:{token}")

    async def verify_token(self, token: str) -> UserData:
        """Проверяет токен и возвращает payload"""
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            token_data = UserTokenData.model_validate(payload)
        except (InvalidTokenError, ValidationError):
            raise credentials_exception

        user = await self.uow.user.get_by_id(UUID(token_data.sub))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден"
            )
        return UserData(user_id=user.user_id, username=user.username)

    @staticmethod
    def create_token(
        user_id: UUID,
        username: str,
        exp_time_sec: int,
    ) -> str:
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_time_sec)
        }
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
