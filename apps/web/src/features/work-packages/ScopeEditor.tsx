import { useState } from 'react';
import type { HistoricalCreateHandler } from '../../lib/reconstruction.js';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatUnits, humanLabel } from '../../lib/planning.js';
import { boundedWorkBody, buildScope, newScope, newDeliverable, scopeDraft, workRoles,
  type ScopeDraft, type DeliverableDraft, type WorkOptions, type WorkPackageDetail, type WorkRole } from '../../lib/workPackages.js';

export function ScopeEditor({ root, options, item, onSaved, onCancel, submitCreate, initialOutcome, initialTitle, initialDraft }: {
  submitCreate?: HistoricalCreateHandler; initialOutcome?: string; initialTitle?: string; initialDraft?:ScopeDraft; root: string; options: WorkOptions; item?: WorkPackageDetail; onSaved: (value: WorkPackageDetail) => void; onCancel: () => void;
}) {
  const [allocationId, setAllocationId] = useState(options.allocations[0]?.id ?? '');
  const [draft, setDraft] = useState<ScopeDraft>(() => item ? scopeDraft(item.revision.document) : initialDraft ?? ({ ...newScope(options.my_user_id, initialTitle ?? options.allocations[0]?.title), outcome: initialOutcome ?? '' }));
  const [reason, setReason] = useState(''); const [confirmed, setConfirmed] = useState(false); const action = useAction();
  const allocation = options.allocations.find(a => a.id === allocationId);
  const budget = item ? item.budget_atoms : allocation?.atoms ?? 0;
  const update = <K extends keyof ScopeDraft>(key: K, value: ScopeDraft[K]) => setDraft(old => ({ ...old, [key]: value }));
  const changeDeliverable = (id: string, value: Partial<DeliverableDraft>) => setDraft(old => ({ ...old, deliverables: old.deliverables.map(d => d.id === id ? { ...d, ...value } : d) }));
  const activeIds = new Set(options.participants.map(p => p.user_id));
  const missing = [...new Set([draft.coordinator, ...draft.intended])].filter(id => id && !activeIds.has(id));
  const label = (id: string) => options.participants.find(p => p.user_id === id)?.display_name || item?.revision.document.participant_labels[id] || id;
  return <section className="panel scope-editor"><div className="section-heading"><h2>{item ? 'Create a scope amendment' : 'Create a work package'}</h2><button className="button" disabled={action.pending} onClick={onCancel}>Close editor</button></div>
    <p>Budget outcomes rather than activity counts. Saving a draft issues no credit. Every later scope change preserves the previous revision and requires fresh planning approval.</p>
    <Feedback error={action.error} /><form onSubmit={event => { event.preventDefault(); void action.run(async () => {
      const scope = buildScope(draft, budget);
      if (item) return api<WorkPackageDetail>(`${root}/${item.id}/revisions`, 'POST', boundedWorkBody({ expected_version: item.version, reviewed_hash: item.review_hash, scope, reason }));
      if (!allocation) throw new Error('Select an approved, unlinked work allocation first.');
      if (submitCreate) return submitCreate(scope, allocation, reason);
      return api<WorkPackageDetail>(root, 'POST', boundedWorkBody({ milestone_id: allocation.milestone_id, allocation_id: allocation.id, expected_allocation_version: allocation.version, scope, reason }));
    }, onSaved); }}><fieldset disabled={action.pending} className="scope-fields">
    {!item && <SelectField label="Approved work allocation" required value={allocationId} onChange={e => setAllocationId(e.target.value)}>
      {!options.allocations.length && <option value="">No approved unlinked allocations</option>}{options.allocations.map(a => <option key={a.id} value={a.id}>{a.milestone_name} · {a.title} · {formatUnits(a.atoms)} units</option>)}</SelectField>}
    <p className="planning-warning">Parent budget: <strong>{formatUnits(budget)} units</strong>. {item ? item.category : allocation?.category} · {item ? item.pool_key : allocation?.pool_key} pool. Parent and policy links cannot be moved to another project or allocation.</p>
    <TextField label="Work-package title" required minLength={2} maxLength={120} value={draft.title} onChange={e => update('title', e.target.value)} />
    <TextArea label="Useful outcome" required minLength={8} maxLength={2000} rows={3} value={draft.outcome} onChange={e => update('outcome', e.target.value)} />
    <TextArea label="Package acceptance criteria — one per line" required minLength={8} rows={3} value={draft.criteria} onChange={e => update('criteria', e.target.value)} />
    <TextArea label="Required evidence" required minLength={8} maxLength={2000} rows={3} value={draft.evidence} onChange={e => update('evidence', e.target.value)} />
    <SelectField label="Coordinator" required value={draft.coordinator} onChange={e => update('coordinator', e.target.value)}>
      <option value="">Choose a coordinator</option>{options.participants.map(p => <option key={p.user_id} value={p.user_id}>{p.display_name} · {p.role}</option>)}
      {missing.includes(draft.coordinator) && <option value={draft.coordinator}>{label(draft.coordinator)} — inactive; replace</option>}
    </SelectField>
    <fieldset className="choice-group"><legend>Intended contributors</legend><div className="checkbox-grid">{options.participants.map(p => <label key={p.user_id}><input type="checkbox" checked={draft.intended.includes(p.user_id)} onChange={e => update('intended', e.target.checked ? [...draft.intended, p.user_id] : draft.intended.filter(id => id !== p.user_id))} />{p.display_name}</label>)}</div>
      {missing.filter(id => draft.intended.includes(id)).map(id => <p key={id}>{label(id)} no longer has eligible access. <button type="button" className="button" onClick={() => update('intended', draft.intended.filter(value => value !== id))}>Remove from this new revision</button></p>)}
      <p className="small muted">An intended contributor is not automatically awarded units. Assign specific roles and proposed amounts below.</p></fieldset>
    <h3>Independently acceptable deliverables</h3><p>Each deliverable has its own outcome, evidence requirements and budget. Drafts may be incomplete; approval and submission require fully planned budgets and attribution.</p>
    {draft.deliverables.map((d, index) => <fieldset className="work-deliverable" key={d.id}><legend>Deliverable {index + 1}</legend>
      <TextField label={`Deliverable ${index + 1} title`} required minLength={2} maxLength={120} value={d.title} onChange={e => changeDeliverable(d.id, { title: e.target.value })} />
      <TextArea label={`Deliverable ${index + 1} outcome`} required minLength={8} maxLength={2000} value={d.outcome} onChange={e => changeDeliverable(d.id, { outcome: e.target.value })} />
      <TextArea label={`Deliverable ${index + 1} criteria — one per line`} required minLength={8} value={d.criteria} onChange={e => changeDeliverable(d.id, { criteria: e.target.value })} />
      <TextArea label={`Deliverable ${index + 1} evidence requirements`} required minLength={8} maxLength={2000} value={d.evidence} onChange={e => changeDeliverable(d.id, { evidence: e.target.value })} />
      <div className="form-grid"><TextField label={`Deliverable ${index + 1} budget in units`} required inputMode="decimal" value={d.units} onChange={e => changeDeliverable(d.id, { units: e.target.value })} hint="Up to three decimal places; these are not dollars." />
        <SelectField label={`Deliverable ${index + 1} attribution method`} value={d.mode} onChange={e => changeDeliverable(d.id, { mode: e.target.value as 'units' | 'percent', entries: d.entries.map(row => ({ ...row, amount: '' })) })}>
          <option value="units">Direct proposed units</option><option value="percent">Percentage of this deliverable</option></SelectField></div>
      <p className="small muted">Changing attribution method clears entered amounts. Percentages use up to two decimal places and are converted to exact unit atoms on the server.</p>
      {d.entries.map((entry, rowIndex) => <div className="attribution-row" key={entry.key}>
        <SelectField label={`Deliverable ${index + 1}, attribution ${rowIndex + 1} contributor`} required value={entry.user_id} onChange={e => changeDeliverable(d.id, { entries: d.entries.map(row => row.key === entry.key ? { ...row, user_id: e.target.value } : row) })}>
          <option value="">Choose a contributor</option>{draft.intended.map(id => <option key={id} value={id}>{label(id)}{!activeIds.has(id) ? ' — inactive' : ''}</option>)}
          {entry.user_id && !draft.intended.includes(entry.user_id) && <option value={entry.user_id}>{label(entry.user_id)} — not selected; replace</option>}
        </SelectField>
        <SelectField label={`Deliverable ${index + 1}, attribution ${rowIndex + 1} role`} value={entry.role} onChange={e => changeDeliverable(d.id, { entries: d.entries.map(row => row.key === entry.key ? { ...row, role: e.target.value as WorkRole } : row) })}>
          {workRoles.map(role => <option key={role} value={role}>{humanLabel(role)}</option>)}</SelectField>
        <TextField label={`Deliverable ${index + 1}, attribution ${rowIndex + 1} ${d.mode === 'units' ? 'units' : 'percent'}`} required inputMode="decimal" value={entry.amount} onChange={e => changeDeliverable(d.id, { entries: d.entries.map(row => row.key === entry.key ? { ...row, amount: e.target.value } : row) })} />
        <button type="button" className="button" aria-label={`Remove attribution ${rowIndex + 1} from deliverable ${index + 1}`} onClick={() => changeDeliverable(d.id, { entries: d.entries.filter(row => row.key !== entry.key) })}>Remove</button>
      </div>)}
      <div className="button-row"><button type="button" className="button" disabled={d.entries.length >= 30} onClick={() => changeDeliverable(d.id, { entries: [...d.entries, { key: crypto.randomUUID(), user_id: draft.intended[0] || '', role: 'implementation', amount: '' }] })}>Add proposed attribution</button>
      <button type="button" className="button danger" onClick={() => update('deliverables', draft.deliverables.filter(value => value.id !== d.id))}>Remove this deliverable from draft</button></div>
    </fieldset>)}
    <button type="button" className="button" disabled={draft.deliverables.length >= 30} onClick={() => update('deliverables', [...draft.deliverables, newDeliverable(crypto.randomUUID())])}>Add deliverable</button>
    <div className="form-details"><TextArea label="Reason for this scope revision" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      {item && <ConfirmCheck checked={confirmed} onChange={setConfirmed}>I reviewed this amendment. It returns the package to draft, preserves previous submissions, and requires fresh planning approval.</ConfirmCheck>}
      <Submit pending={action.pending}>{item ? 'Save scope amendment' : 'Save work-package draft'}</Submit></div>
    </fieldset></form></section>;
}
