from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

REQUESTED_SCOPES = ["read:user", "user:email", "read:org"]

ROLE_PERMISSIONS = {
    "admin": ["profile:read", "users:read", "users:write", "admin:access"],
    "user": ["profile:read"],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_url: str = "https://github.com/login/oauth"
    github_api_url: str = "https://api.github.com"

    # Public URL of the UI. The OAuth callback is served under it via the
    # Vite dev proxy / nginx, so UI and API share one origin for cookies.
    frontend_url: str = "http://localhost:5173"
    redirect_uri: str = ""

    jwt_secret: str = "change-me"
    jwt_issuer: str = "sample-sso"
    session_ttl_hours: int = 8
    cookie_secure: bool = False

    # Comma-separated GitHub logins that get the app "admin" role.
    admin_github_logins: str = ""

    database_path: str = "app.db"

    @property
    def callback_url(self) -> str:
        return self.redirect_uri or f"{self.frontend_url.rstrip('/')}/auth/github/callback"

    @property
    def admin_logins(self) -> set[str]:
        return {s.strip().lower() for s in self.admin_github_logins.split(",") if s.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
