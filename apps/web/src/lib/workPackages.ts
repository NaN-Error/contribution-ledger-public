import { parseUnits, parseWeight, unitInput, type Category, type PoolKey } from './planning.js';

export const workStates = ['draft', 'budget_approved', 'in_progress', 'submitted', 'changes_requested', 'cancelled', 'completed'] as const;
export type WorkState = typeof workStates[number];
export const workRoles = ['implementation', 'design', 'testing', 'review', 'documentation', 'production', 'other'] as const;
export type WorkRole = typeof workRoles[number];
export type WorkAction = 'approve_scope' | 'start' | 'submit' | 'request_changes' | 'withdraw' | 'cancel' | 'refresh_submission';
export const actionLabels: Record<WorkAction, string> = {
  refresh_submission: 'Resubmit with current evidence',
  approve_scope: 'Approve this scope for work', start: 'Start work', submit: 'Submit readiness declaration',
  request_changes: 'Request scope changes', withdraw: 'Withdraw submission for amendment', cancel: 'Cancel package and release its budget',
};
export interface PersonOption { user_id: string; display_name: string; role: string }
export interface AllocationOption {
  id: string; milestone_id: string; milestone_name: string; policy_id: string; title: string;
  category: Category; pool_key: PoolKey; atoms: number; version: number;
}
export interface WorkOptions {
  my_user_id: string; can_create: boolean; can_assess?: boolean; participants: PersonOption[]; allocations: AllocationOption[];
  allocations_truncated: boolean; notice: string;
}
export interface UnitEntry { user_id: string; role: WorkRole; atoms: number }
export interface PercentEntry { user_id: string; role: WorkRole; basis_points: number }
export type AttributionPlan = { mode: 'units'; entries: UnitEntry[] } | { mode: 'percent'; entries: PercentEntry[] };
export interface DeliverableInput {
  id: string | null; title: string; outcome: string; acceptance_criteria: string[]; evidence_requirements: string;
  budget_atoms: number; attribution: AttributionPlan;
}
export interface ScopeInput {
  title: string; outcome: string; acceptance_criteria: string[]; evidence_requirements: string;
  coordinator_id: string; intended_contributor_ids: string[]; deliverables: DeliverableInput[];
}
export interface DeliverableDocument extends DeliverableInput {
  id: string; resolved_attributions: (UnitEntry & { basis_points?: number })[]; unassigned_atoms: number; attribution_complete: boolean;
}
export interface ScopeDocument extends ScopeInput {
  deliverables: DeliverableDocument[]; participant_labels: Record<string, string>;
  budget_atoms: number; deliverable_atoms: number; unplanned_atoms: number;
  milestone_id: string; allocation_id: string; policy_id: string; policy_version: number; policy_hash: string;
  category: Category; pool_key: PoolKey;
}
export interface ScopeRevision {
  number: number; allocation_version: number; document: ScopeDocument; content_hash: string;
  created_by: string; reason: string; created_at: string;
}
export interface WorkPackageSummary {
  origin: 'prospective' | 'retrospective'; reconstruction_batch_id: string|null;
  id: string; milestone_id: string; milestone_name: string; allocation_id: string; policy_id: string; state: WorkState;
  version: number; scope_revision: number; approved_revision: number | null;
  title: string; category: Category; pool_key: PoolKey; coordinator_id: string; coordinator_name: string;
  budget_atoms: number; scope_budget_atoms: number; deliverable_atoms: number; unplanned_atoms: number;
  issued_atoms: number; created_at: string;
}
export interface WorkEvent {
  id: string; version: number; scope_revision: number; actor_id: string; action: string;
  reason: string; details: Record<string, unknown>; created_at: string;
}
export interface SubmissionSummary {
  id: string; scope_revision: number; package_version: number; submitted_by: string; snapshot_hash: string; created_at: string;
}
export interface SubmissionRecord extends SubmissionSummary {
  snapshot: { scope: ScopeDocument; submission_note: string; evidence_status: string; notice: string; [key: string]: unknown };
}
export interface WorkPackageDetail extends WorkPackageSummary {
  revision: ScopeRevision; allocation_version: number; review_hash: string; blockers: string[];
  can_edit: boolean; allowed_actions: WorkAction[]; policy: { id: string; version: number; title: string; state: string; ready: boolean };
  history: WorkEvent[]; history_offset: number; next_history_offset: number | null;
  recent_submissions: SubmissionSummary[]; notice: string;
}
export interface WorkCollection { items: WorkPackageSummary[]; total: number; offset: number; next_offset: number | null }

