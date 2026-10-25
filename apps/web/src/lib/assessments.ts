import type { AIProfile,AIJob } from './ai.js';
import type { ReviewRecord } from './reviews.js';
export interface AssessmentOptions {
  role:string; can_approve_data:boolean; package_id:string; package_version:number; state:string;
  deliverables:{id:string;title:string}[]; profiles:AIProfile[]; profiles_truncated?:boolean; active_profile_id:string|null;
  evidence:{id:string;revision:number;kind:string;title:string;visibility:string;inclusion:string}[];
  live_evidence_enabled:boolean; notice:string;
}
export interface Source {id:string;kind:string;title:string;lines:string[]}
export interface Citation {source_id:string;start_line:number;end_line:number}
export interface PacketPayload {packet_version:string;outcome:string;deliverable:string;criteria:{id:string;text:string}[];
  contributors:{alias:string}[];sources:Source[];omissions:{code:string;count:number}[];notice:string}
export interface Packet {
  id:string;package_id:string;scope_revision:number;submission_id:string;deliverable_id:string;profile_id:string;
  content_hash:string;prompt_hash:string;stale:boolean;reason:string;created_at:string;source_count:number;
  payload:PacketPayload;capture:{scope_hash:string;evidence_snapshot_hash:string;criteria_map:Record<string,string>;
    aliases:Record<string,string>;redaction_counts:Record<string,number>;privacy_notice:string;
    sources:Record<string,{evidence_id:string;revision:number;evidence_ref:string;title:string}>};
}
export interface RunPlan {
  id:string;packet_id:string;profile_id:string;connection_id:string;package_id:string;deliverable_id:string;
  mode:'official'|'advisory';prior_plan_id:string|null;content_hash:string;reason:string;created_at:string;
  definition:{provider:string;requested_model:string;payer_id:string;max_output_tokens:number;audience:string;notice:string};
  packet_stale:boolean;can_approve_data:boolean;can_pay:boolean;can_revoke:boolean;revoked:boolean;result_id:string|null;
  grant:null|{id:string;approved_by:string;valid_until:string;permission_reference:string;reason:string};job:AIJob|null;notice:string;
}
export interface AssessmentQuote {quote_hash:string;notice:string;data_notice:string;
  specification:{reservation_microusd:number;month:string;remote_id:string;input_token_allowance:number;max_output_tokens:number}}
export interface AssessmentFinding {criterion_id:string;status:'supported'|'contradicted'|'insufficient';explanation:string;evidence_refs:Citation[]}
export interface AssessmentResult {
  id:string;plan_id:string;job_id:string;status:string;content_hash:string;created_at:string;mode:'official'|'advisory';
  document:null|{schema_version:string;summary:string;findings:AssessmentFinding[];
    proposed_roles:{contributor_alias:string;role:string;explanation:string;evidence_refs:Citation[]}[];
    overlap_flags:{explanation:string;evidence_refs:Citation[]}[];questions:string[]};
  metadata:{synthetic:boolean;provider:string;requested_model:string;returned_model:string|null;provider_request_id:string|null;
    prompt_version:string;schema_version:string;rubric_version:string;input_tokens:number|null;output_tokens:number|null;finish:string};
  packet:Packet;notice:string;
}
export interface ReviewerObservation {id:string;created_by:string;review_id:string;criterion_id:string;action:string;reason:string;replacement_text:string|null;created_at:string}

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function parseExcludedPaths(value:string):string[] {
  const rows=value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
  if(rows.length>30||rows.some(p=>p.length>200||p.includes('\0')||p.includes('://')))throw new Error('Use at most 30 bounded repository path patterns, not URLs.');
  return [...new Set(rows)];
}
export function assessmentRequest(q:AssessmentQuote,id:string,approved:boolean) {
  if(approved!==true)throw new Error('The payer must explicitly approve this exact request.');
  if(!uuid.test(id)||!/^[0-9a-f]{64}$/.test(q.quote_hash)||!Number.isSafeInteger(q.specification.reservation_microusd)||q.specification.reservation_microusd<0||q.specification.reservation_microusd>1_000_000_000)
    throw new Error('Refresh and review a valid assessment quotation.');
  return {request_id:id,quote_hash:q.quote_hash,confirmed_reservation_microusd:q.specification.reservation_microusd,payer_approved:true};
}
export function citedLines(packet:PacketPayload,ref:Citation):string[] {
  const source=packet.sources.find(s=>s.id===ref.source_id);
  if(!source||!Number.isInteger(ref.start_line)||!Number.isInteger(ref.end_line)||ref.start_line<1||ref.end_line<ref.start_line||ref.end_line>source.lines.length)
    throw new Error('This citation does not identify available packet lines.');
  return source.lines.slice(ref.start_line-1,ref.end_line).map((line,index)=>`${ref.start_line+index}: ${line}`);
}
export function feedbackEligible(result:AssessmentResult,review:ReviewRecord):boolean {
  return result.status==='valid'&&result.document!==null&&result.packet.stale===false&&review.kind==='award'&&review.can_decide===true
    &&review.package_id===result.packet.package_id&&review.deliverable_id===result.packet.deliverable_id
    &&review.target.submission_id===result.packet.submission_id&&review.target.scope_hash===result.packet.capture.scope_hash
    &&review.target.evidence_snapshot_hash===result.packet.capture.evidence_snapshot_hash;
}
export function planStatus(plan:RunPlan):string {
  if(plan.revoked)return 'Disclosure revoked';
  if(plan.packet_stale)return 'Evidence or acceptance changed';
  if(plan.job)return plan.job.status;
  if(!plan.grant)return 'Waiting for administrator data approval';
  return 'Data approved; payer request still required';
}
