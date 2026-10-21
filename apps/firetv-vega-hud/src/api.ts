// Muni backend client for the Vega HUD.
// No credentials are embedded: the operator types them on the TV login screen.

export const DEFAULT_BACKEND = 'https://100-49-183-59.sslip.io';

export type Json = any;

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let counter = 0;
export function idempotencyKey(prefix: string): string {
  counter += 1;
  return `tv-${prefix}-${Date.now().toString(36)}-${counter}-${Math.random()
    .toString(36)
    .slice(2, 10)}`;
}

export function normalizeBase(url: string): string {
  let u = (url || '').trim();
  if (!u) {
    return DEFAULT_BACKEND;
  }
  if (!/^https?:\/\//i.test(u)) {
    u = 'https://' + u;
  }
  return u.replace(/\/+$/, '');
}

export class DoneIrlClient {
  base: string;
  token: string | null = null;
  user: string | null = null;
  role: string | null = null;

  constructor(base: string) {
    this.base = normalizeBase(base);
  }

  headers(json: boolean): Record<string, string> {
    const h: Record<string, string> = {Accept: 'application/json'};
    if (json) {
      h['Content-Type'] = 'application/json';
    }
    if (this.token) {
      h.Authorization = 'Bearer ' + this.token;
    }
    return h;
  }

  async parse(res: any): Promise<Json> {
    const text = await res.text();
    let body: Json = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch (e) {
      body = null;
    }
    if (!res.ok) {
      const err = body && body.error ? body.error : {};
      throw new ApiError(
        res.status,
        err.code || 'HTTP_' + res.status,
        err.message || 'Request failed (' + res.status + ').',
      );
    }
    return body;
  }

  async login(username: string, password: string): Promise<Json> {
    const res = await fetch(this.base + '/api/auth/login', {
      method: 'POST',
      headers: this.headers(true),
      body: JSON.stringify({username, password}),
      credentials: 'include',
    });
    const body = await this.parse(res);
    // The backend issues the session as the `done_session` cookie. Read it when the
    // platform exposes Set-Cookie so we can use `Authorization: Bearer`; otherwise the
    // native cookie jar carries the session (credentials: 'include').
    const raw = res.headers.get('set-cookie') || res.headers.get('Set-Cookie') || '';
    const m = /done_session=([^;,\s]+)/.exec(raw);
    this.token = m ? m[1] : null;
    this.user = body && body.user;
    this.role = body && body.role;
    return body;
  }

  async get(path: string): Promise<Json> {
    const res = await fetch(this.base + path, {
      method: 'GET',
      headers: this.headers(false),
      credentials: 'include',
    });
    return this.parse(res);
  }

  async post(path: string, body: Json, keyPrefix: string): Promise<Json> {
    const h = this.headers(true);
    h['Idempotency-Key'] = idempotencyKey(keyPrefix);
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: h,
      body: JSON.stringify(body || {}),
      credentials: 'include',
    });
    return this.parse(res);
  }

  async logout(): Promise<void> {
    try {
      await this.post('/api/auth/logout', {}, 'logout');
    } catch (e) {
      // Session may already be expired; local state is cleared regardless.
    }
    this.token = null;
    this.user = null;
    this.role = null;
  }

  frameSource(path: string, bust: number) {
    const headers: Record<string, string> = {};
    if (this.token) {
      headers.Authorization = 'Bearer ' + this.token;
    }
    return {uri: this.base + path + '?t=' + bust, headers};
  }
}
