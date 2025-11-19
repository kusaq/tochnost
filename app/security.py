from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

try:
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover
    bcrypt = None  # type: ignore
else:
    if bcrypt is not None and not hasattr(bcrypt, "__about__"):
        version = getattr(bcrypt, "__version__", "0")

        class _About:
            __slots__ = ("__version__",)

            def __init__(self, ver: str) -> None:
                self.__version__ = ver

        bcrypt.__about__ = _About(version)  # type: ignore

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _resolve_password_hash() -> str:
    if settings.api_password_hash:
        return settings.api_password_hash
    if not settings.api_password:
        raise RuntimeError(
            "API password is not configured. "
            "Set API_PASSWORD or API_PASSWORD_HASH in the environment."
        )
    return pwd_context.hash(settings.api_password)


HASHED_PASSWORD = _resolve_password_hash()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str) -> bool:
    if username != settings.api_username:
        return False
    return verify_password(password, HASHED_PASSWORD)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str | None = payload.get("sub")
        if username != settings.api_username:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc
    return settings.api_username



