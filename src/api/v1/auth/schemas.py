from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserTokenData(BaseModel):
    sub: str
    username: str
    exp: datetime


class UserData(BaseModel):
    user_id: UUID
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    expires_in: int
