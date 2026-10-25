import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Submit } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { explicitInstant, formatBps, humanLabel, type Policy } from '../../lib/planning.js';

function Approval({ policy, path, refresh }: { policy: Policy; path: string; refresh: () => void }) {
  const [reviewed, setReviewed] = useState(false); const [reason, setReason] = useState(''); const [effective, setEffective] = useState(''); const action = useAction();
  return <section className="panel"><h3>Approve this policy version</h3><p>Approval preserves this exact document. It becomes usable only after its effective time and every required acknowledgement. No automatic fallback to older rules occurs when a new effective version is missing acknowledgements.</p>
    <Feedback error={action.error} /><form onSubmit={e => { e.preventDefault(); if (!reviewed) return; void action.run(() => api(path + '/approve', 'POST', {
      expected_latest_version: policy.version, reviewed_content_hash: policy.content_hash, examples_reviewed: true,
      effective_at: explicitInstant(effective), reason }), refresh); }}>
      <TextField label="Effective time (optional)" value={effective} maxLength={40} onChange={e => setEffective(e.target.value)} placeholder="Leave blank for immediate approval" hint="For a future time, include seconds and a UTC offset, for example 2030-01-01T12:00:00-04:00. No backdating." />
      <TextField label="Reason for policy approval" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      <ConfirmCheck checked={reviewed} onChange={setReviewed}>I reviewed this full policy, its participant list, and all example values. Approval does not replace an external agreement.</ConfirmCheck>
      <Submit pending={action.pending}>Approve policy version {policy.version}</Submit>
    </form>
  </section>;
}
function Acknowledge({ policy, path, refresh }: { policy: Policy; path: string; refresh: () => void }) {
  const [reviewed, setReviewed] = useState(false); const action = useAction();
  return <section className="panel"><h3>Your acknowledgement</h3><p>This records only your review of version {policy.version}, not consent on behalf of another contributor.</p><Feedback error={action.error} /><form onSubmit={e => { e.preventDefault(); if (!reviewed) return; void action.run(() => api(path + '/acknowledge', 'POST', { reviewed_content_hash: policy.content_hash, reviewed: true }), refresh); }}>
    <ConfirmCheck checked={reviewed} onChange={setReviewed}>I reviewed this exact policy version and its agreement reference. This acknowledgement does not issue credit or legally certify the agreement.</ConfirmCheck>
    <Submit pending={action.pending}>Acknowledge version {policy.version}</Submit>
  </form></section>;
}
export function PolicyDetail({ policy, path, canManage, refresh }: { policy: Policy; path: string; canManage: boolean; refresh: () => void }) {
  const rules = policy.rules;
  return <div className="planning-stack"><section className="panel"><div className="section-heading"><h2>Version {policy.version}: {policy.title}</h2><Badge>{humanLabel(policy.state)}</Badge></div>
    <p className="planning-warning">{policy.notice}</p>
    <dl className="policy-facts"><div><dt>Agreement reference</dt><dd>{policy.agreement_reference}</dd></div><div><dt>Revision reason</dt><dd>{policy.reason}</dd></div><div><dt>Accounting scope</dt><dd>{rules.currency} · {rules.timezone} · calendar months</dd></div><div><dt>Review threshold for future awards</dt><dd>{rules.review.minimum_independent_reviewers} independent reviewer(s); beneficiary cannot approve alone</dd></div>
      <div><dt>Categories</dt><dd>{rules.eligible_categories.join(', ')}</dd></div><div><dt>Unissued units</dt><dd>Remain unowned until accepted; not assigned to an owner</dd></div></dl>
    <h3>Pool weights</h3><div className="pool-list">{rules.pools.map(pool => <div key={pool.key}><strong>{formatBps(pool.weight_bps)}</strong><span>{pool.key} pool</span><small>{humanLabel(pool.eligibility)}</small></div>)}</div>
    <h3>Attribution</h3><p className="preserve-text">{rules.attribution_rule}</p><h3>Departure and historical credit</h3><p className="preserve-text">{rules.departure_rule}</p>
    <h3>Distributable earnings</h3><p>{humanLabel(rules.accounting.revenue_basis)}</p><p className="preserve-text">{rules.accounting.distributable_definition}</p><p>Permitted deduction categories: {rules.accounting.allowed_deductions.map(humanLabel).join(', ') || 'None'}. Each expense requires documented administrative approval.</p>
    <h3>Cash reserve</h3><p className="preserve-text">{rules.accounting.reserve_rule}</p><h3>Capital repayment</h3><p className="preserve-text">{rules.accounting.capital_repayment_rule}</p>
    <p>Unresolved disputes block affected closes. Empty pools block closing. Time boundaries that are ambiguous or nonexistent are rejected. These accounting rules are configured here; the financial workflow is not implemented yet.</p>
    <p>Policy and budget governance: one project administrator. Required policy acknowledgements: original participant snapshot plus current active non-viewer project participants. Workspace administrators inherit project access and are included.</p>
    {policy.approval && <div className="policy-approved"><h3>Administrative approval</h3><p>{policy.approval.reason}</p><p>Effective instant: <time dateTime={policy.approval.effective_at}>{policy.approval.effective_at}</time></p><p>Approved by account <code className="wrap">{policy.approval.approved_by}</code>.</p></div>}
    <details className="form-details"><summary>Full versioned document and content fingerprint</summary><p className="wrap"><code>{policy.content_hash}</code></p><pre>{JSON.stringify(rules, null, 2)}</pre><p>Version IDs and fingerprints preserve which document was reviewed; they do not certify the truth of its terms.</p></details>
  </section>
  <section className="panel"><h3>Required participant acknowledgements</h3><p>{policy.acknowledgements.complete ? 'Every currently required acknowledgement is recorded.' : `${policy.acknowledgements.missing_user_ids.length} acknowledgement(s) are still required.`}</p>
    <div className="table-scroll"><table><caption>Review status for this exact version</caption><thead><tr><th scope="col">Participant</th><th scope="col">Requirement</th><th scope="col">Status</th></tr></thead><tbody>{policy.acknowledgements.participants.map(member => <tr key={member.user_id}><th scope="row">{member.display_name}<small>{member.role}</small></th><td>{member.required_at_creation ? 'Original snapshot' : 'New participant'}{!member.currently_required && ' · no longer active'}</td><td>{member.acknowledged_at ? 'Acknowledged' : 'Pending'}</td></tr>)}</tbody></table></div>
    <p>{policy.acknowledgements.note}</p>
  </section>
  {canManage && !policy.approval && policy.is_latest_revision && <Approval policy={policy} path={path} refresh={refresh} />}
  {!!policy.approval && !policy.my_acknowledgement && <Acknowledge policy={policy} path={path} refresh={refresh} />}
  {policy.my_acknowledgement && <p className="success-note">Your acknowledgement of version {policy.version} is recorded.</p>}
  {!policy.is_latest_revision && !policy.approval && <p className="planning-warning">A newer draft exists. This historical draft can no longer be approved.</p>}
  </div>;
}
