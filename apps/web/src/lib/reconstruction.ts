import type { Category, PoolKey } from './planning.js';
import type { PersonOption, AllocationOption, ScopeInput, WorkPackageDetail } from './workPackages.js';

export interface Fraction { numerator: number; denominator: number }
export interface HistoricalDefinition { title: string; start_at: string; end_before: string; historical_scope: string; agreement_reference: string; initial_approved_budget: BudgetSnapshot }
export interface BatchSummary { id: string; milestone_id: string; policy_id: string; definition: HistoricalDefinition; state: 'draft'|'approved'|'frozen'; version: number; created_at: string; notice: string }
export interface HistoricalAllocation { id: string; title: string; category: Category; pool_key: PoolKey; atoms: number; issued_atoms: number; status: string; version: number }
export interface BudgetSnapshot { total_atoms: number; allocated_atoms: number; reserve_floor_atoms: number; available_atoms?: number; issued_atoms: number; version: number; allocations: HistoricalAllocation[] }
export interface IdentityResolution { external_key: string; disposition: 'participant'|'context_only'; user_id: string|null; reason: string }
export interface CandidateDocument { title: string; category: Category; summary: string; unresolved_questions: string[]; identity_resolutions: IdentityResolution[] }
export interface HistoricalSource { id: string; entity_key: string; repository_id: string; repository: Record<string,unknown>; kind: string; remote_key: string; content_hash: string; captured_at: string; omissions: unknown[] }
export interface ObservedIdentity { external_key: string; display_name?: string; login?: string; kind?: string; role?: string; suggested_user_id: string|null; resolution: IdentityResolution|null; [key: string]: unknown }
export interface Candidate { id: string; version: number; state: 'draft'|'linked'|'rejected'|'superseded'; document: CandidateDocument & { provenance: Record<string,unknown> }; package_id: string|null; allocation_id: string|null; sources: HistoricalSource[]; identities: ObservedIdentity[]; blockers: string[]; review_hash: string }
export interface MissingClaim { id: string; created_by: string; document: { title: string; category: Category; description: string }; state: 'open'|'included'|'declined'; candidate_id: string|null; resolution_reason: string|null }
export interface CreditCapture { policy_id: string; pools: Record<string,{denominator_atoms:number;people:{user_id:string;display_name:string;atoms:number;share:Fraction}[]}>; awards: unknown[] }
export interface ScopeContext { batch_id:string;version:number;definition:HistoricalDefinition;milestone:BudgetSnapshot;policy_hash:string;policy_ready:boolean;credit:CreditCapture }
export interface ShareComparison { pool_key: string; baseline_denominator_atoms: number; current_denominator_atoms: number; batch_denominator_atoms: number; people: { user_id: string; display_name: string; baseline_atoms: number; current_atoms: number; batch_atoms: number; baseline_share: Fraction; current_share: Fraction }[] }
export interface OpeningRecord { schema: string; batch_id: string; version: number; historical_definition: HistoricalDefinition; baseline_at_scope_approval: ScopeContext|null; current_context: ScopeContext; batch_issued_atoms: number; share_comparison: ShareComparison[]; blockers: string[]; notice: string; [key: string]:unknown }
export interface OpeningPreview { record: OpeningRecord; review_hash: string }
export interface FrozenOpening { id: string; record: OpeningRecord; record_hash: string; created_at: string }
export interface BatchDetail extends BatchSummary { my_user_id: string; can_submit_claim: boolean; can_manage:boolean;can_inspect:boolean;my_claims_or_review_queue:MissingClaim[];candidates?:Candidate[];scope_context?:ScopeContext;scope_review_hash?:string;participants?:PersonOption[];allocations?:HistoricalAllocation[];frozen_snapshot?:FrozenOpening }
export interface BatchCollection { items: BatchSummary[]; can_manage:boolean;can_inspect:boolean;can_submit_claim:boolean;notice:string }
export interface ReconstructionOptions { milestones:{id:string;name:string;policy_id:string;total_atoms:number}[];imports:{id:string;repository_id:string;start_at:string;end_before:string;state:string;omission_count:number}[];imports_truncated:boolean;my_user_id:string;notice:string }
export interface HistoricalResult { result:{candidate_id?:string;package_id?:string;claim_id?:string;group_count?:number;source_count?:number;[key:string]:unknown};batch:BatchDetail }
export interface HistoryPage { items:{id:string;version:number;record:Record<string,unknown>;record_hash:string;previous_hash:string|null;created_at:string}[];next_offset:number|null }
export type HistoricalCreateHandler = (scope:ScopeInput,allocation:AllocationOption,reason:string)=>Promise<WorkPackageDetail>;

