import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Items, Member } from '../../lib/accounts.js';

export const projectRoles = ['admin', 'contributor', 'reviewer', 'finance', 'viewer'];

function MemberEditor({ member, path, workspace, owner, refresh }: { member: Member; path: string; workspace: boolean; owner: boolean; refresh: () => void }) {
  const [role, setRole] = useState(member.role); const [status, setStatus] = useState(member.status); const [reason, setReason] = useState('');
  const action = useAction(); const editable = !workspace || owner || member.role === 'member';
  const roles = workspace ? owner ? ['owner', 'admin', 'member'] : ['member'] : projectRoles;
  return <details className="member-row"><summary><span><strong>{member.display_name}</strong><small>{member.email}</small></span><Badge tone={member.status === 'active' && member.account_active ? 'good' : 'warning'}>{member.role} · {member.account_active ? member.status : 'account disabled'}</Badge></summary>
    <p className="small">Member ID: <code className="wrap">{member.user_id}</code></p>
    {!editable ? <p>Only a workspace owner can change this administrative membership.</p> : <form onSubmit={event => { event.preventDefault(); void action.run(() => api(`${path}/${member.user_id}`, 'PATCH', {
      role, status, reason, expected_version: member.version }), refresh); }}>
      <Feedback error={action.error} /><div className="form-grid"><SelectField label="Role" value={role} onChange={e => setRole(e.target.value)}>{roles.map(value => <option key={value} value={value}>{value}</option>)}</SelectField>
      <SelectField label="Access" value={status} onChange={e => setStatus(e.target.value as Member['status'])}><option value="active">Active</option><option value="suspended">Suspended</option></SelectField></div>
      <TextField label="Reason for this change" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} hint="Stored in the audit log. Do not include passwords or private tokens." />
      <p className="small">{workspace ? 'Suspension revokes sessions and suspends project grants. Restoring workspace access does not restore old project grants.' : 'Workspace administrators also inherit access; changing an explicit project grant cannot remove that inherited access.'}</p>
      <Submit pending={action.pending}>Save access change</Submit></form>}</details>;
}

export function Members({ path, workspace = false, owner = false }: { path: string; workspace?: boolean; owner?: boolean }) {
  const state = useResource<Items<Member>>(path);
  const action = useAction(); const [userId, setUserId] = useState(''); const [role, setRole] = useState('contributor'); const [reason, setReason] = useState('');
  return <section className="panel"><div className="section-heading"><h2>{workspace ? 'Workspace members' : 'Explicit project members'}</h2><button className="button" onClick={state.refresh}>Refresh members</button></div>
    {state.loading || state.error ? <Loading error={state.error} refresh={state.refresh} /> : <>
      {!state.data?.items.length && <p>No explicit memberships to show.</p>}
      {state.data?.items.map(member => <MemberEditor key={`${member.user_id}-${member.version}`} member={member} path={path} workspace={workspace} owner={owner} refresh={state.refresh} />)}</>}
    {!workspace && <details className="form-details"><summary>Add an existing workspace member</summary><p>Use an active workspace member ID. Workspace administrators can find it on the workspace team screen. New people must first accept an invitation.</p>
      <Feedback error={action.error} success={action.success} /><form onSubmit={event => { event.preventDefault(); void action.run(() => api(path, 'POST', { user_id: userId.trim(), role, reason }), () => { state.refresh(); setUserId(''); setReason(''); }, 'Project membership added.'); }}>
        <TextField label="Existing workspace member ID" required pattern="[0-9a-fA-F-]{36}" value={userId} onChange={e => setUserId(e.target.value)} />
        <SelectField label="Project role" value={role} onChange={e => setRole(e.target.value)}>{projectRoles.map(value => <option key={value} value={value}>{value}</option>)}</SelectField>
        <TextField label="Reason for adding this member" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /><Submit pending={action.pending}>Add to project</Submit></form></details>}
    <p className="small muted">Historical identities are preserved. Roles do not bypass independent-review rules or create contribution credit.</p></section>;
}
