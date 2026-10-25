import type { OverviewReport } from './overview.js';
import { utcDayRange } from './github.js';

export interface AnalysisRun { id:string; state:string; version:number; requests:number; completed_tasks:number; total_tasks:number; source_count:number; omissions:string[]; error_code:string|null; retry_after:string|null; created_at:string; finished_at:string|null; definition:{repository_urls:string[];import_ids:string[];start_at:string;end_before:string} }
export interface AnalysisPerson {key:string;name:string;kind:string;username:string|null;aliases:{key:string;name:string;username:string|null}[];repositories:string[];roles:string[];proposed_atoms:number;outcome_ids:string[];share:{numerator:number;denominator:number};estimated_cents:number;summary:string;github_usernames?:string[];approved_user_ids?:string[];highlights?:{label:string;title:string;outcome_id:string}[]}
export interface AnalysisProposal {proposed_atoms:number;entries:{contributor_key:string;atoms:number}[];rationale:string;rubric_version:string}
export interface AnalysisSource {id:string;kind:string;repository:string|null;url:string|null;title:string;excerpt:string;omissions:string[];content_hash?:string;context_only?:boolean;recorded_times?:Partial<Record<'created_at'|'updated_at'|'closed_at'|'merged_at'|'submitted_at'|'git_author_date'|'git_committer_date',string>>}
export interface AnalysisOutcome {id:string;title:string;category:string;origin:string;summary:string;findings?:{label:string;text:string;source_ids:string[]}[];repositories:string[];files:string[];contributors:{key:string;roles:string[]}[];proposal:AnalysisProposal|null;proposal_stale:boolean;limitations:string[];manual_id?:string;handoff?:{id:string;package_id:string;created_at:string}|null;sources:AnalysisSource[]}
export interface ManualEntry {id:string;title:string;description:string;category:string;contributor_key:string;evidence:string;performed_at:string;repository:string|null;proposed_atoms:number;rationale:string;status:'proposed'|'excluded'}
export interface ManualHistory {contribution_id:string;truncated:boolean;revisions:{version:number;created_at:string;created_by:string;reason:string;entry:ManualEntry}[]}
export interface AnalysisDashboard {report_id:string|null;draft_version:number;contributors:AnalysisPerson[];outcomes:AnalysisOutcome[];proposed_denominator_atoms:number;unassigned_atoms:number;stale_proposal_count:number;denominator_label:string;aliases:Record<string,string>;manual_entries:ManualEntry[];rubric:{version:string;name:string;criteria:string[];notice:string};scenario:{amount_cents:number;allocated_cents:number;unallocated_cents:number;currency:string;synthetic_only:true;payable:false};recognized:OverviewReport;report:{scope:null|{start_at:string;end_before:string};repositories:{full_name:string;private:boolean;description:string;anchor_sha:string|null;latest_commit_at?:string|null;history_unavailable?:boolean;tree_paths:string[];context:{path:string;text:string;anchor_sha:string}[]}[];omissions:string[];source_count?:number}}
export interface AnalysisPublication {id:string;created_at:string;created_by:string;reason:string;content_hash:string;report_id:string;draft_version:number;revoked_at:string|null;revocation_reason:string|null}
export interface AnalysisSharingPreview {document:Omit<AnalysisDashboard,'recognized'>;review_hash:string;notice:string}
export interface RepositoryConnection {id:string;version:number;method:'token'|'cli';username:string;repository_urls:string[];active:boolean;expires_at:string}
export interface AnalysisOverview {can_manage:boolean;runs:AnalysisRun[];imports:{id:string;repository:string;private:boolean;start_at:string;end_before:string}[];dashboard:AnalysisDashboard;private_reads_enabled?:boolean;cli_available?:boolean;connection?:RepositoryConnection|null;shared?:{publication_id:string|null;created_at:string|null;content_hash:string|null;items:AnalysisPublication[];notice:string}}
export interface AnalysisRoute {workspace:string;project:string;report:string;person:string;outcome:string;publication?:string}

