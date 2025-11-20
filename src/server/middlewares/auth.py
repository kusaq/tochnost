from datetime import datetime, timezone

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings
from api.v1.auth.utils import extract_token_from_value
from api.v1.auth.service import AuthService


class SlidingSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Только HTTP (WS не проходит через это middleware)
        token_cookie = request.cookies.get("Authorization")
        token = extract_token_from_value(token_cookie) if token_cookie else None

        new_token: str | None = None
        if token:
            try:
                payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
                # Сколько осталось до истечения
                exp_ts = payload.get("exp")
                if isinstance(exp_ts, (int, float)):
                    now = datetime.now(timezone.utc).timestamp()
                    remaining = int(exp_ts - now)
                    threshold = settings.jwt_renew_threshold_minutes * 60
                    if 0 < remaining <= threshold:
                        # Выпускаем новый токен на основе payload
                        user_id = payload.get("sub")
                        username = payload.get("username", "")
                        new_token = AuthService.create_token(
                            user_id=user_id,
                            username=username,
                            exp_time_sec=settings.access_token_expire_minutes * 60,
                        )
            except Exception:
                # Любая ошибка верификации — не продлеваем
                pass

        response: Response = await call_next(request)

        if new_token:
            response.set_cookie(
                key="Authorization",
                value=f"Bearer {new_token}",
                httponly=True,
                secure=True,
                samesite="none",
                path="/",
            )

        return response
