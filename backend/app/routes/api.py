from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request

from app import db
from app.config import ROLE_PERMISSIONS, Settings, get_settings
from app.security import SESSION_COOKIE, cookie_attributes, decode_session_token

router = APIRouter(prefix="/api", tags=["api"])


def current_session(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = decode_session_token(token, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid session: {exc}")
    user = db.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"user": user, "claims": claims}


def require_role(role: str):
    def checker(session: dict = Depends(current_session)) -> dict:
        if session["user"]["role"] != role:
            raise HTTPException(
                status_code=403, detail=f"Requires role '{role}', you have '{session['user']['role']}'"
            )
        return session

    return checker


def _ts(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/me")
def me(session: dict = Depends(current_session), settings: Settings = Depends(get_settings)):
    user, claims = session["user"], session["claims"]
    snapshot = user["github_snapshot"]
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "user": {k: user[k] for k in ("id", "github_id", "login", "name", "email", "avatar_url", "role",
                                      "created_at", "last_login_at")},
        "identity": snapshot["profile"],
        "emails": snapshot["emails"],
        "authentication": {**user["last_auth"], "authenticated": True},
        "session": {
            "type": "JWT (HS256) in HttpOnly cookie",
            "cookie_name": SESSION_COOKIE,
            "cookie_attributes": cookie_attributes(settings),
            "claims": claims,
            "issued_at": _ts(claims["iat"]),
            "expires_at": _ts(claims["exp"]),
            "expires_in_seconds": claims["exp"] - now,
        },
        "authorization": {
            "app_role": user["role"],
            "permissions": ROLE_PERMISSIONS.get(user["role"], []),
            "role_source": "admin if GitHub login is in ADMIN_GITHUB_LOGINS, else user",
            "github_site_admin": snapshot["profile"].get("site_admin", False),
            "orgs": snapshot["orgs"],
            "org_memberships": snapshot["org_memberships"],
            "teams": snapshot["teams"],
        },
    }


@router.get("/user-only")
def user_only(session: dict = Depends(current_session)):
    return {"ok": True, "message": f"Hello {session['user']['login']}, any authenticated user can see this."}


@router.get("/admin-only")
def admin_only(session: dict = Depends(require_role("admin"))):
    return {"ok": True, "message": f"Welcome admin {session['user']['login']}."}
