import { api, loadSession, rememberSession } from './api.js';
import { isAuthSession, type AuthSession } from './accounts.js';

export function desktopToken(hash: string): string | null {
  const match = /^#desktop\/([A-Za-z0-9_-]{43})$/.exec(hash);
  return match?.[1] ?? null;
}

export async function openDesktopSession(token: string): Promise<AuthSession> {
  // One invocation outside React StrictMode; unsafe requests are never retried.
  await loadSession();
  const value = await api<unknown>('/api/v1/auth/desktop/login', 'POST', { token });
  if (!isAuthSession(value)) throw new Error('The desktop session response is invalid. Open Start.cmd again.');
  rememberSession(value);
  return value;
}
