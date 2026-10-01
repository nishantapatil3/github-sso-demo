"""Thin async client for the GitHub OAuth + REST endpoints used during login."""

import httpx

from app.config import Settings

API_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


class GitHubError(Exception):
    pass


def _split_scopes(value: str | None, sep: str = ",") -> list[str]:
    return [s.strip() for s in (value or "").split(sep) if s.strip()]


async def exchange_code(code: str, settings: Settings) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.github_oauth_url}/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.callback_url,
            },
        )
    if resp.status_code != 200:
        raise GitHubError(f"token exchange failed: HTTP {resp.status_code}")
    data = resp.json()
    if "error" in data:
        raise GitHubError(data.get("error_description") or data["error"])
    if "access_token" not in data:
        raise GitHubError("token exchange returned no access_token")
    return data


async def _optional(client: httpx.AsyncClient, path: str) -> dict:
    """Fetch an endpoint that may be denied by missing scopes; never raises on 4xx."""
    resp = await client.get(path, params={"per_page": 100})
    if resp.is_success:
        return {"granted": True, "status": resp.status_code, "data": resp.json()}
    try:
        message = resp.json().get("message")
    except ValueError:
        message = resp.text
    return {"granted": False, "status": resp.status_code, "data": None, "error": message}


async def fetch_user_bundle(access_token: str, settings: Settings) -> dict:
    headers = {**API_HEADERS, "Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(base_url=settings.github_api_url, headers=headers, timeout=10) as client:
        resp = await client.get("/user")
        if not resp.is_success:
            raise GitHubError(f"GET /user failed: HTTP {resp.status_code}")
        h = resp.headers
        bundle = {
            "profile": resp.json(),
            "emails": await _optional(client, "/user/emails"),
            "orgs": await _optional(client, "/user/orgs"),
            "org_memberships": await _optional(client, "/user/memberships/orgs"),
            "teams": await _optional(client, "/user/teams"),
            "token_scopes": _split_scopes(h.get("x-oauth-scopes")),
            "accepted_scopes": _split_scopes(h.get("x-accepted-oauth-scopes")),
            "rate_limit": {
                "limit": h.get("x-ratelimit-limit"),
                "remaining": h.get("x-ratelimit-remaining"),
                "used": h.get("x-ratelimit-used"),
                "reset": h.get("x-ratelimit-reset"),
                "resource": h.get("x-ratelimit-resource"),
            },
        }
    return bundle


def primary_email(bundle: dict) -> str | None:
    if bundle["profile"].get("email"):
        return bundle["profile"]["email"]
    for e in bundle["emails"].get("data") or []:
        if e.get("primary") and e.get("verified"):
            return e["email"]
    return None
