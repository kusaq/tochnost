from typing import Annotated

from fastapi import APIRouter, Depends, Response, Cookie
from fastapi.security.http import HTTPAuthorizationCredentials

from api.v1.auth.dependencies import AuthServiceDep, CurrentUserDep, authentication_schema
from api.v1.auth.utils import get_token_from_request, set_auth_cookie, delete_auth_cookie
from api.v1.auth.schemas import LoginRequest, TokenResponse, UserData

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, auth_service: AuthServiceDep, response: Response):
    """
    Устанавливает access токен в куки
    """
    data = await auth_service.login(request)
    token = data.get("access_token")
    set_auth_cookie(response, token)
    return TokenResponse(expires_in=data.get("expires_in"))


@router.get("/auth/me", response_model=UserData)
async def me(current_user: CurrentUserDep):
    return current_user


@router.post("/logout", response_model=dict)
async def logout(
    current_user: CurrentUserDep,
    auth_service: AuthServiceDep,
    response: Response,
    auth_cred: Annotated[HTTPAuthorizationCredentials | None, Depends(authentication_schema)] = None,
    authorization_cookie: str | None = Cookie(default=None, alias="Authorization"),
):
    """
    Выход из системы - добавляет токен в blacklist
    """
    token = get_token_from_request(auth_cred, authorization_cookie)
    if token:
        await auth_service.logout(token)

    delete_auth_cookie(response)
    return {"message": "ok"}
