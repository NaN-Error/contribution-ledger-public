/** Exact unit input/output. No floating-point multiplication of decimal strings. */
export const UNIT_SCALE = 1000;
export const MAX_ATOMS = 1_000_000_000_000;
export const categories = ['code', 'art', 'design', 'qa', 'documentation', 'research', 'maintenance', 'marketing', 'production', 'community', 'other'] as const;
export type Category = typeof categories[number];
export type PoolKey = 'release' | 'ongoing';
export const deductions = ['platform_fees', 'refunds', 'sales_taxes', 'hosting', 'tools', 'marketing', 'approved_external_services'] as const;
export type Deduction = typeof deductions[number];

function decimalToScaled(text: string, digits: number, maximum: number): number {
  const input = text.trim();
  if (!new RegExp(`^(0|[1-9][0-9]*)(\\.[0-9]{1,${digits}})?$`).test(input)) {
    throw new Error(`Use a nonnegative decimal with up to ${digits} decimal places; no commas, signs or exponents.`);
  }
  if (input.length > 30) throw new Error('The amount is too large.');
  const [whole, fraction = ''] = input.split('.');
  const value = BigInt(whole) * (10n ** BigInt(digits)) + BigInt(fraction.padEnd(digits, '0'));
  if (value > BigInt(maximum)) throw new Error('The amount exceeds this application’s supported limit.');
  return Number(value);
}
export function parseUnits(text: string): number { return decimalToScaled(text, 3, MAX_ATOMS); }
export function parseWeight(text: string): number { return decimalToScaled(text, 2, 10000); }
export function unitInput(atoms: number): string {
  if (!Number.isSafeInteger(atoms) || atoms < 0 || atoms > MAX_ATOMS) throw new Error('Invalid unit atoms.');
  const value = BigInt(atoms);
  const fraction = String(value % 1000n).padStart(3, '0').replace(/0+$/, '');
  return `${value / 1000n}${fraction ? '.' + fraction : ''}`;
}
export function formatUnits(atoms: number): string {
  const [whole, decimal] = unitInput(atoms).split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (decimal ? '.' + decimal : '');
}
export function formatBps(bps: number): string {
  if (!Number.isSafeInteger(bps) || bps < 0 || bps > 10000) throw new Error('Invalid percentage basis points.');
  return `${Math.floor(bps / 100)}.${String(bps % 100).padStart(2, '0')}%`;
}
export function formatRatio(numerator: number, denominator: number): string {
  if (![numerator, denominator].every(v => Number.isSafeInteger(v) && v >= 0 && v <= MAX_ATOMS) || numerator > denominator) throw new Error('Invalid scoped ratio.');
  if (denominator === 0) return 'Not defined';
  // Integer half-up rounding for display only; no entitlement is rounded here.
  const bps = Number((BigInt(numerator) * 10000n * 2n + BigInt(denominator)) / (2n * BigInt(denominator)));
  return formatBps(bps);
}
export function explicitInstant(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new Error('Use a complete ISO time with an explicit UTC offset, such as 2030-01-01T12:00:00-04:00.');
  }
  return text;
}
export function humanLabel(value: string): string { return value.replaceAll('_', ' '); }

