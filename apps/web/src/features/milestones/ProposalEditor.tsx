import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit } from '../../components/forms.js';
import { BudgetComparison } from '../../components/planning.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatUnits, humanLabel, parseUnits, unitInput, type Amendment, type AmendmentInput,
  type BudgetChange, type Category, type MilestoneDetail, type PoolKey, type PreviewResult } from '../../lib/planning.js';

export function ProposalEditor({ milestone, path, refresh }: { milestone: MilestoneDetail; path: string; refresh: () => void }) {
  const [kind, setKind] = useState<BudgetChange['kind']>(milestone.status === 'draft' ? 'initial_budget' : 'allocate');
  const [title, setTitle] = useState(''); const [category, setCategory] = useState<Category>(milestone.policy.rules.eligible_categories[0]);
  const [pool, setPool] = useState<PoolKey>(milestone.policy.rules.pools[0].key);
  const [amount, setAmount] = useState(''); const [total, setTotal] = useState(unitInput(milestone.total_atoms));
  const [reserve, setReserve] = useState(unitInput(milestone.reserve_floor_atoms)); const [reason, setReason] = useState('');
  const active = milestone.allocations.filter(x => x.status === 'active');
  const [allocationId, setAllocationId] = useState(active[0]?.id || '');
  const [prepared, setPrepared] = useState<{ body: AmendmentInput; result: PreviewResult } | null>(null); const action = useAction();
  const choices: BudgetChange['kind'][] = milestone.status === 'draft' ? ['initial_budget'] : ['allocate', 'set_budget', 'resize_allocation', 'cancel_allocation'];
  const needsAllocation = kind === 'resize_allocation' || kind === 'cancel_allocation';
  return <section className="panel proposal-editor"><h3>Propose a budget change</h3><p>Preview first, save the proposal, then explicitly approve or reject it. Saving a proposal does not change the approved totals.</p>
    <Feedback error={action.error} /><form onChange={() => setPrepared(null)} onSubmit={e => { e.preventDefault(); void action.run(async () => {
      let change: BudgetChange;
      if (kind === 'initial_budget' || kind === 'set_budget') change = { kind, total_atoms: parseUnits(total), reserve_floor_atoms: parseUnits(reserve) };
      else if (kind === 'allocate') change = { kind, title, category, pool_key: pool, atoms: parseUnits(amount) };
      else if (kind === 'resize_allocation') change = { kind, allocation_id: allocationId, atoms: parseUnits(amount) };
      else change = { kind: 'cancel_allocation', allocation_id: allocationId };
      const body: AmendmentInput = { expected_version: milestone.version, change, reason };
      const result = await api<PreviewResult>(path + '/preview', 'POST', body);
      return { body, result };
    }, setPrepared); }}>
      <SelectField label="Budget change type" value={kind} onChange={e => setKind(e.target.value as BudgetChange['kind'])}>{choices.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</SelectField>
      {(kind === 'initial_budget' || kind === 'set_budget') && <div className="form-grid"><TextField label="Proposed total units" required inputMode="decimal" value={total} onChange={e => setTotal(e.target.value)} hint="Use up to three decimal places. This is a planning budget, not cash." /><TextField label="Protected reserve units" required inputMode="decimal" value={reserve} onChange={e => setReserve(e.target.value)} hint="Unassigned units that cannot be allocated until a reserve amendment is approved." /></div>}
      {kind === 'allocate' && <><TextField label="Planned outcome" required minLength={2} maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder="For example, implement reconnection" /><div className="form-grid"><SelectField label="Contribution category" value={category} onChange={e => setCategory(e.target.value as Category)}>{milestone.policy.rules.eligible_categories.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</SelectField><SelectField label="Contribution pool" value={pool} onChange={e => setPool(e.target.value as PoolKey)}>{milestone.policy.rules.pools.map(value => <option key={value.key} value={value.key}>{value.key}</option>)}</SelectField></div></>}
      {needsAllocation && <SelectField label="Existing allocation" required value={allocationId} onChange={e => setAllocationId(e.target.value)}><option value="">Select an active allocation</option>{active.map(row => <option key={row.id} value={row.id}>{row.title} · {formatUnits(row.atoms)} units</option>)}</SelectField>}
      {(kind === 'allocate' || kind === 'resize_allocation') && <TextField label="Planned allocation units" required inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} hint="Up to three decimal places; no commas. No contributor receives earned credit from this action." />}
      {kind === 'cancel_allocation' && <p>Cancellation can release only an allocation with no issued units. Its history remains visible.</p>}
      <TextField label="Reason for budget proposal" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      <Submit pending={action.pending}>Preview budget change</Submit>
    </form>
    {prepared && <div className="prepared-preview"><h3>Review the proposed effect</h3><BudgetComparison value={prepared.result.preview} /><button className="button primary" disabled={action.pending} onClick={() => {
      const staged = prepared; void action.run(() => api<Amendment>(path + '/amendments', 'POST', staged.body), () => { setPrepared(null); refresh(); });
    }}>Save proposal for approval</button><p className="small">The server rechecks the milestone revision. A stale preview cannot spend the same budget twice.</p></div>}
  </section>;
}
