import { useState } from 'react';
import { MfaPanel, type EnrollmentHandler } from './Mfa.js';
import { TextField } from '../../components/shared.js';
import { Feedback, Loading, Submit } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatDate } from '../../lib/status.js';
import type { AuthSession, Items, SessionItem } from '../../lib/accounts.js';

export function Account({ session, onSession, onEnrollment }: { session: AuthSession; onSession: (s: AuthSession) => void; onEnrollment: EnrollmentHandler }) {
  const rows = useResource<Items<SessionItem>>('/api/v1/auth/sessions');
  const action = useAction();
  const [current, setCurrent] = useState(''); const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  return <><div className="page-heading"><div><p className="eyebrow">Your account</p><h1>Account and sessions</h1><p>{session.user?.display_name} · {session.user?.email}</p></div></div>
    <MfaPanel session={session} onSession={onSession} onEnrollment={onEnrollment}/><Feedback error={action.error} success={action.success} /><div className="guide-grid"><section className="panel"><h2>Change password</h2><p>Changing your password revokes other sessions. Your current browser receives a new session.</p>
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
        if (password !== confirm) throw new Error('The passwords do not match.');
        return api<AuthSession>('/api/v1/auth/password', 'POST', { current_password: current, password });
      }, value => { onSession(value); setCurrent(''); setPassword(''); setConfirm(''); rows.refresh(); }, 'Password changed; other sessions revoked.'); }}>
        <TextField label="Current password" type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={e => setCurrent(e.target.value)} />
        <TextField label="New password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} />
        <TextField label="Confirm new password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirm} onChange={e => setConfirm(e.target.value)} />
        <Submit pending={action.pending}>Update password</Submit></form></section>
    <section className="panel"><div className="section-heading"><h2>Unrevoked sessions</h2><button className="button" onClick={rows.refresh}>Refresh</button></div><p>Sessions expire after 30 minutes of inactivity or 8 hours overall. A listed session may already be idle-expired.</p>
      {rows.loading || rows.error ? <Loading error={rows.error} refresh={rows.refresh} /> : rows.data?.items.map(row => <div className="session-row" key={row.id}><strong>{row.current ? 'This browser' : 'Another session'}</strong>
        <p>Started {formatDate(row.created_at)}<br />Last application activity {formatDate(row.last_seen_at)}</p>
        {!row.current && <button className="button" disabled={action.pending} onClick={() => void action.run(() => api(`/api/v1/auth/sessions/${row.id}`, 'DELETE'), rows.refresh, 'Session revoked.')}>Revoke session</button>}</div>)}
      <p className="small">Lost access? The local operator can issue an audited recovery token after verifying your identity. Account disablement is also an operator action.</p></section></div></>;
}
