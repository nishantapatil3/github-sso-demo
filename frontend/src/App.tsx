import { useEffect, useState, type ReactNode } from "react";
import { call, getMe, logout, type CallResult, type Me, type Optional } from "./api";

function fmt(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  if (typeof value === "boolean") return <span className={value ? "yes" : "no"}>{value ? "true" : "false"}</span>;
  if (Array.isArray(value) && value.every((v) => typeof v !== "object")) {
    return value.length ? value.map((v) => <code key={String(v)} className="chip">{String(v)}</code>) : <span className="muted">none</span>;
  }
  if (typeof value === "object") return <pre className="inline-json">{JSON.stringify(value, null, 2)}</pre>;
  const s = String(value);
  if (/^https?:\/\//.test(s)) return <a href={s} target="_blank" rel="noreferrer">{s}</a>;
  return s;
}

function KV({ data }: { data: Record<string, unknown> }) {
  return (
    <table className="kv">
      <tbody>
        {Object.entries(data).map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{fmt(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {subtitle && <p className="subtitle">{subtitle}</p>}
      {children}
    </section>
  );
}

function Grant({ result, children }: { result: Optional<unknown>; children: ReactNode }) {
  if (!result.granted) {
    return (
      <p className="warn">
        Not granted (HTTP {result.status}): {result.error ?? "unknown error"}
      </p>
    );
  }
  return <>{children}</>;
}

function Table({ rows, cols }: { rows: Array<Record<string, unknown>>; cols: Array<[string, (r: any) => unknown]> }) {
  if (!rows.length) return <p className="muted">None</p>;
  return (
    <table className="grid">
      <thead>
        <tr>{cols.map(([h]) => <th key={h}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{cols.map(([h, get]) => <td key={h}>{fmt(get(r))}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function Countdown({ seconds }: { seconds: number }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);
  const h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
  return <span>{`${h}h ${m}m ${s}s`}</span>;
}

function AuthzTests() {
  const [results, setResults] = useState<Record<string, CallResult>>({});
  const run = async (path: string) => {
    const r = await call(path);
    setResults((prev) => ({ ...prev, [path]: r }));
  };
  return (
    <div className="tests">
      {["/api/user-only", "/api/admin-only"].map((path) => (
        <div key={path} className="test">
          <button onClick={() => run(path)}>GET {path}</button>
          {results[path] && (
            <span className={results[path].status < 300 ? "yes" : "no"}>
              HTTP {results[path].status} — {JSON.stringify(results[path].body)}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function Dashboard({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const { user, identity, emails, authentication, session, authorization: authz } = me;
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(me, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <>
      <header className="hero">
        {user.avatar_url && <img src={user.avatar_url} alt="" />}
        <div className="who">
          <div className="status">✅ SSO login successful</div>
          <h1>{user.name ?? user.login}</h1>
          <div>
            @{user.login} · {user.email ?? "no public email"} ·{" "}
            <span className={`badge ${user.role}`}>{user.role}</span>
          </div>
        </div>
        <button className="secondary" onClick={onLogout}>Log out</button>
      </header>

      <div className="cards">
        <Card title="App user" subtitle="Local account linked to the GitHub identity (SQLite)">
          <KV data={user} />
        </Card>

        <Card title="Authentication (AuthN)" subtitle="How this login was established">
          <KV data={authentication} />
        </Card>

        <Card title="Session" subtitle={session.type}>
          <KV
            data={{
              cookie_name: session.cookie_name,
              ...Object.fromEntries(Object.entries(session.cookie_attributes).map(([k, v]) => [`cookie.${k}`, v])),
              issued_at: session.issued_at,
              expires_at: session.expires_at,
            }}
          />
          <p>Time remaining: <Countdown seconds={session.expires_in_seconds} /></p>
          <h3>Decoded JWT claims</h3>
          <KV data={session.claims} />
        </Card>

        <Card title="Authorization (AuthZ)" subtitle={`Role source: ${authz.role_source}`}>
          <KV
            data={{
              app_role: authz.app_role,
              permissions: authz.permissions,
              github_site_admin: authz.github_site_admin,
            }}
          />
          <h3>Live authorization checks</h3>
          <AuthzTests />
        </Card>

        <Card title="GitHub org memberships & roles" subtitle="GET /user/memberships/orgs (needs read:org)">
          <Grant result={authz.org_memberships}>
            <Table
              rows={authz.org_memberships.data ?? []}
              cols={[
                ["org", (r) => r.organization?.login],
                ["role", (r) => r.role],
                ["state", (r) => r.state],
              ]}
            />
          </Grant>
        </Card>

        <Card title="GitHub teams" subtitle="GET /user/teams (needs read:org)">
          <Grant result={authz.teams}>
            <Table
              rows={authz.teams.data ?? []}
              cols={[
                ["org", (r) => r.organization?.login],
                ["team", (r) => r.name],
                ["slug", (r) => r.slug],
                ["permission", (r) => r.permission],
                ["privacy", (r) => r.privacy],
              ]}
            />
          </Grant>
        </Card>

        <Card title="GitHub orgs" subtitle="GET /user/orgs">
          <Grant result={authz.orgs}>
            <Table
              rows={authz.orgs.data ?? []}
              cols={[
                ["login", (r) => r.login],
                ["id", (r) => r.id],
                ["description", (r) => r.description],
              ]}
            />
          </Grant>
        </Card>

        <Card title="Emails" subtitle="GET /user/emails (needs user:email)">
          <Grant result={emails}>
            <Table
              rows={emails.data ?? []}
              cols={[
                ["email", (r) => r.email],
                ["primary", (r) => r.primary],
                ["verified", (r) => r.verified],
                ["visibility", (r) => r.visibility],
              ]}
            />
          </Grant>
        </Card>

        <Card title="Identity — GitHub profile" subtitle="Full GET /user payload">
          <KV data={identity} />
        </Card>

        <Card title="Raw /api/me response">
          <details>
            <summary>Show JSON</summary>
            <button className="secondary small" onClick={copy}>{copied ? "Copied!" : "Copy JSON"}</button>
            <pre className="raw">{JSON.stringify(me, null, 2)}</pre>
          </details>
        </Card>
      </div>
    </>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<CallResult | null>(null);
  const error = new URLSearchParams(window.location.search).get("error");

  const load = async () => {
    setLoading(true);
    const r = await getMe();
    setStatus(r);
    setMe(r.status === 200 ? (r.body as Me) : null);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleLogout = async () => {
    await logout();
    window.history.replaceState(null, "", "/");
    await load();
  };

  if (loading) return <main className="center">Loading…</main>;

  return (
    <main>
      {me ? (
        <Dashboard me={me} onLogout={handleLogout} />
      ) : (
        <div className="login">
          <h1>GitHub SSO Demo</h1>
          <p>Sign in with a GitHub OAuth App and inspect every detail of the resulting identity, session and roles.</p>
          {error && <p className="warn">Login failed: {error}</p>}
          <a className="gh-button" href="/auth/github/login">
            <svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">
              <path
                fill="currentColor"
                d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
              />
            </svg>
            Sign in with GitHub
          </a>
          {status && (
            <p className="muted small">
              GET /api/me → HTTP {status.status} {JSON.stringify(status.body)}
            </p>
          )}
        </div>
      )}
    </main>
  );
}
