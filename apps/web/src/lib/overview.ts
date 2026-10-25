import type { Fraction } from './reconstruction.js';
export interface OverviewPerson {user_id:string;display_name:string;atoms:number;share:Fraction;roles:Record<string,number>;award_ids:string[]}
export interface OverviewGroup {policy_id:string;policy_version:number;pool_key:string;denominator_atoms:number;people:OverviewPerson[];by_category:Record<string,number>;by_origin:Record<string,number>;disputed_atoms:number;accepted_deliverable_count:number;evidence_snapshot_count:number}
export interface OverviewReport {groups:OverviewGroup[];snapshot_hash:string;captured_at:string;my_user_id:string;pending_planned_atoms:number;filters:Record<string,string|null>;denominator_label:string;evidence_notice:string;notice:string;activity:null|{available:boolean;reason?:string;scope?:string;unique_observed_entities?:Record<string,number>;retained_version_count?:number;notice?:string}}
export function overviewPath(root:string,filters:Record<string,string>):string{
  const allowed=new Set(['policy_id','pool_key','category','origin','person_id']);const q=new URLSearchParams();
  for(const [key,value]of Object.entries(filters).sort(([a],[b])=>a.localeCompare(b))){if(!allowed.has(key))throw new Error('Unsupported report filter.');if(value)q.set(key,value);}
  return root+'/reports/overview'+(q.size?'?'+q.toString():'');
}
