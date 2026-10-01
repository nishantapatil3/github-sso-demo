from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Response

from app.config import Settings

SESSION_COOKIE = "session"
STATE_COOKIE = "oauth_state"
ALGORITHM = "HS256"


def create_session_token(user: dict, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user["id"],
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_ttl_hours)).timestamp()),
        "role": user["role"],
        "github_id": user["github_id"],
        "github_login": user["login"],
        "auth_provider": "github",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_session_token(token: str, settings: Settings) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], issuer=settings.jwt_issuer)


def cookie_attributes(settings: Settings) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure, "path": "/"}


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.session_ttl_hours * 3600, **cookie_attributes(settings)
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE, **cookie_attributes(settings))


def mask_token(token: str) -> str:
    prefix = token.split("_", 1)[0] + "_" if "_" in token else ""
    return f"{prefix}••••{token[-4:]}"
