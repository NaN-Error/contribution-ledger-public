import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Items, Project } from '../../lib/accounts.js';
import { formatUnits, parseUnits, type Milestone, type MilestoneDetail as MilestoneRecord, type Policy, type PolicyCollection } from '../../lib/planning.js';
import { MilestoneDetail } from './MilestoneDetail.js';

function CreateMilestone({ root, policies, onCreated }: { root: string; policies: Policy[]; onCreated: (item: MilestoneRecord) => void }) {
  const [policyId, setPolicyId] = useState(policies[0].id); const [name, setName] = useState(''); const [description, setDescription] = useState('');
  const [total, setTotal] = useState(''); const [reserve, setReserve] = useState('0'); const [reason, setReason] = useState(''); const action = useAction();
  return <section className="panel form-panel"><h3>Create a milestone and propose its initial budget</h3><p>Approved totals begin at zero. A separate human approval activates the proposed budget.</p><Feedback error={action.error} /><form onSubmit={e => { e.preventDefault(); void action.run(() => api<MilestoneRecord>(root, 'POST', { name, description, policy_id: policyId,
    total_atoms: parseUnits(total), reserve_floor_atoms: parseUnits(reserve), reason }), onCreated); }}>
    <SelectField label="Approved policy for this milestone" value={policyId} onChange={e => setPolicyId(e.target.value)}>{policies.map(p => <option key={p.id} value={p.id}>Version {p.version}: {p.title}</option>)}</SelectField>
    <TextField label="Milestone name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} />
    <TextArea label="Milestone description" rows={3} maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} />
    <div className="form-grid"><TextField label="Initial total units" required inputMode="decimal" value={total} onChange={e => setTotal(e.target.value)} placeholder="For example, 1000" hint="Up to three decimal places. Unit budgets are not money." /><TextField label="Initial protected reserve units" required inputMode="decimal" value={reserve} onChange={e => setReserve(e.target.value)} hint="Reserve is unowned capacity within the total, not added on top." /></div>
    <TextField label="Reason for initial budget" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
    <Submit pending={action.pending}>Create milestone proposal</Submit>
  </form></section>;
}
export function Milestones({ project }: { project: Project }) {
  const base = `/api/v1/workspaces/${project.workspace_id}/projects/${project.id}`;
  const state = useResource<Items<Milestone>>(base + '/milestones'); const policies = useResource<PolicyCollection>(base + '/policies');
  const [selected, setSelected] = useState<string | null>(null);
  const refresh = () => { state.refresh(); policies.refresh(); };
  if (selected) return <MilestoneDetail key={selected} path={base + '/milestones/' + selected} canManage={project.can_manage} onBack={() => { setSelected(null); refresh(); }} />;
  if (state.loading || state.error || !state.data || policies.loading || policies.error || !policies.data) return <Loading error={state.error || policies.error} refresh={refresh} />;
  const available = policies.data.items.filter(p => p.usable_for_new_milestones);
  return <><div className="section-heading"><div><h2>Milestone budgets</h2><p>Budget outcomes before work is accepted. No earned shares exist yet.</p></div><button className="button" onClick={refresh}>Refresh milestones</button></div>
    <div className="project-grid">{state.data.items.length ? state.data.items.map(item => <button className="project-card" key={item.id} onClick={() => setSelected(item.id)}><strong>{item.name}</strong><p>Approved total: {formatUnits(item.total_atoms)} units<br />Planned: {formatUnits(item.allocated_atoms)} · Available: {formatUnits(item.available_atoms)}</p><Badge>{item.status === 'draft' ? 'Awaiting initial approval' : 'Approved budget'}</Badge></button>) : <section className="panel empty"><h3>No milestones yet</h3><p>First approve and acknowledge a policy, then propose a milestone budget.</p></section>}</div>
    {project.can_manage && (available.length ? <CreateMilestone key={available[0].id} root={base + '/milestones'} policies={available} onCreated={item => { setSelected(item.id); refresh(); }} /> : <section className="panel"><h3>A ready policy is required</h3><p>Open Policies, approve the reviewed document, and obtain its required participant acknowledgements. Only the current effective version can start new milestones.</p></section>)}
  </>;
}
