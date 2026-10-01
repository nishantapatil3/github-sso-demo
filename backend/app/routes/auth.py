import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import db, github
from app.config import REQUESTED_SCOPES, Settings, get_settings
from app.security import (
    STATE_COOKIE,
    clear_session_cookie,
    create_session_token,
    mask_token,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _error_redirect(settings: Settings, message: str) -> RedirectResponse:
    resp = RedirectResponse(f"{settings.frontend_url}/?{urlencode({'error': message})}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/auth")
    return resp


@router.get("/github/login")
def github_login(settings: Settings = Depends(get_settings)):
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.callback_url,
        "scope": " ".join(REQUESTED_SCOPES),
        "state": state,
        "allow_signup": "true",
    }
    resp = RedirectResponse(f"{settings.github_oauth_url}/authorize?{urlencode(params)}", status_code=302)
    resp.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/auth"
    )
    return resp


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    settings: Settings = Depends(get_settings),
):
    if error:
        return _error_redirect(settings, error_description or error)

    expected_state = request.cookies.get(STATE_COOKIE)
    if not code or not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")

    try:
        token = await github.exchange_code(code, settings)
        bundle = await github.fetch_user_bundle(token["access_token"], settings)
    except github.GitHubError as exc:
        return _error_redirect(settings, str(exc))

    profile = bundle["profile"]
    role = "admin" if profile["login"].lower() in settings.admin_logins else "user"
    last_auth = {
        "provider": "github",
        "flow": "OAuth 2.0 authorization code (GitHub OAuth App)",
        "client_id": settings.github_client_id,
        "redirect_uri": settings.callback_url,
        "state_verified": True,
        "authenticated_at": db.utcnow(),
        "token_type": token.get("token_type"),
        "access_token_masked": mask_token(token["access_token"]),
        "requested_scopes": REQUESTED_SCOPES,
        "granted_scopes": github._split_scopes(token.get("scope")),
        "x_oauth_scopes": bundle["token_scopes"],
        "rate_limit": bundle["rate_limit"],
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    snapshot = {k: bundle[k] for k in ("profile", "emails", "orgs", "org_memberships", "teams")}
    user = db.upsert_user(profile, github.primary_email(bundle), role, snapshot, last_auth)

    resp = RedirectResponse(settings.frontend_url, status_code=302)
    set_session_cookie(resp, create_session_token(user, settings), settings)
    resp.delete_cookie(STATE_COOKIE, path="/auth")
    return resp


@router.post("/logout", status_code=204)
def logout(settings: Settings = Depends(get_settings)):
    resp = Response(status_code=204)
    clear_session_cookie(resp, settings)
    return resp
