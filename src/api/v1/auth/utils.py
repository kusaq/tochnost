from urllib.parse import unquote_plus

from fastapi import Response
from fastapi.security.http import HTTPAuthorizationCredentials

from core.config import settings


def extract_token_from_value(value: str | None) -> str | None:
    if not value:
        return None
    decoded = unquote_plus(value).strip()
    if not decoded:
        return None
    if decoded.lower().startswith("bearer "):
        return decoded[7:]
    return decoded


def get_token_from_request(
    auth_cred: HTTPAuthorizationCredentials | None,
    authorization_cookie: str | None,
) -> str | None:
    if auth_cred and getattr(auth_cred, "credentials", None):
        token = extract_token_from_value(auth_cred.credentials)
        if token:
            return token
    if authorization_cookie:
        token = extract_token_from_value(authorization_cookie)
        if token:
            return token
    return None


def get_auth_cookie_kwargs() -> dict:
    if settings.DEBUG:
        return {"httponly": True, "secure": False, "samesite": "lax", "path": "/"}
    return {"httponly": True, "secure": True, "samesite": "none", "path": "/"}


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="Authorization",
        value=f"Bearer {token}",
        **get_auth_cookie_kwargs(),
    )


def delete_auth_cookie(response: Response) -> None:
    response.delete_cookie(key="Authorization", path="/")