export function historicalCommand(version:number,reason:string) {
  if (!Number.isSafeInteger(version)||version<1) throw new Error('Reload the historical batch before making a change.');
  if (reason.trim().length<8||reason.length>500) throw new Error('Explain this decision using 8–500 characters.');
  return {request_id:crypto.randomUUID(),expected_version:version,reason:reason.trim()};
}
export function boundedHistoricalBody<T>(body:T):T {
  if (new TextEncoder().encode(JSON.stringify(body)).length>64_000) throw new Error('This command exceeds 64 KB. Split the candidate or shorten the description.');
  return body;
}
export function utcDateBoundary(date:string):string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('Enter a calendar date.');
  const value=date+'T00:00:00.000Z';const parsed=new Date(value);
  if (!Number.isFinite(parsed.getTime())||parsed.toISOString()!==value) throw new Error('Enter a real calendar date.');
  return value;
}
export function formatFraction(share:Fraction):string {
  if (!Number.isSafeInteger(share.numerator)||!Number.isSafeInteger(share.denominator)||share.numerator<0||share.denominator<0) return 'Unavailable';
  if (!share.denominator) return 'No denominator';
  const n=BigInt(share.numerator),d=BigInt(share.denominator);
  const hundredths=(n*10000n+d/2n)/d;
  return `${hundredths/100n}.${String(hundredths%100n).padStart(2,'0')}%`;
}
export function questionLines(value:string):string[] {
  const lines=value.split('\n').map(x=>x.trim()).filter(Boolean);
  if (lines.length>30||lines.some(x=>x.length<8||x.length>2000)) throw new Error('Use up to 30 questions of 8–2,000 characters each.');
  return lines;
}
export function makeCandidateDocument(value:CandidateDocument):CandidateDocument {
  if(value.title.trim().length<2||value.title.length>120||value.summary.trim().length<8||value.summary.length>2000) throw new Error('Add a title and a useful outcome description.');
  questionLines(value.unresolved_questions.join('\n'));
  if(new Set(value.identity_resolutions.map(x=>x.external_key)).size!==value.identity_resolutions.length) throw new Error('An observed identity can have only one disposition.');
  for(const row of value.identity_resolutions){
    if(row.reason.trim().length<8||row.reason.length>500) throw new Error('Explain every identity disposition using 8–500 characters.');
    if((row.disposition==='participant')!==!!row.user_id) throw new Error('A participant disposition requires a local contributor.');
  }
  return {...value,title:value.title.trim(),summary:value.summary.trim()};
}
export function promotionBody(batch:BatchDetail,candidate:Candidate,allocation:AllocationOption,scope:ScopeInput,reason:string,shared:boolean) {
  if(batch.state!=='approved'||candidate.state!=='draft'||candidate.blockers.length) throw new Error('Approve the scope and resolve the candidate before creating its package.');
  if(!shared) throw new Error('Review and explicitly approve sharing the pinned source records as project evidence.');
  if(allocation.milestone_id!==batch.milestone_id||allocation.category!==candidate.document.category) throw new Error('Use an approved allocation in this batch with the same category.');
  return boundedHistoricalBody({...historicalCommand(batch.version,reason),reviewed:true,reviewed_hash:candidate.review_hash,
    candidate_id:candidate.id,allocation_id:allocation.id,expected_allocation_version:allocation.version,scope,project_sharing_confirmed:true});
}
