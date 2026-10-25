import { AssessmentPanel } from '../assessments/AssessmentPanel.js';
import { ReviewAssignments } from '../reviews/Reviews.js';
import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatUnits, humanLabel } from '../../lib/planning.js';
import { actionLabels, type WorkAction, type WorkOptions, type WorkPackageDetail as PackageRecord,
  type ScopeRevision, type SubmissionRecord } from '../../lib/workPackages.js';
import { ScopeEditor } from './ScopeEditor.js';
import { ScopeView } from './ScopeView.js';
import { EvidencePanel } from '../evidence/EvidencePanel.js';
import { SnapshotView } from '../evidence/Snapshots.js';
import { ArchivedEvidence } from '../evidence/EvidenceView.js';

function ActionPanel({ root, item, refresh }: { root: string; item: PackageRecord; refresh: () => void }) {
  const [selected, setSelected] = useState<WorkAction>(item.allowed_actions[0]);
  const [reason, setReason] = useState(''); const [reviewed, setReviewed] = useState(false); const action = useAction();
  if (!item.allowed_actions.length) return <section className="panel"><h3>No state change available</h3><p>Check the scope blockers and your current role. Use Human reviews for independent acceptance and separate credit finalization; package completion follows accepted deliverables.</p></section>;
  return <section className="panel"><h3>Review the scope before changing its state</h3><Feedback error={action.error} />
    <form onSubmit={event => { event.preventDefault(); void action.run(() => api(`${root}/${item.id}/actions`, 'POST', {
      action: selected, expected_version: item.version, reviewed_hash: item.review_hash, reviewed: true, reason,
    }), refresh); }}>
      <SelectField label="Work-package action" value={selected} onChange={e => { setSelected(e.target.value as WorkAction); setReviewed(false); }} disabled={action.pending}>
        {item.allowed_actions.map(value => <option key={value} value={value}>{actionLabels[value]}</option>)}</SelectField>
      {selected === 'approve_scope' && <p className="planning-warning">This approves the budgeted scope for work. It does not accept a deliverable or grant any person credit.</p>}
      {(selected === 'submit' || selected === 'refresh_submission') && <p className="planning-warning">This archives the exact scope, attribution, policy references and current evidence packet, including omissions. It is a readiness declaration, not independent acceptance. A resubmission never overwrites the earlier packet.</p>}
      {(selected === 'request_changes' || selected === 'withdraw') && <p>The current submission remains archived. A new scope revision and fresh planning approval will be required before resubmitting.</p>}
      {selected === 'cancel' && <p className="planning-warning">This permanently cancels the package and releases {formatUnits(item.budget_atoms)} unissued units to the milestone’s available planning capacity. Protected reserve is unchanged. Scope and submission history remain. A cancelled package cannot be reopened; new work needs a new approved allocation.</p>}
      <TextArea label={selected === 'submit' ? 'Submission note' : 'Reason for this action'} required minLength={8} maxLength={500} rows={3} value={reason} onChange={e => setReason(e.target.value)} disabled={action.pending} />
      <ConfirmCheck checked={reviewed} onChange={setReviewed} disabled={action.pending}>I reviewed scope revision {item.scope_revision}, its proposed attribution and this action. I understand that this does not award contribution units or create earnings.</ConfirmCheck>
      <Submit pending={action.pending}>{actionLabels[selected]}</Submit>
    </form></section>;
}
function Archive({ path, kind, close }: { path: string; kind: 'revision' | 'submission'; close: () => void }) {
  const state = useResource<ScopeRevision | SubmissionRecord>(path);
  const [showEvidence,setShowEvidence]=useState(false);
  const [evidenceArchive,setEvidenceArchive]=useState<{id:string;revision:number}|null>(null);
  if (state.loading || state.error || !state.data) return <section className="panel"><button className="button" onClick={close}>Close archive</button><Loading error={state.error} refresh={state.refresh} /></section>;
  const revision = kind === 'revision' ? state.data as ScopeRevision : null;
  const submission = kind === 'submission' ? state.data as SubmissionRecord : null;
  const doc = revision ? revision.document : submission!.snapshot.scope;
  return <section className="panel archive-panel"><div className="section-heading"><h3>{revision ? `Archived scope revision ${revision.number}` : `Archived submission of scope ${submission!.scope_revision}`}</h3><button className="button" onClick={close}>Close archive</button></div>
    <p className="planning-warning">Historical snapshot, not the current editable scope.</p><p className="preserve-text">{revision ? revision.reason : submission!.snapshot.submission_note}</p>
    <p className="small wrap">Fingerprint: <code>{revision ? revision.content_hash : submission!.snapshot_hash}</code></p>
    {submission && <p>{submission.snapshot.notice}</p>}<ScopeView doc={doc} />
    {submission && typeof submission.snapshot.evidence_snapshot_id === 'string' && <>
      <button className="button" onClick={()=>setShowEvidence(!showEvidence)}>Inspect this submission’s evidence packet</button>
      {showEvidence && <SnapshotView root={`${path.split('/submissions/')[0]}/evidence`} id={submission.snapshot.evidence_snapshot_id} close={()=>setShowEvidence(false)} inspect={(id,revision)=>setEvidenceArchive({id,revision})}/>}
      {evidenceArchive && <ArchivedEvidence root={`${path.split('/submissions/')[0]}/evidence`} evidenceId={evidenceArchive.id} revision={evidenceArchive.revision} close={()=>setEvidenceArchive(null)}/>}
    </>}</section>;
}
export function WorkPackageDetail({ root, packageId, options, onBack }: {
  root: string; packageId: string; options: WorkOptions; onBack: () => void;
}) {
  const [offset, setOffset] = useState(0); const path = `${root}/${packageId}`;
  const state = useResource<PackageRecord>(`${path}?history_offset=${offset}`);
  const [editing, setEditing] = useState(false);
  const [archive, setArchive] = useState<{ path: string; kind: 'revision' | 'submission' } | null>(null);
  const refresh = () => { setEditing(false); setArchive(null); setOffset(0); state.refresh(); };
  if (state.loading || state.error || !state.data) return <><button className="button back-button" onClick={onBack}>Back to work packages</button><Loading error={state.error} refresh={state.refresh} /></>;
  const item = state.data;
  if (editing && item.can_edit) return <ScopeEditor key={item.version} root={root} options={options} item={item} onSaved={refresh} onCancel={() => setEditing(false)} />;
  const metrics: [string, number][] = [[item.state === 'cancelled' ? 'Archived scope budget' : 'Package budget', item.scope_budget_atoms],
    ['Budgeted deliverables', item.deliverable_atoms], ['Not yet planned in scope', item.unplanned_atoms], ['Issued credit', item.issued_atoms]];
  return <div className="planning-stack"><div><button className="button back-button" onClick={onBack}>Back to work packages</button>
    <div className="section-heading"><div><h2>{item.title}</h2><p>{item.milestone_name} · {humanLabel(item.origin)} · Scope revision {item.scope_revision} · Package version {item.version}</p></div><button className="button" onClick={refresh}>Refresh package</button></div>
    <Badge>{humanLabel(item.state)}</Badge><p className="planning-warning">{item.notice}</p>
    <div className="budget-metrics">{metrics.map(([label, amount]) => <div className="budget-metric" key={label}><span>{label}</span><strong>{formatUnits(amount)}</strong><small>contribution units</small></div>)}</div>
    {item.state === 'cancelled' && <p>Current parent allocation: {formatUnits(item.budget_atoms)} units. The historical scope above remains unchanged after cancellation.</p>}
    <p>Pinned policy: version {item.policy.version} · {item.policy.title} · {humanLabel(item.policy.state)}</p>
    {item.blockers.length > 0 && item.state !== 'cancelled' && <section className="error-panel"><h3>Resolve before scope approval or submission</h3><ul>{item.blockers.map(value => <li key={value}>{value}</li>)}</ul></section>}
  </div>
  <section className="panel"><div className="section-heading"><h3>Current scope</h3>{item.can_edit && <button className="button" onClick={() => setEditing(true)}>Amend scope</button>}</div><ScopeView doc={item.revision.document} />
    <details className="form-details"><summary>Scope and review fingerprints</summary><p className="wrap small">Scope: <code>{item.revision.content_hash}</code></p><p className="wrap small">Current review: <code>{item.review_hash}</code></p><p>A newer scope or parent-budget revision invalidates a stale command.</p></details></section>
  <EvidencePanel key={item.id+":"+item.version} packagePath={path} packageRecord={item} refreshPackage={refresh} />
  <ReviewAssignments key={item.id+":review:"+item.version} root={root.replace(/\/work-packages$/,'')} packageId={item.id} onChanged={refresh} />
  {options.can_assess&&<AssessmentPanel key={item.id+':ai:'+item.version} projectRoot={root.replace(/\/work-packages$/,'')} packageId={item.id}/>}
  <ActionPanel key={item.review_hash} root={root} item={item} refresh={refresh} />
  <section className="panel"><h3>Recent submissions</h3>{!item.recent_submissions.length && <p>No readiness declaration has been submitted.</p>}
    {item.recent_submissions.map(s => <div className="work-history" key={s.id}><div><strong>Scope {s.scope_revision} · package version {s.package_version}</strong><small>{new Date(s.created_at).toLocaleString()} · browser local time</small></div>
      <button className="button" onClick={() => setArchive({ path: `${path}/submissions/${s.id}`, kind: 'submission' })}>Inspect submission</button></div>)}
    <p className="small muted">The latest 10 submissions are shown here. Earlier submissions remain accessible through their timeline events.</p></section>
  <section className="panel"><h3>Recorded changes</h3>{item.history.map(event => <div className="work-history" key={event.id}><div><strong>Version {event.version}: {humanLabel(event.action)}</strong><small>Scope {event.scope_revision} · {new Date(event.created_at).toLocaleString()}</small>
      <p className="preserve-text">{event.reason}</p><small className="wrap">Actor: {event.actor_id}</small></div><div className="work-history-buttons">
      <button className="button" onClick={() => setArchive({ path: `${path}/revisions/${event.scope_revision}`, kind: 'revision' })}>Inspect scope {event.scope_revision}</button>
      {typeof event.details.submission_id === 'string' && <button className="button" onClick={() => setArchive({ path: `${path}/submissions/${event.details.submission_id}`, kind: 'submission' })}>Inspect submitted snapshot</button>}</div></div>)}
    <div className="button-row"><button className="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Newer events</button><button className="button" disabled={item.next_history_offset === null} onClick={() => item.next_history_offset !== null && setOffset(item.next_history_offset)}>Older events</button></div></section>
  {archive && <Archive key={archive.path} {...archive} close={() => setArchive(null)} />}</div>;
}
