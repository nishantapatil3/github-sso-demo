export type Optional<T = unknown> = {
  granted: boolean;
  status: number;
  data: T | null;
  error?: string;
};

export type Me = {
  user: {
    id: string;
    github_id: number;
    login: string;
    name: string | null;
    email: string | null;
    avatar_url: string | null;
    role: string;
    created_at: string;
    last_login_at: string;
  };
  identity: Record<string, unknown>;
  emails: Optional<Array<Record<string, unknown>>>;
  authentication: Record<string, unknown>;
  session: {
    type: string;
    cookie_name: string;
    cookie_attributes: Record<string, unknown>;
    claims: Record<string, unknown>;
    issued_at: string;
    expires_at: string;
    expires_in_seconds: number;
  };
  authorization: {
    app_role: string;
    permissions: string[];
    role_source: string;
    github_site_admin: boolean;
    orgs: Optional<Array<Record<string, any>>>;
    org_memberships: Optional<Array<Record<string, any>>>;
    teams: Optional<Array<Record<string, any>>>;
  };
};

export type CallResult = { status: number; body: unknown };

export async function call(path: string, init?: RequestInit): Promise<CallResult> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  const text = await res.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON body */
  }
  return { status: res.status, body };
}

export const getMe = () => call("/api/me");
export const logout = () => call("/auth/logout", { method: "POST" });
