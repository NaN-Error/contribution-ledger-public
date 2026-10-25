import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatDate } from '../../lib/status.js';
import { invitationUrl, type Invitation, type Items, type NewInvitation, type Project } from '../../lib/accounts.js';
import { projectRoles } from './Members.js';

function Revoke({ invitation, path, refresh }: { invitation: Invitation; path: string; refresh: () => void }) {
  const [reason, setReason] = useState(''); const action = useAction();
  return <details className="member-row"><summary><span><strong>{invitation.email}</strong><small>{invitation.project_role ?? invitation.workspace_role} · expires {formatDate(invitation.expires_at)}</small></span><Badge>{invitation.status}</Badge></summary>
    {invitation.status === 'pending' && <form onSubmit={event => { event.preventDefault(); void action.run(() => api(`${path}/${invitation.id}`, 'DELETE', { reason }), refresh); }}>
      <Feedback error={action.error} /><TextField label="Reason for revocation" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /><Submit pending={action.pending}>Revoke invitation</Submit></form>}</details>;
}

export function Invitations({ workspaceId, owner }: { workspaceId: string; owner: boolean }) {
  const base = `/api/v1/workspaces/${workspaceId}`; const [offset, setOffset] = useState(0);
  const rows = useResource<Items<Invitation>>(`${base}/invitations?offset=${offset}`);
  const projects = useResource<Items<Project>>(`${base}/projects`);
  const [email, setEmail] = useState(''); const [workspaceRole, setWorkspaceRole] = useState('member');
  const [projectId, setProjectId] = useState(''); const [role, setRole] = useState('contributor'); const [hours, setHours] = useState('72');
  const [reason, setReason] = useState(''); const [created, setCreated] = useState<NewInvitation | null>(null);
  const [copyMessage, setCopyMessage] = useState(''); const action = useAction();
  const url = created ? invitationUrl(window.location.origin, window.location.pathname, created.accept_fragment) : '';
  return <div className="guide-grid"><section className="panel"><h2>Invite a collaborator</h2><p>An invitation is single-use. Creating another invitation for the same email and workspace revokes the earlier pending one.</p>
    <Feedback error={action.error} /><form onSubmit={event => { event.preventDefault(); setCreated(null); setCopyMessage(''); void action.run(() => api<NewInvitation>(`${base}/invitations`, 'POST', {
      email, workspace_role: workspaceRole, project_id: projectId || null, project_role: projectId ? role : null,
      expires_in_hours: Number(hours), reason }), value => { setCreated(value); setOffset(0); rows.refresh(); }); }}>
      <TextField label="Invited email" type="email" autoComplete="off" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} />
      <SelectField label="Workspace role" value={workspaceRole} onChange={e => setWorkspaceRole(e.target.value)}><option value="member">Member · selected projects only</option>{owner && <option value="admin">Administrator · all workspace projects</option>}</SelectField>
      {projects.loading || projects.error ? <Loading error={projects.error} refresh={projects.refresh} /> : <SelectField label="Initial project" value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">No explicit project grant</option>{projects.data?.items.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</SelectField>}
      {projectId && <SelectField label="Project role" value={role} onChange={e => setRole(e.target.value)}>{projectRoles.map(value => <option key={value} value={value}>{value}</option>)}</SelectField>}
      <TextField label="Invitation validity in hours" type="number" required min={1} max={168} value={hours} onChange={e => setHours(e.target.value)} />
      <TextField label="Reason for inviting this collaborator" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      <Submit pending={action.pending}>Create invitation</Submit></form>
    {created && <div className="secret-result"><h3>Share privately with {created.email}</h3><p>This link is shown only now and expires {formatDate(created.expires_at)}. No email has been sent. It works only from a computer that can reach this local deployment.</p>
      <TextArea label="One-time invitation link" readOnly value={url} rows={4} /><TextField label="Invitation token for manual entry" readOnly value={created.token} />
      <button className="button" onClick={() => { void (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject(new Error('Clipboard unavailable'))).then(() => setCopyMessage('Invitation copied. Share it privately.')).catch(() => setCopyMessage('Clipboard access is unavailable. Select and copy the link above.')); }}>Copy invitation</button>
      <button className="button subtle" onClick={() => setCreated(null)}>Hide invitation secret</button><p role="status">{copyMessage}</p></div>}</section>
    <section className="panel"><div className="section-heading"><h2>Invitation history</h2><button className="button" onClick={rows.refresh}>Refresh history</button></div>
      {rows.loading || rows.error ? <Loading error={rows.error} refresh={rows.refresh} /> : <>{!rows.data?.items.length && <p>No invitations have been created.</p>}
        {rows.data?.items.map(invitation => <Revoke key={`${invitation.id}-${invitation.status}`} invitation={invitation} path={`${base}/invitations`} refresh={rows.refresh} />)}
        <div className="button-row"><button className="button" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 50))}>Previous</button><button className="button" disabled={rows.data?.next_offset == null} onClick={() => setOffset(rows.data?.next_offset ?? offset)}>Next</button></div></>}
      <p className="small">Expired and accepted invitations remain as history. An invitation cannot silently reactivate suspended access or change an existing workspace role.</p></section></div>;
}
