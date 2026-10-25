import { useState } from 'react';
import { Feedback, Loading, Submit } from '../../components/forms.js';
import { TextField } from '../../components/shared.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { AuthSession } from '../../lib/accounts.js';

interface FactorStatus { enabled: boolean; required: boolean; key_available: boolean; recovery_codes_remaining: number; pending_login: boolean }
interface Enrollment { secret: string; uri: string; expires_at: string; warning: string }
export type EnrollmentHandler = (session: AuthSession, codes: string[]) => void;
export function MfaPanel({ session, onSession, onEnrollment }: { session: AuthSession; onSession: (s: AuthSession) => void; onEnrollment: EnrollmentHandler }) {
  const status = useResource<FactorStatus>('/api/v1/auth/mfa/status'); const action = useAction();
  const [password, setPassword] = useState(''); const [code, setCode] = useState('');
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  if (status.loading || status.error) return <Loading error={status.error} refresh={status.refresh} />;
  if (!status.data) return null;
  const factor = status.data;
  return <section className="panel"><h2>Authenticator protection</h2>
    <p>{factor.enabled ? `Enabled. ${factor.recovery_codes_remaining} unused recovery codes remain.` : 'Use an authenticator app with a six-digit code that changes every 30 seconds.'}</p>
    <Feedback error={action.error} success={action.success} />
    {!factor.key_available && <p role="alert">The protected authentication key is unavailable. The operator must initialize or restore it before enrollment. Do not create a replacement key over existing factors.</p>}
    {factor.enabled && session.mfa_required ? <form onSubmit={e => { e.preventDefault(); void action.run(() => api<AuthSession>('/api/v1/auth/mfa/verify','POST',{code}), value => {setCode('');onSession(value);}); }}>
      <p>Your password was checked. Project access remains blocked until this step succeeds. This challenge expires after five minutes.</p>
      <TextField label="Authenticator or unused recovery code" type="password" autoComplete="one-time-code" required minLength={6} maxLength={40} value={code} onChange={e=>setCode(e.target.value)} />
      <Submit pending={action.pending}>Verify and sign in</Submit></form> : !factor.enabled ? <>
        {!enrollment ? <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<Enrollment>('/api/v1/auth/mfa/enroll','POST',{password}),value=>{setPassword('');setEnrollment(value);});}}>
          <TextField label="Current password" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/>
          <button className="button primary" type="submit" disabled={action.pending || !factor.key_available}>Begin enrollment</button></form> : <>
          <p>Add a new time-based account in your authenticator. Enter this setup key manually; it is not sent to a QR service.</p>
          <TextField label="Private authenticator setup key" readOnly value={enrollment.secret} autoComplete="off" />
          <p className="small">Issuer: Contribution ledger. Six digits, SHA-1, 30-second interval. Do not put this key in a report, chat, screenshot, or shared clipboard.</p>
          <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<{session:AuthSession;recovery_codes:string[]}>('/api/v1/auth/mfa/confirm','POST',{code}),value=>{setCode('');setEnrollment(null);onEnrollment(value.session,value.recovery_codes);});}}>
            <TextField label="Code from your authenticator" type="password" inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} value={code} onChange={e=>setCode(e.target.value)} />
            <Submit pending={action.pending}>Confirm authenticator</Submit></form></>}
      </> : <>
      <p>Enabled factors are checked on every new login. Enrollment revokes earlier sessions. A password reset does not remove the factor.</p>
      {!factor.required && <details><summary>Disable this factor on the local deployment</summary>
        <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<AuthSession>('/api/v1/auth/mfa/disable','POST',{password,code}),value=>{setCode('');setPassword('');onSession(value);status.refresh();},'Factor disabled; earlier sessions revoked.');}}>
          <TextField label="Current password" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/>
          <TextField label="Unused authenticator or recovery code" type="password" autoComplete="one-time-code" required maxLength={40} value={code} onChange={e=>setCode(e.target.value)}/>
          <Submit pending={action.pending}>Confirm factor removal</Submit></form></details>}
      {factor.required && <p>This deployment requires MFA. Disabling it is not available.</p>}</>}
    <p className="small">Authenticator codes are not phishing-resistant. Verify the application address; never share a current code. Lost factors require the documented operator identity-verification procedure.</p>
  </section>;
}
export function RecoveryCodes({codes,onDone}:{codes:string[];onDone:()=>void}) {
  const [saved,setSaved]=useState(false);
  return <main className="auth-shell"><section className="panel auth-card"><h1>Save your recovery codes</h1><p>Each code works once, together with your password. Store them separately from your authenticator. They will not be displayed again.</p>
    <pre className="evidence-text" aria-label="Private single-use recovery codes">{codes.join('\n')}</pre>
    <label><input type="checkbox" checked={saved} onChange={e=>setSaved(e.target.checked)}/> I have saved these codes privately.</label>
    <button className="button primary" disabled={!saved} onClick={onDone}>Continue</button></section></main>;
}
