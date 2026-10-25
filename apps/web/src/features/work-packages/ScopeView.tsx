import { Badge } from '../../components/shared.js';
import { formatUnits, formatBps, humanLabel } from '../../lib/planning.js';
import type { ScopeDocument } from '../../lib/workPackages.js';

export function ScopeView({ doc }: { doc: ScopeDocument }) {
  const name = (id: string) => doc.participant_labels[id] || id;
  return <div className="work-scope"><dl className="policy-facts">
    <div><dt>Category and pool</dt><dd>{humanLabel(doc.category)} · {doc.pool_key}</dd></div>
    <div><dt>Coordinator at this revision</dt><dd>{name(doc.coordinator_id)}</dd></div>
    <div><dt>Intended contributors</dt><dd>{doc.intended_contributor_ids.map(name).join(', ')}</dd></div>
    <div><dt>Pinned policy</dt><dd>Version {doc.policy_version} · <code>{doc.policy_id}</code></dd></div>
  </dl><h3>Intended outcome</h3><p className="preserve-text">{doc.outcome}</p>
  <h3>Package acceptance criteria</h3><ol className="work-criteria">{doc.acceptance_criteria.map((value, n) => <li key={n}>{value}</li>)}</ol>
  <h3>Required evidence</h3><p className="preserve-text">{doc.evidence_requirements}</p>
  <h3>Independently acceptable deliverables</h3>
  {!doc.deliverables.length && <p>No deliverables planned yet. This scope cannot be approved.</p>}
  {doc.deliverables.map((d, i) => <section className="work-deliverable" key={d.id}>
    <div className="section-heading"><h3>{i + 1}. {d.title}</h3><Badge>{formatUnits(d.budget_atoms)} planned units</Badge></div>
    <p className="preserve-text">{d.outcome}</p><ol className="work-criteria">{d.acceptance_criteria.map((criterion, n) => <li key={n}>{criterion}</li>)}</ol>
    <p className="preserve-text"><strong>Evidence required: </strong>{d.evidence_requirements}</p>
    <div className="table-scroll"><table><caption>Proposed split of this deliverable only — not an earned project or revenue share</caption>
      <thead><tr><th scope="col">Contributor</th><th scope="col">Role</th><th scope="col">Proposed units</th>{d.attribution.mode === 'percent' && <th scope="col">Entered percentage</th>}</tr></thead>
      <tbody>{d.resolved_attributions.map(e => <tr key={e.user_id + e.role}><th scope="row">{name(e.user_id)}</th><td>{humanLabel(e.role)}</td><td>{formatUnits(e.atoms)}</td>{d.attribution.mode === 'percent' && <td>{formatBps(e.basis_points ?? 0)}</td>}</tr>)}</tbody>
    </table></div><p>Unassigned: <strong>{formatUnits(d.unassigned_atoms)} units</strong>. {d.attribution_complete ? 'Attribution fully planned.' : 'Attribution remains incomplete and blocks approval.'}</p>
    {d.attribution.mode === 'percent' && <p className="small muted">Percentages resolve to whole atoms using stable largest-remainder rounding. A small share may resolve to zero atoms; it does not receive fabricated credit.</p>}
    <small className="muted wrap">Deliverable reference: {d.id}</small>
  </section>)}<p>Scope budget: {formatUnits(doc.budget_atoms)} units · Deliverables: {formatUnits(doc.deliverable_atoms)} · Not yet planned: {formatUnits(doc.unplanned_atoms)}</p></div>;
}
