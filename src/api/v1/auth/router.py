from typing import Annotated

from fastapi import APIRouter, Depends, Response, Cookie
from fastapi.security.http import HTTPAuthorizationCredentials

from api.v1.auth.dependencies import AuthServiceDep, CurrentUserDep, authentication_schema
from api.v1.auth.utils import get_token_from_request
from api.v1.auth.schemas import LoginRequest, TokenResponse

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, auth_service: AuthServiceDep, response: Response):
    """
    Устанавливает access токен в куки
    """
    data = await auth_service.login(request)
    token = data.get("access_token")
    response.set_cookie(
        key="Authorization",
        value=f"Bearer {token}",
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return TokenResponse(expires_in=data.get("expires_in"))


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

    response.delete_cookie(
        key="Authorization",
        path="/",
    )
    return {"message": "ok"}