export interface AttributionDraft { key: string; user_id: string; role: WorkRole; amount: string }
export interface DeliverableDraft {
  id: string; title: string; outcome: string; criteria: string; evidence: string; units: string;
  mode: 'units' | 'percent'; entries: AttributionDraft[];
}
export interface ScopeDraft {
  title: string; outcome: string; criteria: string; evidence: string; coordinator: string;
  intended: string[]; deliverables: DeliverableDraft[];
}
export function newDeliverable(id: string): DeliverableDraft {
  return { id, title: '', outcome: '', criteria: '', evidence: '', units: '', mode: 'units', entries: [] };
}
export function newScope(coordinator: string, title = ''): ScopeDraft {
  return { title, outcome: '', criteria: '', evidence: '', coordinator, intended: coordinator ? [coordinator] : [], deliverables: [] };
}
export function scopeDraft(doc: ScopeDocument): ScopeDraft {
  return { title: doc.title, outcome: doc.outcome, criteria: doc.acceptance_criteria.join('\n'), evidence: doc.evidence_requirements,
    coordinator: doc.coordinator_id, intended: [...doc.intended_contributor_ids], deliverables: doc.deliverables.map(d => ({
      id: d.id, title: d.title, outcome: d.outcome, criteria: d.acceptance_criteria.join('\n'), evidence: d.evidence_requirements,
      units: unitInput(d.budget_atoms), mode: d.attribution.mode,
      entries: d.attribution.mode === 'units'
        ? d.attribution.entries.map((e, n) => ({ key: `${d.id}:${n}`, user_id: e.user_id, role: e.role, amount: unitInput(e.atoms) }))
        : d.attribution.entries.map((e, n) => ({ key: `${d.id}:${n}`, user_id: e.user_id, role: e.role, amount: `${Math.floor(e.basis_points / 100)}.${String(e.basis_points % 100).padStart(2, '0')}` })),
    })) };
}
function criteria(text: string, label: string): string[] {
  const rows = text.split('\n').map(x => x.trim()).filter(Boolean);
  if (!rows.length || rows.length > 20 || rows.some(x => x.length < 8 || x.length > 2000) || new Set(rows).size !== rows.length) {
    throw new Error(`${label}: enter 1–20 distinct criteria, one per line, with 8–2,000 characters each.`);
  }
  return rows;
}
export function buildScope(draft: ScopeDraft, parentAtoms: number): ScopeInput {
  if (draft.deliverables.length > 30) throw new Error('Use no more than 30 independently acceptable deliverables.');
  if (!draft.coordinator || !draft.intended.length) throw new Error('Choose a coordinator and at least one intended contributor.');
  const deliverables = draft.deliverables.map((d, index): DeliverableInput => {
    const budget = parseUnits(d.units);
    if (!budget) throw new Error(`Deliverable ${index + 1} needs a positive budget.`);
    if (d.entries.length > 30) throw new Error('Use no more than 30 attribution rows per deliverable.');
    if (new Set(d.entries.map(e => e.user_id + ':' + e.role)).size !== d.entries.length) throw new Error('Do not repeat the same person and role within a deliverable.');
    if (d.entries.some(e => !draft.intended.includes(e.user_id))) throw new Error('Every attributed person must be selected as an intended contributor.');
    let attribution: AttributionPlan;
    if (d.mode === 'units') {
      const entries = d.entries.map(e => ({ user_id: e.user_id, role: e.role, atoms: parseUnits(e.amount) }));
      if (entries.some(e => !e.atoms) || entries.reduce((n, e) => n + e.atoms, 0) > budget) throw new Error('Use positive proposed units within the deliverable budget.');
      attribution = { mode: 'units', entries };
    } else {
      const entries = d.entries.map(e => ({ user_id: e.user_id, role: e.role, basis_points: parseWeight(e.amount) }));
      if (entries.some(e => !e.basis_points) || entries.reduce((n, e) => n + e.basis_points, 0) > 10000) throw new Error('Use positive percentages totaling no more than 100% per deliverable.');
      attribution = { mode: 'percent', entries };
    }
    return { id: d.id, title: d.title, outcome: d.outcome, acceptance_criteria: criteria(d.criteria, d.title || `Deliverable ${index + 1}`),
      evidence_requirements: d.evidence, budget_atoms: budget, attribution };
  });
  if (deliverables.reduce((n, d) => n + d.budget_atoms, 0) > parentAtoms) throw new Error('The deliverables exceed the approved parent allocation.');
  return { title: draft.title, outcome: draft.outcome, acceptance_criteria: criteria(draft.criteria, 'Work package'),
    evidence_requirements: draft.evidence, coordinator_id: draft.coordinator,
    intended_contributor_ids: draft.intended, deliverables };
}
export function boundedWorkBody<T>(body: T): T {
  if (new TextEncoder().encode(JSON.stringify(body)).length > 64_000) throw new Error('This scope exceeds the local 64 KB request limit. Split it into smaller packages or shorten repeated criteria.');
  return body;
}
