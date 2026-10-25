/** Read-only source integration types. Neither an activity count nor a mapping is credit. */
export interface RepositoryOption { github_id:number; full_name:string; private:boolean; default_branch:string }
export interface GitHubRepository extends RepositoryOption { id:string; connection_id:string; enabled:boolean; version:number; retry_not_before?:string|null }
export interface GitHubConnection { id:string; installation_id:number; account:string; github_login:string; enabled:boolean; version:number; verified_at:string; verified_until:string; last_error:string|null }
export interface GitHubOverview { configured:boolean; can_manage:boolean; api_version:string; permissions:Record<string,string>; connections:GitHubConnection[]; repositories:GitHubRepository[]; source_version_counts:Record<string,number>; notice:string; metric_notice:string; worker_notice:string }
export interface GitHubProof { flow_id:string; workspace_id:string; project_id:string; proof_hash:string; expires_at:string; github_login:string; account:string; installation_id:number; repositories:RepositoryOption[]; notice:string }
export interface GitHubCallback { code:string; state:string; error:string|null }
export interface ImportJob { id:string; repository_id:string; state:string; version:number; start_at:string; end_before:string; requested_as_of:string; anchor_sha:string|null; request_limit:number; entity_limit:number; data_requests:number; failures:number; stats:Record<string,number>; omissions:string[]; next_attempt_at:string; error_code:string|null; created_at:string; finished_at:string|null; tasks:Record<string,number>; notice:string; scope:string }
export interface SourceIdentity { external_key:string; kind:string; label:string; role:string; assertion:string }
export interface SourceDocument { schema_version:number; kind:string; remote_key:string; repository:{github_id:number;full_name:string}; content:Record<string,unknown>; identities:SourceIdentity[]; omissions:string[]; notice:string }
export interface SourceVersion { id:string; repository_id:string; kind:string; remote_key:string; content_hash:string; size_bytes:number; captured_at:string; title:string; omission_count:number; document?:SourceDocument; other_preserved_versions?:number }
export interface IdentityRow { id:string; external_key:string; kind:string; label:string; linked_user_id:string|null; version:number }
export interface GitHubPage<T> { items:T[]; next_offset:number|null; notice?:string }
export interface IdentityPage extends GitHubPage<IdentityRow> { people:{user_id:string;display_name:string;role:string}[]; can_manage:boolean }

export function githubCallback(urlString:string):GitHubCallback|null {
  const url=new URL(urlString);
  if(url.pathname!=='/github/callback')return null;
  const params=url.searchParams;
  if(params.has('error'))return {code:'',state:'',error:'GitHub authorization was declined or did not finish. Start a new connection from the project.'};
  if(params.getAll('state').length!==1 || params.getAll('code').length!==1 ||
     !/^[A-Za-z0-9_-]{43}$/.test(params.get('state') || '') || !/^[A-Za-z0-9_-]{10,200}$/.test(params.get('code') || '')) {
    return {code:'',state:'',error:'This callback is incomplete or invalid. Start a new authorization flow.'};
  }
  return {code:params.get('code')!,state:params.get('state')!,error:null};
}
export function authorizationURL(value:string):string {
  const url=new URL(value);
  if(url.origin!=='https://github.com' || url.pathname!=='/login/oauth/authorize' || url.username || url.password || url.hash ||
     !/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('state') || '') || url.searchParams.get('code_challenge_method')!=='S256') {
    throw new Error('The API returned an invalid GitHub authorization address.');
  }
  return url.toString();
}
export function installationID(value:string):number {
  if(!/^[1-9]\d{0,15}$/.test(value))throw new Error('Enter the positive numeric installation ID from the GitHub App installation settings.');
  const result=Number(value);
  if(!Number.isSafeInteger(result))throw new Error('This installation ID exceeds the supported exact integer range.');
  return result;
}
export function utcDayRange(start:string,end:string):{start_at:string;end_before:string} {
  const valid=(s:string)=>/^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s+'T00:00:00Z')) && new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
  if(!valid(start)||!valid(end))throw new Error('Enter two complete calendar dates.');
  const difference=Date.parse(end+'T00:00:00Z')-Date.parse(start+'T00:00:00Z');
  if(difference<=0||difference>366*86400000)throw new Error('Choose an increasing UTC range no longer than 366 days. The end date is excluded.');
  return {start_at:start+'T00:00:00Z',end_before:end+'T00:00:00Z'};
}
export function isProof(value:unknown):value is GitHubProof {
  if(!value||typeof value!=='object')return false;
  const p=value as Partial<GitHubProof>;
  return typeof p.flow_id==='string' && /^[0-9a-f-]{36}$/.test(p.flow_id) && typeof p.proof_hash==='string' && /^[0-9a-f]{64}$/.test(p.proof_hash)
    && typeof p.expires_at==='string' && Number.isFinite(Date.parse(p.expires_at)) && Array.isArray(p.repositories)
    && p.repositories.length>0 && p.repositories.every(r=>Number.isSafeInteger(r.github_id)&&r.github_id>0&&typeof r.full_name==='string'&&typeof r.private==='boolean');
}
export function selectedRepositories(proof:GitHubProof,selected:number[]):number[] {
  if(!selected.length||selected.length>20||new Set(selected).size!==selected.length||selected.some(id=>!proof.repositories.some(r=>r.github_id===id)))
    throw new Error('Select 1–20 distinct repositories from the verified list.');
  return [...selected].sort((a,b)=>a-b);
}
export function importTerminal(state:string):boolean {return ['failed','cancelled','completed','completed_incomplete'].includes(state);}
export function sourceLabel(source:SourceVersion):string{return `${source.kind.replaceAll('_',' ')} · ${source.remote_key} · ${source.title}`;}