export interface PoolRule { key: PoolKey; weight_bps: number; eligibility: 'accepted_release_work' | 'accepted_work_in_accounting_period' }
export interface PolicyRules {
  schema_version: 1; currency: 'USD'; timezone: string; unit_scale: 1000; eligible_categories: Category[];
  review: { minimum_independent_reviewers: number; beneficiary_cannot_be_sole_approver: true; acceptance: 'budgeted_deliverables_only' };
  governance: { policy_approval: 'project_admin'; budget_approval: 'project_admin'; acknowledgement: 'snapshot_and_current_non_viewer_participants' };
  pools: PoolRule[];
  accounting: {
    cadence: 'calendar_month'; start_day: 1; boundary_time: '00:00:00'; boundary_resolution: 'reject_ambiguous_or_nonexistent_local_time';
    revenue_basis: 'gross_receipts' | 'net_storefront_settlements'; allowed_deductions: Deduction[]; distributable_definition: string;
    expense_approval: 'documented_project_admin_approval'; reserve_rule: string; capital_repayment_rule: string;
    empty_pool_rule: 'block_close'; dispute_rule: 'block_affected_close';
  };
  departure_rule: string; attribution_rule: string; unissued_units: 'unowned_until_accepted';
}
export interface Participant {
  user_id: string; display_name: string; role: string; required_at_creation: boolean; currently_required: boolean; acknowledged_at: string | null;
}
export interface Policy {
  id: string; version: number; predecessor_id: string | null; title: string; rules: PolicyRules; agreement_reference: string;
  reason: string; content_hash: string; created_by: string; created_at: string; is_latest_revision: boolean;
  approval: { approved_by: string; reason: string; created_at: string; effective_at: string } | null;
  acknowledgements: { participants: Participant[]; missing_user_ids: string[]; complete: boolean; note: string };
  my_acknowledgement: boolean; state: 'draft' | 'scheduled' | 'awaiting_acknowledgements' | 'effective' | 'historical';
  is_current_candidate: boolean; ready_for_pinned_work: boolean; usable_for_new_milestones: boolean; notice: string;
}
export interface PolicyCollection { items: Policy[]; latest_version: number; current_candidate_id: string | null }
export interface PolicyTemplate { key: string; title: string; example_only: boolean; rules: PolicyRules }
export interface BudgetTotals {
  total_atoms: number; reserve_floor_atoms: number; allocated_atoms: number; issued_atoms: number;
  unassigned_atoms: number; available_atoms: number; unissued_atoms: number;
}
export interface Allocation { id: string; title: string; category: Category; pool_key: PoolKey; atoms: number; issued_atoms: number; status: 'active' | 'cancelled'; version: number }
export interface BudgetSnapshot { milestone_id: string; policy_id: string; version: number; status: 'draft' | 'active'; allocations: Allocation[]; total_atoms: number; reserve_floor_atoms: number; allocated_atoms: number; issued_atoms: number }
export interface BudgetPreview {
  before: BudgetSnapshot; after: BudgetSnapshot; before_totals: BudgetTotals; after_totals: BudgetTotals;
  planned_budget_shares: { allocation_id: string; title: string; pool_key: PoolKey; before: { numerator_atoms: number; denominator_atoms: number }; after: { numerator_atoms: number; denominator_atoms: number } }[];
  personal_share_notice: string; credit_effect: string;
}
export interface PreviewResult { preview: BudgetPreview; preview_hash: string }
export type BudgetChange =
  | { kind: 'initial_budget' | 'set_budget'; total_atoms: number; reserve_floor_atoms: number }
  | { kind: 'allocate'; title: string; category: Category; pool_key: PoolKey; atoms: number }
  | { kind: 'resize_allocation'; allocation_id: string; atoms: number }
  | { kind: 'cancel_allocation'; allocation_id: string };
export interface AmendmentInput { expected_version: number; change: BudgetChange; reason: string }
export interface Amendment extends PreviewResult {
  id: string; expected_version: number; proposed_by: string; created_at: string; reason: string; change: BudgetChange;
  state: 'pending' | 'stale' | 'approved' | 'rejected';
  decision: { decision: 'approve' | 'reject'; decided_by: string; created_at: string; reason: string; resulting_version: number } | null;
}
export interface Milestone extends BudgetTotals {
  id: string; name: string; description: string; policy_id: string; status: 'draft' | 'active'; version: number; created_by: string; created_at: string; unit_scale: number; notice: string;
}
export interface MilestoneDetail extends Milestone { allocations: Allocation[]; amendments: Amendment[]; policy: Policy; history_offset: number; next_history_offset: number | null }
