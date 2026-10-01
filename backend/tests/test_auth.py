from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import get_settings

API = "https://api.github.com"
TOKEN = "gho_abcdefghijklmnop1234"
PROFILE = {"id": 42, "login": "octocat", "name": "The Octocat", "email": None,
           "avatar_url": "https://example.com/a.png", "site_admin": False}
EMAILS = [
    {"email": "secondary@example.com", "primary": False, "verified": True, "visibility": None},
    {"email": "octo@example.com", "primary": True, "verified": True, "visibility": "private"},
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "secret")
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setenv("ADMIN_GITHUB_LOGINS", "")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app, base_url="http://localhost:5173") as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def github():
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://github.com/login/oauth/access_token").respond(
            json={"access_token": TOKEN, "token_type": "bearer", "scope": "read:org,read:user,user:email"}
        )
        mock.get(f"{API}/user").respond(
            json=PROFILE,
            headers={"X-OAuth-Scopes": "read:org, read:user, user:email", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Remaining": "4999"},
        )
        mock.get(f"{API}/user/emails").respond(json=EMAILS)
        mock.get(f"{API}/user/orgs").respond(json=[{"login": "acme", "id": 1}])
        mock.get(f"{API}/user/memberships/orgs").respond(
            json=[{"organization": {"login": "acme"}, "role": "admin", "state": "active"}]
        )
        mock.get(f"{API}/user/teams").respond(json=[{"name": "core", "organization": {"login": "acme"}}])
        yield mock


def login(client) -> httpx.Response:
    resp = client.get("/auth/github/login", follow_redirects=False)
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return client.get(f"/auth/github/callback?code=abc&state={state}", follow_redirects=False)


def test_login_redirects_to_github_with_state(client):
    resp = client.get("/auth/github/login", follow_redirects=False)
    assert resp.status_code == 302
    url = urlparse(resp.headers["location"])
    q = parse_qs(url.query)
    assert url.netloc == "github.com" and url.path == "/login/oauth/authorize"
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://localhost:5173/auth/github/callback"]
    assert q["scope"] == ["read:user user:email read:org"]
    assert q["state"][0] == resp.cookies["oauth_state"]


def test_callback_rejects_bad_state(client):
    client.get("/auth/github/login", follow_redirects=False)
    resp = client.get("/auth/github/callback?code=abc&state=wrong", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_rejects_missing_state_cookie(client):
    resp = client.get("/auth/github/callback?code=abc&state=x", follow_redirects=False)
    assert resp.status_code == 400


def test_github_denied_redirects_with_error(client):
    resp = client.get("/auth/github/callback?error=access_denied&error_description=denied",
                      follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:5173/?error=denied"


def test_full_login_and_me(client, github):
    resp = login(client)
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:5173"
    set_cookie = resp.headers["set-cookie"].lower()
    assert "session=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = client.get("/api/me").json()
    assert me["user"]["login"] == "octocat"
    assert me["user"]["email"] == "octo@example.com"  # fallback from /user/emails
    assert me["user"]["role"] == "user"
    auth = me["authentication"]
    assert auth["state_verified"] is True
    assert auth["access_token_masked"] == "gho_••••1234"
    assert TOKEN not in str(me)
    assert set(auth["granted_scopes"]) == {"read:org", "read:user", "user:email"}
    assert me["session"]["claims"]["github_login"] == "octocat"
    assert me["session"]["expires_in_seconds"] > 0
    assert me["authorization"]["permissions"] == ["profile:read"]
    assert me["authorization"]["org_memberships"]["data"][0]["role"] == "admin"
    assert me["authorization"]["teams"]["granted"] is True


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401
    client.cookies.set("session", "garbage")
    assert client.get("/api/me").status_code == 401


def test_authz_endpoints_for_user(client, github):
    login(client)
    assert client.get("/api/user-only").status_code == 200
    assert client.get("/api/admin-only").status_code == 403


def test_admin_role_from_env(client, github, monkeypatch):
    monkeypatch.setenv("ADMIN_GITHUB_LOGINS", "someone, OctoCat")
    get_settings.cache_clear()
    login(client)
    me = client.get("/api/me").json()
    assert me["user"]["role"] == "admin"
    assert "admin:access" in me["authorization"]["permissions"]
    assert client.get("/api/admin-only").status_code == 200


def test_missing_read_org_scope_is_graceful(client, github):
    github.get(f"{API}/user/memberships/orgs").respond(403, json={"message": "Must have read:org scope"})
    github.get(f"{API}/user/teams").respond(403, json={"message": "Must have read:org scope"})
    assert login(client).status_code == 302
    authz = client.get("/api/me").json()["authorization"]
    assert authz["org_memberships"] == {"granted": False, "status": 403, "data": None,
                                        "error": "Must have read:org scope"}
    assert authz["teams"]["granted"] is False


def test_logout_clears_session(client, github):
    login(client)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
