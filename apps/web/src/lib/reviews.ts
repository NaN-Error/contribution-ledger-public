import { parseUnits } from './planning.js';
import { workRoles, type WorkRole } from './workPackages.js';

export interface ReviewPerson { user_id: string; display_name: string; role: string }
export interface CreditLine { user_id: string; display_name: string; role: WorkRole; atoms: number }
export interface Criterion { id: string; text: string }
export interface EvidenceSource { restricted?: boolean; ref?: string; title?: string; evidence_id?: string; revision?: number; visibility?: string }
export interface ReviewTarget {
  kind: 'award' | 'uphold' | 'reallocate'; package_id: string; title: string; package_title: string;
  deliverable_id: string; policy_id: string; policy_version: number; pool_key: string; budget_atoms: number;
  attributions: CreditLine[]; before_attributions?: CreditLine[]; criteria: Criterion[];
  evidence_sources: EvidenceSource[]; evidence_snapshot_id: string; submission_id: string;
  scope_hash?: string; evidence_snapshot_hash?: string;
  resolver_id?: string; award_id?: string; notice: string;
  context?: { opening_reason: string; notes: { id: string; text: string; source_url: string | null; created_by: string }[] };
}
export interface Finding { criterion_id: string; result: 'supported'|'unsupported'|'insufficient'; evidence_refs: string[]; explanation: string }
export interface ReviewRecord {
  id: string; kind: ReviewTarget['kind']; number: number; package_id: string; deliverable_id: string; dispute_id: string | null;
  target: ReviewTarget; target_hash: string; state: string; blocker: string | null; reason: string; created_at: string;
  reviewer_ids: string[]; minimum_reviewers: number; decisions_hash: string;
  decisions: { id: string; reviewer_id: string; decision: string; findings: Finding[]; reason: string | null; created_at: string }[];
  can_read_assessments?: boolean; can_decide: boolean; can_finalize: boolean; finalized_record_id: string | null;
}
export interface ReviewOption {
  deliverable_id: string; title: string; budget_atoms: number; award_id: string | null; target_hash: string | null;
  minimum_reviewers: number | null; eligible_reviewers: ReviewPerson[]; blocker: string | null;
}
export interface ReviewOptions { package_id: string; package_version: number; items: ReviewOption[]; can_assign: boolean; notice: string }
export interface ReviewSummary { id: string; title: string; package_title: string; kind: string; number: number; state: string; blocker: string | null; created_at: string }
export interface Paged<T> { items: T[]; offset: number; next_offset: number | null }
export interface CreditAward {
  id: string; package_id: string; deliverable_id: string; title: string; budget_atoms: number; pool_key: string;
  policy_id: string; policy_version: number; milestone_id: string; review_id: string; submission_id: string;
  evidence_snapshot_id: string; original_attributions: CreditLine[]; current_attributions: CreditLine[];
  current_balance_hash: string; finalized_by: string; reason: string; created_at: string;
  events?: { id: string; review_id: string; resolution_id: string|null; kind: string; user_id: string;
    display_name: string; role: string; delta_atoms: number; created_at: string }[]; next_offset?: number|null;
}
export interface ContributionGroup {
  policy_id: string; policy_version: number; milestone_id: string; milestone_name: string; pool_key: string;
  denominator_atoms: number; pending_planned_atoms: number; disputed_atoms: number; close_blocked: boolean;
  people: { user_id: string; display_name: string; atoms: number; roles: Record<string,number>; share: {numerator:number;denominator:number} }[];
}
export interface Contributions { groups: ContributionGroup[]; my_user_id:string; total_issued_atoms:number;
  pending_planned_atoms:number; open_dispute_count:number; award_count:number; notice:string }
