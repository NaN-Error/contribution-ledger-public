import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { BudgetComparison, BudgetMetrics, ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatUnits, humanLabel, type Amendment, type MilestoneDetail as MilestoneRecord } from '../../lib/planning.js';
import { ProposalEditor } from './ProposalEditor.js';

function ProposalReview({ proposal, milestone, path, canManage, refresh }: { proposal: Amendment; milestone: MilestoneRecord; path: string; canManage: boolean; refresh: () => void }) {
  const policyReady = milestone.status === 'draft' ? milestone.policy.usable_for_new_milestones : milestone.policy.ready_for_pinned_work;
  const canApprove = proposal.state === 'pending' && policyReady;
  const [choice, setChoice] = useState<'approve' | 'reject'>(canApprove ? 'approve' : 'reject');
  const [reason, setReason] = useState(''); const [reviewed, setReviewed] = useState(false); const action = useAction();
  return <details className="proposal-record" open={proposal.state === 'pending'}><summary><span><strong>{humanLabel(proposal.change.kind)}</strong><small>Based on milestone revision {proposal.expected_version} · {new Date(proposal.created_at).toLocaleString()}</small></span><Badge>{proposal.state}</Badge></summary>
    <p className="preserve-text">Proposal reason: {proposal.reason}</p><BudgetComparison value={proposal.preview} />
    <p className="small wrap">Preview fingerprint: <code>{proposal.preview_hash}</code></p>
    {proposal.decision && <div className="decision-note"><strong>{humanLabel(proposal.state)}</strong><p>{proposal.decision.reason}</p><p>Milestone revision after decision: {proposal.decision.resulting_version}. Actor: <code className="wrap">{proposal.decision.decided_by}</code>.</p></div>}
    {proposal.state === 'stale' && <p className="planning-warning">Another decision changed the milestone. This proposal cannot be approved. Submit a new proposal against the latest revision, or reject this obsolete one.</p>}
    {!proposal.decision && canManage && <form onSubmit={e => { e.preventDefault(); if (!reviewed) return; void action.run(() => api<MilestoneRecord>(path + `/amendments/${proposal.id}/decision`, 'POST', {
      decision: choice, expected_version: milestone.version, reviewed_preview_hash: proposal.preview_hash, reason }), refresh); }}>
      <Feedback error={action.error} />
      <SelectField label="Decision" value={choice} onChange={e => setChoice(e.target.value as 'approve' | 'reject')}>{canApprove && <option value="approve">Approve budget change</option>}<option value="reject">Reject proposal</option></SelectField>
      {!policyReady && <p className="planning-warning">Policy readiness blocks approval. Review the policy acknowledgements and effective time; rejection is still available.</p>}
      <TextField label="Reason for budget decision" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      <ConfirmCheck checked={reviewed} onChange={setReviewed}>I reviewed this exact before-and-after preview and its impact on the available budget. This does not award contribution credit.</ConfirmCheck>
      <Submit pending={action.pending}>{choice === 'approve' ? 'Approve budget change' : 'Reject proposal'}</Submit>
    </form>}
  </details>;
}

export function MilestoneDetail({ path, canManage, onBack }: { path: string; canManage: boolean; onBack: () => void }) {
  const [historyOffset, setHistoryOffset] = useState(0);
  const state = useResource<MilestoneRecord>(path + `?history_offset=${historyOffset}`);
  const refresh = () => { setHistoryOffset(0); state.refresh(); };
  if (state.loading || state.error || !state.data) return <><button className="button back-button" onClick={onBack}>← Back to milestones</button><Loading error={state.error} refresh={state.refresh} /></>;
  const item = state.data;
  const ready = item.status === 'draft' ? item.policy.usable_for_new_milestones : item.policy.ready_for_pinned_work;
  return <><button className="button back-button" onClick={onBack}>← Back to milestones</button><div className="section-heading"><div><h2>{item.name}</h2><p>{item.description || 'Milestone planning budget'} · revision {item.version}</p></div><button className="button" onClick={refresh}>Refresh budget</button></div>
    <div className="planning-stack"><section className="panel"><div className="section-heading"><h3>Budget status</h3><Badge>{item.status === 'draft' ? 'Awaiting initial approval' : 'Approved planning budget'}</Badge></div><BudgetMetrics value={item} />
      <p>{formatUnits(item.unassigned_atoms)} units remain unassigned, including the protected reserve. Issued units: {formatUnits(item.issued_atoms)}. Only independent human review and separate finalization issue contribution credit; planning a budget does not.</p>
      <p className="planning-warning">{item.notice}</p><p>Pinned policy: version {item.policy.version}, {item.policy.title} · {item.policy.rules.timezone}. A successor policy does not automatically replace this reference.</p>
      {!ready && <p className="planning-warning">Budget approval is blocked by the pinned policy's readiness. Open Policies to inspect effective dates, supersession, and participant acknowledgements.</p>}
    </section>
    <section className="panel"><h3>Planned allocations</h3>{item.allocations.length ? <div className="table-scroll"><table><caption>Work budgets, not contributor awards</caption><thead><tr><th scope="col">Outcome</th><th scope="col">Pool</th><th scope="col">Units</th><th scope="col">Status</th></tr></thead><tbody>{item.allocations.map(row => <tr key={row.id}><th scope="row">{row.title}<small>{humanLabel(row.category)}</small></th><td>{row.pool_key}</td><td>{formatUnits(row.atoms)}</td><td>{row.status}</td></tr>)}</tbody></table></div> : <p>No approved allocations. Work packages and acceptance criteria will build on these budgets in phase 4.</p>}</section>
    {canManage && ready && <ProposalEditor key={item.version} milestone={item} path={path} refresh={refresh} />}
    <section className="panel"><h3>Proposal and decision history</h3><p>Every approved change keeps its reviewed snapshot and reason. Pending proposals are excluded from approved totals.</p>
      {!item.amendments.length && <p>No proposals on this history page.</p>}
      {item.amendments.map(proposal => <ProposalReview key={`${proposal.id}-${item.version}`} proposal={proposal} milestone={item} path={path} canManage={canManage} refresh={refresh} />)}
      <div className="button-row"><button className="button" disabled={historyOffset === 0} onClick={() => setHistoryOffset(Math.max(0, historyOffset - 20))}>Newer proposals</button><button className="button" disabled={item.next_history_offset === null} onClick={() => { if (item.next_history_offset !== null) setHistoryOffset(item.next_history_offset); }}>Older proposals</button></div>
    </section></div>
  </>;
}
