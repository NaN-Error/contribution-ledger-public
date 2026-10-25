import { useId, type ReactNode } from 'react';
import { formatUnits, formatRatio, type BudgetPreview, type BudgetTotals } from '../lib/planning.js';

export function ConfirmCheck({ children, checked, onChange, disabled = false }: { children: ReactNode; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) {
  const id = useId();
  return <div className="confirm-check"><input type="checkbox" id={id} required checked={checked} onChange={e => onChange(e.target.checked)} disabled={disabled} /><label htmlFor={id}>{children}</label></div>;
}
export function BudgetMetrics({ value }: { value: BudgetTotals }) {
  const items: [string, number][] = [['Approved total', value.total_atoms], ['Planned allocations', value.allocated_atoms], ['Protected reserve', value.reserve_floor_atoms], ['Available to plan', value.available_atoms]];
  return <div className="budget-metrics">{items.map(([label, amount]) => <div className="budget-metric" key={label}><span>{label}</span><strong>{formatUnits(amount)}</strong><small>contribution units</small></div>)}</div>;
}
export function BudgetComparison({ value }: { value: BudgetPreview }) {
  const rows: [string, keyof BudgetTotals][] = [['Milestone total', 'total_atoms'], ['Protected reserve', 'reserve_floor_atoms'], ['Planned allocations', 'allocated_atoms'], ['Available to plan', 'available_atoms'], ['Issued units', 'issued_atoms']];
  return <div className="budget-comparison"><div className="table-scroll"><table><caption>Budget before and after this proposal</caption><thead><tr><th scope="col">Measure</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>
    {rows.map(([label, key]) => <tr key={key}><th scope="row">{label}</th><td>{formatUnits(value.before_totals[key])}</td><td>{formatUnits(value.after_totals[key])}</td></tr>)}
  </tbody></table></div>
  {value.planned_budget_shares.length > 0 && <div className="table-scroll"><table><caption>Planned allocation as a share of the milestone total</caption><thead><tr><th scope="col">Work allocation</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>{value.planned_budget_shares.map(row => <tr key={row.allocation_id}><th scope="row">{row.title}<small>{row.pool_key} pool</small></th><td>{formatRatio(row.before.numerator_atoms, row.before.denominator_atoms)}</td><td>{formatRatio(row.after.numerator_atoms, row.after.denominator_atoms)}</td></tr>)}</tbody></table></div>}
  <p className="planning-warning">{value.personal_share_notice} Percentages are rounded for display; calculations retain exact ratios.</p><p>{value.credit_effect}</p></div>;
}
