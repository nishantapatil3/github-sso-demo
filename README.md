# GitHub OAuth SSO — sample app

A small app for checking that SSO with a GitHub **OAuth App** works. After you sign in with GitHub, the web UI shows everything about the login:

- **Identity:** the full GitHub profile and your emails
- **Authentication (AuthN):** the OAuth flow, client ID, redirect URI, whether the `state` check passed, the scopes requested vs. granted, a masked token, and the rate limit
- **Session:** the decoded JWT claims, when it expires (with a live countdown), and the cookie attributes
- **Authorization (AuthZ):**
  - the app role (`admin` or `user`) and its permissions
  - your GitHub org memberships with your role in each, your teams, and `site_admin`
  - buttons that call a user-only and an admin-only endpoint and show the result
- **Raw JSON:** the whole `/api/me` response

Stack: **FastAPI** backend, **React + Vite** UI, and **SQLite** to store users. The session is a JWT signed by the backend, kept in an **HttpOnly cookie**. The browser's JavaScript never sees a token, and the GitHub access token is used only during login and then thrown away.

```
Browser ── http://localhost:5173 ──► Vite dev server / nginx ──┬─ /           → React UI
                                                              ├─ /auth/*     → FastAPI
                                                              └─ /api/*      → FastAPI ──► github.com / api.github.com
```

## 1. Create the GitHub OAuth App

1. Go to GitHub → **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. Fill in:
   - **Homepage URL:** `http://localhost:5173`
   - **Authorization callback URL:** `http://localhost:5173/auth/github/callback`
3. Copy the **Client ID**, then click **Generate a new client secret** and copy it too.

> If your org restricts OAuth App access, an org admin must approve the app before its memberships and teams show up. Until then, those sections show only public data or "not granted".

## 2. Configure

```bash
cp .env.example .env              # for Docker Compose
# or: cp backend/.env.example backend/.env   for local dev
```

| Variable | Purpose |
|---|---|
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | From the OAuth App |
| `JWT_SECRET` | Signs the session cookie. Generate one with `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `FRONTEND_URL` | Public URL of the UI. The callback is `$FRONTEND_URL/auth/github/callback` |
| `COOKIE_SECURE` | `true` when the app is served over HTTPS |
| `ADMIN_GITHUB_LOGINS` | Comma-separated GitHub logins that get the `admin` role (e.g. your own login, to test admin-only) |

## 3a. Run with Docker Compose (recommended on Mac)

```bash
docker compose up --build        # open http://localhost:5173
docker compose down              # stop (users are kept in the sso-data volume)
docker compose down -v           # stop and delete users
```

## 3b. Run locally without Docker (hot reload)

```bash
# terminal 1
cd backend && poetry install && poetry run uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm install && npm run dev       # open http://localhost:5173
```

Both modes serve the app at `localhost:5173`, so one OAuth App works for both. Run one mode at a time.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/auth/github/login` | — | Sets the `oauth_state` cookie and redirects to GitHub |
| GET | `/auth/github/callback` | — | Checks `state`, exchanges the code, fetches the profile/emails/orgs/teams, saves the user, sets the `session` cookie |
| POST | `/auth/logout` | — | Clears the session cookie |
| GET | `/api/me` | session | Returns all identity, authn, session, and authz details |
| GET | `/api/user-only` | session | Allowed for any logged-in user |
| GET | `/api/admin-only` | role=admin | Returns 403 unless your login is in `ADMIN_GITHUB_LOGINS` |
| GET | `/api/health` | — | Health check |

Requested scopes: `read:user user:email read:org`.

## Tests

```bash
cd backend && poetry run pytest
```

The tests fake GitHub's responses (with respx) and cover: the login redirect and `state` cookie, rejecting a bad or missing state, the full login, `/api/me`, the user and admin authz checks, falling back to `/user/emails` for the email, a missing `read:org` scope, and logout.

## Deploying beyond localhost

You can run the same images on any VM or container host (Render, Fly.io, ECS, …) behind HTTPS:

1. Set `FRONTEND_URL=https://your-domain` and `COOKIE_SECURE=true`.
2. Change the OAuth App's Homepage URL and callback URL to `https://your-domain` and `https://your-domain/auth/github/callback`, or create a separate OAuth App for that environment.
3. Use a strong `JWT_SECRET`, and put SQLite on persistent storage (or switch to Postgres).

## TODO

Long-lived "remember me" sessions, like Google and Facebook:

- [ ] Server-side `sessions` table in SQLite: hashed session ID, user, device/user agent, IP, created / last seen / expires. The cookie holds only a random session ID, not a signed token.
- [ ] Sliding expiry: for example 30 days, pushed forward while you're active (`SESSION_IDLE_DAYS`), with an absolute cap (`SESSION_MAX_DAYS`).
- [ ] Revocation: logout deletes the server record. "Log out of all devices" deletes all of a user's sessions. Changing `ADMIN_GITHUB_LOGINS` or deleting a user takes effect immediately.
- [ ] Sessions card on the dashboard: list active sessions (device, IP, last seen, this-session marker), revoke one, log out everywhere.
- [ ] Optional: short access token (~15 min) plus a rotating refresh token, where reusing an old refresh token kills the whole chain.
- [ ] Optional: ask for a fresh GitHub login on sensitive actions (re-login if the last login was more than N minutes ago).
- [ ] Tests for sliding expiry, revocation, log out everywhere, and refresh-token reuse.
