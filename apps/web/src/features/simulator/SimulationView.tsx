import { Badge } from '../../components/shared.js';
import { formatCents,poolWeight,type SimulationRecord } from '../../lib/simulator.js';
import { formatCreditUnits,formatShare } from '../../lib/reviews.js';
import { humanLabel } from '../../lib/planning.js';

export function SimulationView({record}:{record:SimulationRecord}) {
  const {snapshot,result}=record;
  const names=new Map(snapshot.people.map(p=>[p.user_id,p.display_name]));
  return <div className="simulation-output">
    <section className="panel"><p className="eyebrow">Hypothetical · not payable</p><h2>Simulation results</h2>
      <Badge tone={result.status==='blocked'?'warning':'muted'}>{result.status==='blocked'?'Incomplete — blocked pool':'Calculated example only'}</Badge>
      <p>{record.notice}</p><div className="sim-metrics">
        <div><span>Hypothetical distributable amount</span><strong>{formatCents(result.amount_cents)}</strong></div>
        <div><span>Allocated within this example</span><strong>{formatCents(result.allocated_cents)}</strong></div>
        <div><span>Unallocated because of blockers</span><strong>{formatCents(result.unallocated_cents)}</strong></div>
      </div>
      <p>Captured {new Date(record.captured_at).toLocaleString()}. Saved examples are not live balances. Refreshing an example never recalculates its historical result.</p>
      <p>Source credit: policy version {snapshot.source_policy.version}. Calculation rules: version {snapshot.calculation_policy.version} ({humanLabel(snapshot.calculation_policy.state)}).</p>
      <p>{snapshot.period.month} in {snapshot.period.timezone}. The UTC interval is {snapshot.period.start_inclusive} (inclusive) to {snapshot.period.end_exclusive} (exclusive).</p>
      <p className="small">Release work: accepted before the selected month ends, cumulative through that point. Ongoing work: originally accepted during that month. Both use only awards already available at capture time, with current corrected attribution.</p>
      <details className="form-details"><summary>Scope and interpretation warnings</summary>{snapshot.warnings.map((warning,i)=><p key={i}>{warning}</p>)}</details>
    </section>
    <section className="panel"><h3>Hypothetical contributor totals</h3><p>{result.status==='blocked'?'Only unblocked pools are included below. Do not use these partial totals as a distribution.':'These totals illustrate the selected scenario, not amounts owed or paid.'}</p>
      {!result.people.length?<p>No contributor amounts can be calculated from this scope.</p>:<div className="table-scroll"><table><caption>Non-payable example totals</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Hypothetical USD</th></tr></thead><tbody>{result.people.map(person=><tr key={person.user_id}><th scope="row">{names.get(person.user_id)||person.user_id}<small className="wrap">{person.user_id}</small></th><td>{formatCents(person.amount_cents)}</td></tr>)}</tbody></table></div>}
    </section>
    {result.pools.map(pool=><section className="panel" key={pool.key}><h3>{humanLabel(pool.key)} pool · {poolWeight(pool.weight_bps)}</h3>
      <p>{formatCents(pool.amount_cents)} of the hypothetical amount. Eligible credit: {formatCreditUnits(pool.denominator_atoms)} units.</p>
      <p className="small">Pool rounding: {formatCents(pool.pool_rounding.floor_cents)} floor + {pool.pool_rounding.rounding_cent} rounding cent. Fractional-cent remainder: {pool.pool_rounding.remainder_numerator}/{pool.pool_rounding.denominator}.</p>
      {pool.blockers.length>0?<div className="error-panel" role="status"><strong>This pool is not allocated.</strong>{pool.blockers.map(b=><p key={b}>{b==='empty_pool'?'No eligible finalized contribution units define this denominator. Pending work is not substituted.':'An unresolved attribution dispute blocks this pool. Its amount is not reassigned to other contributors.'}</p>)}<p>{formatCents(pool.unallocated_cents)} remains unallocated in this example.</p></div>:<div className="table-scroll"><table><caption>Exact credit shares and per-person rounding in the {pool.key} pool</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Units / denominator</th><th scope="col">Share (display rounded)</th><th scope="col">Floor + cent</th><th scope="col">Hypothetical USD</th></tr></thead><tbody>{pool.allocations.map(line=><tr key={line.key}><th scope="row">{names.get(line.key)||line.key}</th><td>{formatCreditUnits(line.weight)} / {formatCreditUnits(line.denominator)}</td><td>{formatShare(line.weight,line.denominator)}</td><td>{formatCents(line.floor_cents)} + {line.rounding_cent}<small>Remainder {line.remainder_numerator}/{line.denominator}</small></td><td>{formatCents(line.amount_cents)}</td></tr>)}</tbody></table></div>}
      <p className="small">Unissued planned work in this pool across the source policy: {formatCreditUnits(snapshot.pending_by_pool[pool.key]||0)} units. This planning total is not month-filtered and is not included in the contribution denominator.</p>
    </section>)}
    <section className="panel"><h3>Planning is not earned credit</h3><p>{formatCreditUnits(snapshot.pending_planned_atoms)} units remain planned but unissued across all source-policy milestones, regardless of the selected month.</p>
      {!snapshot.planning.length?<p>No milestones under the selected source policy.</p>:<div className="table-scroll"><table><caption>Current source-policy planning captured with this example</caption><thead><tr><th scope="col">Milestone</th><th scope="col">Total</th><th scope="col">Planned</th><th scope="col">Issued</th><th scope="col">Protected reserve</th><th scope="col">Available</th></tr></thead><tbody>{snapshot.planning.map(m=><tr key={m.milestone_id}><th scope="row">{m.name}<small>Version {m.version}</small></th><td>{formatCreditUnits(m.total_atoms)}</td><td>{formatCreditUnits(m.planned_atoms)}</td><td>{formatCreditUnits(m.issued_atoms)}</td><td>{formatCreditUnits(m.protected_reserve_atoms)}</td><td>{formatCreditUnits(m.available_to_plan_atoms)}</td></tr>)}</tbody></table></div>}
    </section>
    <section className="panel"><h3>Reproducible source snapshot</h3><p>Engine: {result.engine_version}. Tie-breaks use ascending stable pool and contributor identifiers, never display names or input order.</p>
      <p className="small">Rounding occurs first between pools and then between contributors. Largest-remainder rounding can move a cent away from someone when inputs change; monotonic individual amounts are not guaranteed.</p>
      <dl className="sim-fingerprints"><dt>Ledger revision</dt><dd><code>{snapshot.ledger_revision}</code></dd><dt>Input and snapshot fingerprint</dt><dd><code>{record.snapshot_hash}</code></dd><dt>Result fingerprint</dt><dd><code>{record.result_hash}</code></dd></dl>
      <p>{snapshot.source_award_count} source awards · {snapshot.source_event_count} ledger events · {snapshot.eligible_awards.length} eligible awards. {snapshot.excluded_source_award_count} source awards and {snapshot.excluded_other_policy_award_count} other-policy awards are outside this example.</p>
      <details className="form-details"><summary>Inspect included award attribution</summary>{snapshot.eligible_awards.map(a=><article key={a.award_id}><p className="wrap"><strong>{a.pool_key} award {a.award_id}</strong><br/>{formatCreditUnits(a.budget_atoms)} units · accepted {new Date(a.accepted_at).toLocaleString()}</p><p className="wrap">Package {a.package_id} · milestone {a.milestone_id}</p>{a.current_attributions.map(line=><p key={line.user_id+line.role}>{names.get(line.user_id)||line.user_id} · {humanLabel(line.role)} · {formatCreditUnits(line.atoms)} units</p>)}</article>)}</details>
    </section>
  </div>;
}