export interface DisputeRecord {
  id:string; award:CreditAward; opened_by:string; reason:string; state:'open'|'resolved'; created_at:string;
  context_hash:string; notes:{id:string;created_by:string;text:string;source_url:string|null}[];
  resolver_id:string|null; resolver_candidates:ReviewPerson[]; current_participants:ReviewPerson[]; minimum_reviewers:number;
  assignments:{number:number;resolver_id:string;assigned_by:string;reason:string;created_at:string}[];
  resolution:{id:string;review_id:string;disposition:string;resolved_by:string;reason:string;created_at:string}|null;
  review_ids:string[]; can_assign:boolean; can_note:boolean; can_propose:boolean; notice:string;
}
export interface DisputeSummary { id:string;award_id:string;package_id:string;reason:string;state:string;created_at:string }

export function initialFindings(criteria: Criterion[]): Finding[] {
  return criteria.map(c=>({criterion_id:c.id,result:'insufficient',evidence_refs:[],explanation:''}));
}
export function validateDecision(review: ReviewRecord, decision: string, findings: Finding[], reviewed: boolean, independent: boolean): void {
  if (!reviewed || !independent) throw new Error('Review the actual evidence and confirm your independence.');
  if (!['accept','request_evidence','reject'].includes(decision)) throw new Error('Choose a valid decision.');
  const ids=findings.map(f=>f.criterion_id); const expected=review.target.criteria.map(c=>c.id);
  if (new Set(ids).size!==ids.length || ids.length!==expected.length || expected.some(id=>!ids.includes(id))) throw new Error('Address every criterion exactly once.');
  const refs=new Set(review.target.evidence_sources.filter(s=>!s.restricted).map(s=>s.ref));
  for (const f of findings) {
    if (!['supported','unsupported','insufficient'].includes(f.result) || f.explanation.trim().length<8 || f.explanation.length>500) throw new Error('Explain each finding using 8 to 500 characters.');
    if (new Set(f.evidence_refs).size!==f.evidence_refs.length || f.evidence_refs.some(ref=>!refs.has(ref))) throw new Error('Use supporting references from this exact packet.');
    if (decision==='accept' && (f.result!=='supported' || !f.evidence_refs.length)) throw new Error('Every accepted criterion needs a supported finding and at least one evidence reference.');
  }
}
export function formatCreditUnits(atoms:number):string {
  if (!Number.isSafeInteger(atoms) || atoms<0) throw new Error('Invalid contribution amount.');
  const n=BigInt(atoms);const decimals=String(n%1000n).padStart(3,'0').replace(/0+$/,'');
  return String(n/1000n).replace(/\B(?=(\d{3})+(?!\d))/g,',')+(decimals?'.'+decimals:'');
}
export function formatDelta(atoms:number):string {
  if (!Number.isSafeInteger(atoms)) throw new Error('Invalid signed contribution amount.');
  return (atoms>0?'+':atoms<0?'−':'')+formatCreditUnits(Math.abs(atoms));
}
export function formatShare(numerator:number,denominator:number):string {
  if (![numerator,denominator].every(v=>Number.isSafeInteger(v)&&v>=0) || numerator>denominator) throw new Error('Invalid scoped contribution share.');
  if (!denominator) return 'Not defined';
  const bps=(BigInt(numerator)*20000n+BigInt(denominator))/(2n*BigInt(denominator));
  return `${bps/100n}.${String(bps%100n).padStart(2,'0')}%`;
}
export function correctionRows(rows:{user_id:string;role:string;units:string}[],budget:number) {
  const seen=new Set<string>();
  const entries=rows.map(row=>{
    const key=row.user_id+':'+row.role;
    if (!row.user_id || !workRoles.includes(row.role as WorkRole) || seen.has(key)) throw new Error('Use distinct valid contributor and role rows.');
    seen.add(key);const atoms=parseUnits(row.units);
    if (!atoms) throw new Error('Correction rows need positive units. Remove a row rather than assigning zero.');
    return {user_id:row.user_id,role:row.role as WorkRole,atoms};
  });
  if (entries.reduce((sum,e)=>sum+BigInt(e.atoms),0n)!==BigInt(budget)) throw new Error('The replacement allocation must equal the original accepted budget exactly.');
  return entries;
}
