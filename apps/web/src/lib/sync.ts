import type { ImportJob } from './github.js';
export interface SyncConfiguration {
  id:string;repository_id:string;configured_by:string;enabled:boolean;version:number;
  interval_minutes:number;lookback_days:number;request_limit:number;entity_limit:number;
  next_due_at:string;active_import_id:string|null;last_started_at:string|null;
  last_finished_at:string|null;last_success_at:string|null;last_complete_at:string|null;
  last_error:string|null;updated_at:string;
}
export interface SyncOverview {
  can_manage:boolean;sync_configured:boolean;webhook_configured:boolean;
  configurations:SyncConfiguration[];delivery_counts:Record<string,number>;job_counts:Record<string,number>;
  linked_sources_with_new_observations:number;
  heartbeat:{component:string;last_seen_at:string;status:string;stale:boolean}[];notice:string;
}
export interface SyncJob extends ImportJob {
  capture_mode:'historical'|'sync';dead_letter:boolean;worker_lease_until:string|null;
  dispatch:{publish_attempts:number;last_published_at:string|null;next_dispatch_at:string|null;publish_error:string|null;lease_until:string|null}|null;
}
export interface Delivery {
  id:string;repository_id:string;delivery_id:string;event:string;action:string;received_at:string;
  state:string;note:string;import_id:string|null;payload_hash:string;target_count:number;
}
export interface Observation {
  id:string;repository_id:string;kind:string;remote_key:string;source_id:string|null;
  state:string;observed_at:string;remote_updated_at:string|null;import_id:string;
}
export function boundedInteger(value:string,min:number,max:number,label:string):number {
  if(!/^\d+$/.test(value))throw new Error(`${label} must be a whole number.`);
  const n=Number(value);
  if(!Number.isSafeInteger(n)||n<min||n>max)throw new Error(`${label} must be between ${min} and ${max}.`);
  return n;
}
export function syncPayload(version:number,enabled:boolean,fields:{interval:string;lookback:string;requests:string;entities:string},reason:string,reviewed:boolean) {
  if(!Number.isSafeInteger(version)||version<0)throw new Error('Refresh the synchronization settings.');
  if(!reviewed)throw new Error('Review and confirm the synchronization scope.');
  const explanation=reason.trim();if(explanation.length<8||explanation.length>500)throw new Error('Enter a reason between 8 and 500 characters.');
  return {expected_version:version,enabled,interval_minutes:boundedInteger(fields.interval,60,10080,'Interval'),
    lookback_days:boundedInteger(fields.lookback,1,90,'Lookback'),request_limit:boundedInteger(fields.requests,10,1000,'Data-request budget'),
    entity_limit:boundedInteger(fields.entities,1,200,'Root limit'),reason:explanation,reviewed:true};
}
export function displayInstant(value:string|null):string {
  if(!value)return 'Not recorded';const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString():'Invalid recorded time';
}
export function retryReady(value:string,clock=Date.now()):boolean {
  const t=Date.parse(value);return Number.isFinite(t)&&Number.isFinite(clock)&&t<=clock;
}
export function summaryCounts(value:Record<string,number>):string {
  return Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ')||'No recorded activity';
}

/** Match the existing strict ImportAction schema; no invented reviewed flag. */
export function jobActionPayload(version:number,reason:string) {
  if(!Number.isSafeInteger(version)||version<1||version>2147483647)throw new Error('Refresh the job before acting.');
  const explanation=reason.trim();
  if(explanation.length<8||explanation.length>500||/[\u0000-\u0008\u000b-\u001f]/.test(explanation))throw new Error('Enter an explanation of 8–500 printable characters.');
  return {expected_version:version,reason:explanation};
}
