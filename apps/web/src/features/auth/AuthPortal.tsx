import { useState, type FormEvent } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Submit } from '../../components/forms.js';
import { useAction } from '../../hooks/useApi.js';
import { api, rememberSession } from '../../lib/api.js';
import type { AuthSession, Entry, EntryMode, InviteInfo } from '../../lib/accounts.js';

export function AuthPortal({ session, entry, onSession, onClose }: { session: AuthSession; entry: Entry | null;
  onSession: (value: AuthSession) => void; onClose: () => void }) {
  const [mode, setMode] = useState<EntryMode>(entry?.mode ?? (session.bootstrap_required ? 'bootstrap' : 'login'));
  const [token, setToken] = useState(entry?.token ?? '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [name, setName] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [project, setProject] = useState('');
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const action = useAction();
  const title = mode === 'bootstrap' ? 'Set up your first workspace' : mode === 'invite' ? 'Join an invited team' : mode === 'recover' ? 'Recover your account' : 'Sign in';
  const choose = (next: EntryMode) => { setMode(next); setPassword(''); setConfirm(''); };
  function updated(value: AuthSession, close: boolean) { rememberSession(value); onSession(value); setPassword(''); setConfirm(''); if (close) onClose(); }
  async function submit(event: FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      if (['bootstrap', 'recover'].includes(mode) && password !== confirm) throw new Error('The passwords do not match.');
      if (mode === 'bootstrap') return api<AuthSession>('/api/v1/auth/bootstrap', 'POST', {
        token: token.trim(), email, display_name: name, password, workspace_name: workspace, project_name: project, timezone });
      if (mode === 'recover') return api<AuthSession>('/api/v1/auth/recover', 'POST', { token: token.trim(), password });
      return api<AuthSession>('/api/v1/auth/login', 'POST', { email, password });
    }, value => {
      if (mode === 'recover') { updated(value, false); choose('login'); setToken(''); }
      else if (mode === 'login' && info) { updated(value, false); choose('invite'); }
      else updated(value, true);
    }, mode === 'recover' ? 'Password changed. Sign in with your new password.' : undefined);
  }
  const matchingAccount = !!session.user && session.user.email === info?.email;
  return <div className="auth-shell"><section className="panel auth-card"><div className="section-heading"><Badge>Phase 5 · local pilot</Badge><a href="#setup">Local setup</a></div>
    <h1>{title}</h1><p>Accounts control project access. They do not grant contribution credit or ownership.</p>
    <Feedback error={action.error} success={action.success} />
    {mode === 'invite' ? <>
      {!info ? <form onSubmit={event => { event.preventDefault(); void action.run(() => api<InviteInfo>('/api/v1/auth/invitations/inspect', 'POST', { token: token.trim() }), setInfo); }}>
        <TextField label="Invitation token" type="password" autoComplete="off" required minLength={43} maxLength={43} value={token} onChange={event => setToken(event.target.value)} hint="The administrator must send this privately. Tokens are not kept in browser storage." />
        <Submit pending={action.pending}>Check invitation</Submit></form> : <>
        <section className="invitation-summary"><h2>{info.workspace_name}</h2><p>{info.project_name ?? 'Workspace membership'} · {info.project_role ?? info.workspace_role}</p><p>Invited email: <strong>{info.email}</strong></p></section>
        {info.existing_account && !matchingAccount ? <><p>Sign in to the invited account before accepting. An invitation cannot reset an existing password.</p>
          {session.user ? <button className="button" disabled={action.pending} onClick={() => void action.run(() => api<AuthSession>('/api/v1/auth/logout', 'POST'), value => { updated(value, false); setEmail(info.email); choose('login'); })}>Sign out to switch accounts</button>
            : <button className="button" onClick={() => { setEmail(info.email); choose('login'); }}>Sign in to accept</button>}</>
          : session.user && !matchingAccount ? <><p>You are signed in as a different person. Sign out before creating this invited account.</p><button className="button" disabled={action.pending} onClick={() => void action.run(() => api<AuthSession>('/api/v1/auth/logout', 'POST'), value => updated(value, false))}>Sign out</button></>
          : <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
              if (!info.existing_account && password !== confirm) throw new Error('The passwords do not match.');
              return api<AuthSession>('/api/v1/auth/invitations/accept', 'POST', { token: token.trim(), ...(!info.existing_account ? { display_name: name, password } : {}) });
            }, value => updated(value, true)); }}>
            {!info.existing_account && <><TextField label="Display name" autoComplete="name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} />
              <TextField label="New password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} hint="Use a unique passphrase of 15 to 128 characters." />
              <TextField label="Confirm new password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirm} onChange={e => setConfirm(e.target.value)} /></>}
            <Submit pending={action.pending}>Accept invitation</Submit></form>}
        <button className="button subtle" onClick={() => { setInfo(null); setToken(''); }}>Use another invitation</button></>}
      </> : <form onSubmit={submit}>
      {mode === 'bootstrap' && <><p>On the host computer, run <code>scripts/setup-owner.ps1</code> to obtain a one-hour setup token. Setup runs once; no default account is enabled.</p>
        <TextField label="Setup token" type="password" autoComplete="off" required minLength={43} maxLength={43} value={token} onChange={e => setToken(e.target.value)} />
        <TextField label="Display name" autoComplete="name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} /></>}
      {mode === 'recover' ? <><p>Ask the local operator to verify your identity and issue a one-time recovery token. Recovery revokes previous sessions and does not enable a disabled account.</p>
        <TextField label="Recovery token" type="password" autoComplete="off" required minLength={43} maxLength={43} value={token} onChange={e => setToken(e.target.value)} /></>
        : <TextField label="Email" type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} />}
      <TextField label={mode === 'login' ? 'Password' : 'New password'} type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'login' ? 1 : 15} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} hint={mode !== 'login' ? 'Use a unique passphrase of 15 to 128 characters.' : undefined} />
      {mode !== 'login' && <TextField label="Confirm new password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirm} onChange={e => setConfirm(e.target.value)} />}
      {mode === 'bootstrap' && <><TextField label="Workspace name" required minLength={2} maxLength={120} value={workspace} onChange={e => setWorkspace(e.target.value)} />
        <TextField label="First project name" required minLength={2} maxLength={120} value={project} onChange={e => setProject(e.target.value)} />
        <TextField label="Project timezone" required maxLength={80} value={timezone} onChange={e => setTimezone(e.target.value)} hint="An IANA timezone, such as America/Puerto_Rico. Project currency starts as USD." /></>}
      <Submit pending={action.pending}>{mode === 'bootstrap' ? 'Create owner and workspace' : mode === 'recover' ? 'Set new password' : 'Sign in'}</Submit></form>}
    <div className="auth-links"><button className="text-button" onClick={() => { setInfo(null); choose('login'); }}>Sign in</button>
      <button className="text-button" onClick={() => choose('invite')}>Use invitation</button><button className="text-button" onClick={() => { setToken(''); choose('recover'); }}>Account recovery</button>
      {session.bootstrap_required && <button className="text-button" onClick={() => { setToken(''); choose('bootstrap'); }}>First-owner setup</button>}
      {session.user && <button className="text-button" onClick={onClose}>Back to workspaces</button>}</div>
    <p className="small muted">No public registration, external account connection, or email delivery is enabled.</p>
  </section></div>;
}
