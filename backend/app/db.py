import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    github_id INTEGER NOT NULL UNIQUE,
    login TEXT NOT NULL,
    name TEXT,
    email TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL,
    github_snapshot TEXT NOT NULL,
    last_auth TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL
)
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(get_settings().database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def _row_to_user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    user = dict(row)
    user["github_snapshot"] = json.loads(user["github_snapshot"])
    user["last_auth"] = json.loads(user["last_auth"])
    return user


def upsert_user(profile: dict, email: str | None, role: str, snapshot: dict, last_auth: dict) -> dict:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, github_id, login, name, email, avatar_url, role,
                               github_snapshot, last_auth, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(github_id) DO UPDATE SET
                login = excluded.login,
                name = excluded.name,
                email = excluded.email,
                avatar_url = excluded.avatar_url,
                role = excluded.role,
                github_snapshot = excluded.github_snapshot,
                last_auth = excluded.last_auth,
                last_login_at = excluded.last_login_at
            """,
            (
                str(uuid.uuid4()),
                profile["id"],
                profile["login"],
                profile.get("name"),
                email,
                profile.get("avatar_url"),
                role,
                json.dumps(snapshot),
                json.dumps(last_auth),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM users WHERE github_id = ?", (profile["id"],)).fetchone()
    return _row_to_user(row)


def get_user(user_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row)