export function manualWorkDay(performedAt:string):string {return new Date(performedAt).toISOString().slice(0,10);}
export function manualPerformedAt(day:string,entry?:Pick<ManualEntry,'performed_at'>):string {
  return entry&&day===manualWorkDay(entry.performed_at)?entry.performed_at:day+'T12:00:00Z';
}

export function repositoryActivityRange(repositories:{latest_commit_at?:string|null}[],now=Date.now()):{start:string;end:string}|null {
  const dates=repositories.map(r=>Date.parse(r.latest_commit_at||'')).filter(t=>Number.isFinite(t)&&t>=0&&t<=now);
  if(!dates.length)return null;
  const lastDay=new Date(Math.max(...dates)).toISOString().slice(0,10);
  const end=Date.parse(lastDay+'T00:00:00Z')+86400000;
  return {start:new Date(Math.max(0,end-366*86400000)).toISOString().slice(0,10),end:new Date(end).toISOString().slice(0,10)};
}

export function analysisUtcDayRange(start:string,end:string,now=Date.now()):{start_at:string;end_before:string} {
  const range=utcDayRange(start,end);
  if(Date.parse(range.end_before)>now){
    const tomorrow=new Date(Date.parse(new Date(now).toISOString().slice(0,10)+'T00:00:00Z')+86400000).toISOString().slice(0,10);
    if(end!==tomorrow)throw new Error('The analysis end cannot be in the future.');
    range.end_before=new Date(now).toISOString();
  }
  return range;
}

export function repositoryLinks(input:string):string[] {
  const values=input.trim().split(/\s+/).filter(Boolean);
  if(!values.length||values.length>8)throw new Error('Enter one to eight GitHub repository links.');
  const names=new Set<string>();
  return values.map(value=>{
    let url:URL;try{url=new URL(value);}catch{throw new Error('Use HTTPS GitHub links such as https://github.com/team/project.');}
    const parts=url.pathname.replace(/\/$/,'').split('/');const repo=parts[2]?.replace(/\.git$/,'');
    if(url.protocol!=='https:'||url.host!=='github.com'||url.username||url.password||url.search||url.hash||parts.length!==3||
      !/^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/.test(parts[1]||'')||!repo||!/^[A-Za-z0-9_.-]{1,100}$/.test(repo)||['.','..'].includes(repo))
      throw new Error('Use repository links without credentials, extra paths, query parameters or fragments.');
    const name=parts[1]+'/'+repo;if(names.has(name.toLowerCase()))throw new Error('Enter each repository only once.');
    names.add(name.toLowerCase());return 'https://github.com/'+name;
  });
}

export function parseAnalysisRoute(hash:string):AnalysisRoute {
  const q = new URLSearchParams(hash.startsWith('#analysis?') ? hash.slice(10) : '');
  const id=(key:string)=>{const v=q.get(key)||'';return /^[0-9a-f-]{36}$/.test(v)?v:'';};
  const person=q.get('person')||'';const outcome=q.get('outcome')||'';
  return {workspace:id('workspace'),project:id('project'),report:id('report'),...(id('publication')?{publication:id('publication')}:{}),
    person:/^(github:[1-9]\d{0,18}|(?:email|unknown):[a-f0-9]{64}|(?:manual|local):[a-f0-9-]{36})$/.test(person)?person:'',
    outcome:/^[a-f0-9]{64}$/.test(outcome)?outcome:''};
}
export function analysisHash(route:AnalysisRoute):string {
  const q=new URLSearchParams();for(const [k,v]of Object.entries(route))if(v)q.set(k,v);
  return '#analysis'+(q.size?'?'+q.toString():'');
}
export function filterAnalysis(dashboard:AnalysisDashboard, repository:string, person:string) {
  const outcomes=dashboard.outcomes.filter(o=>(!repository||o.repositories.includes(repository))&&(!person||o.contributors.some(p=>p.key===person)||o.proposal?.entries.some(p=>p.contributor_key===person)));
  const ids=new Set(outcomes.map(o=>o.id));
  return {outcomes,people:dashboard.contributors.filter(p=>(!person||p.key===person)&&(person&&!repository||p.outcome_ids.some(id=>ids.has(id)))),denominator:dashboard.proposed_denominator_atoms};
}
