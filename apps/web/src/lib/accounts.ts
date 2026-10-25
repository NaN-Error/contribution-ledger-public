export interface User { id: string; email: string; display_name: string }
export interface AuthSession { user: User | null; csrf_token: string; session_id: string; expires_at: string; bootstrap_required: boolean; password_min_length: number; mfa_required?: boolean; mfa_enrolled?: boolean }
export interface Workspace { id: string; name: string; role: 'owner' | 'admin' | 'member'; can_manage: boolean }
export interface Project { id: string; workspace_id: string; name: string; description: string; timezone: string; currency: string; version: number; role: string; can_manage: boolean }
export interface Member { user_id: string; display_name: string; email: string; account_active: boolean; role: string; status: 'active' | 'suspended'; version: number }
export interface Invitation { id: string; email: string; workspace_role: string; project_id: string | null; project_role: string | null; status: string; expires_at: string; created_at: string }
export interface NewInvitation extends Invitation { token: string; accept_fragment: string }
export interface InviteInfo { email: string; workspace_name: string; project_name: string | null; workspace_role: string; project_role: string | null; expires_at: string; existing_account: boolean; matching_account: boolean }
export interface SessionItem { id: string; created_at: string; last_seen_at: string; expires_at: string; current: boolean }
export interface AuditItem { id: string; created_at: string; actor_id: string | null; action: string; subject_id: string | null; project_id: string | null; reason: string; details: Record<string, unknown> }
export interface Items<T> { items: T[]; next_offset?: number | null }
export type EntryMode = 'login' | 'bootstrap' | 'invite' | 'recover';
export interface Entry { mode: EntryMode; token: string }

export function isAuthSession(value: unknown): value is AuthSession {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<AuthSession>;
  return typeof v.csrf_token === 'string' && /^[a-f0-9]{64}$/.test(v.csrf_token)
    && (v.mfa_required === undefined || typeof v.mfa_required === 'boolean')
    && (v.mfa_enrolled === undefined || typeof v.mfa_enrolled === 'boolean')
    && !(v.mfa_required && v.user)
    && typeof v.bootstrap_required === 'boolean' && typeof v.expires_at === 'string'
    && Number.isFinite(Date.parse(v.expires_at)) && typeof v.session_id === 'string'
    && typeof v.password_min_length === 'number' && (v.user === null ||
      (typeof v.user === 'object' && !!v.user && typeof v.user.id === 'string'
        && typeof v.user.email === 'string' && typeof v.user.display_name === 'string'));
}

export function entryFromHash(hash: string): Entry | null {
  const match = /^#(invite|recover)(?:\/([A-Za-z0-9_-]{43}))?$/.exec(hash);
  return match ? { mode: match[1] as EntryMode, token: match[2] ?? '' } : null;
}

export function authenticatedAppHash(hash:string):string {
  // Keep in-app destinations through sign-in; discard consumed account tokens.
  if (['#analysis','#projects','#guide','#account','#overview','#setup','#roadmap'].includes(hash)
      || hash.startsWith('#analysis?') || hash.startsWith('#projects?')) return hash;
  return '#analysis';
}

export function invitationUrl(origin: string, path: string, fragment: string): string {
  if (!/^#invite\/[A-Za-z0-9_-]{43}$/.test(fragment)) throw new Error('Invalid invitation fragment.');
  const url = new URL(path, origin);
  if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol)) throw new Error('Invalid application address.');
  url.search = ''; url.hash = fragment;
  return url.toString();
}
