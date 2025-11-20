from typing import AsyncIterator, Annotated

from fastapi import Depends, WebSocket, WebSocketException, status, Cookie, HTTPException
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBase

from api.v1.auth.schemas import UserData
from api.v1.auth.service import AuthService
from api.v1.auth.utils import extract_token_from_value, get_token_from_request
from infra.timescale_db.uow import TimeScaleDBUnitOfWorkDep
from infra.redis.dependencies import RedisDep

authentication_schema = HTTPBase(scheme="Bearer", auto_error=False)


async def get_auth_service(
    uow: TimeScaleDBUnitOfWorkDep,
    redis: RedisDep,
) -> AsyncIterator[AuthService]:
    yield AuthService(
        uow=uow,
        redis=redis,
    )

async def get_current_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    auth_cred: Annotated[HTTPAuthorizationCredentials | None, Depends(authentication_schema)] = None,
    authorization_cookie: str | None = Cookie(default=None, alias="Authorization"),
) -> UserData:
    token = get_token_from_request(auth_cred, authorization_cookie)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return await auth_service.get_user(token)

async def get_current_user_ws(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    websocket: WebSocket,
) -> UserData:
    token = extract_token_from_value(websocket.cookies.get("Authorization"))
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return await auth_service.get_user(token)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[UserData, Depends(get_current_user)]
CurrentUserWsDep = Annotated[UserData, Depends(get_current_user_ws)]
