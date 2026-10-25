import { isAuthSession, type AuthSession } from './accounts.js';
let csrfToken: string | null = null;
let sessionFlight: Promise<AuthSession> | null = null;
let sessionRevision = 0;
let latestSession: AuthSession | null = null;

export class RequestFailure extends Error {
  constructor(message: string, public readonly code: string, public readonly status: number,
    public readonly requestId: string | null = null) { super(message); this.name = 'RequestFailure'; }
}

export function rememberSession(session: AuthSession): void {
  if (!isAuthSession(session)) throw new RequestFailure('The session response is invalid.', 'invalid_session', 502);
  csrfToken = session.csrf_token; latestSession = session; sessionRevision++;
}

export async function api<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  if (!path.startsWith('/api/v1/') || path.includes('://')) throw new Error('Only local API routes are allowed.');
  const unsafe = !['GET', 'HEAD'].includes(method);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (unsafe) {
    headers['Content-Type'] = 'application/json';
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }
  let response: Response;
  try {
    response = await fetch(path, { method, headers, credentials: 'same-origin', cache: 'no-store',
      body: unsafe ? JSON.stringify(body ?? {}) : undefined, signal });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new RequestFailure('The local API is unavailable. Check its status before retrying.', 'network_error', 0);
  }
  const requestId = response.headers.get('X-Request-ID');
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new RequestFailure('The server returned an unreadable response.', 'invalid_response', response.status, requestId); }
  if (!response.ok) {
    const record = value as { error?: { message?: unknown; code?: unknown } } | null;
    const message = typeof record?.error?.message === 'string' ? record.error.message : 'The request could not be completed.';
    const code = typeof record?.error?.code === 'string' ? record.error.code : 'request_failed';
    if (response.status === 401 && ['authentication_required', 'session_expired'].includes(code) && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('ledger-session-expired'));
    }
    throw new RequestFailure(message, code, response.status, requestId);
  }
  return value as T;
}

export function loadSession(): Promise<AuthSession> {
  // Deduplicate concurrent startup/focus/StrictMode calls: different anonymous
  // cookies must not race against different synchronizer tokens in one tab.
  if (!sessionFlight) {
    const startedAt = sessionRevision;
    sessionFlight = api<unknown>('/api/v1/auth/session').then(value => {
      // A late background check must not overwrite a newer login/logout result.
      if (sessionRevision !== startedAt && latestSession) return latestSession;
      if (!isAuthSession(value)) throw new RequestFailure('The session response is invalid.', 'invalid_session', 502);
      rememberSession(value); return value;
    }).finally(() => { sessionFlight = null; });
  }
  return sessionFlight;
}

export function explainError(error: unknown): string {
  if (error instanceof RequestFailure) return `${error.message}${error.requestId ? ` Request ID: ${error.requestId}` : ''}`;
  return error instanceof Error ? error.message : 'An unexpected error occurred.';
}
