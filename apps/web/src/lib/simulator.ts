/** Exact input/display helpers. The server is the authoritative calculator. */
import { formatShare } from './reviews.js';
export const maxCents = 1_000_000_000_000;
export interface SimulationInput { source_policy_id:string; calculation_policy_id:string; month:string; amount_cents:number }
export interface SimulationPolicy { id:string; version:number; title:string; state:string; content_hash:string;
  ready_for_pinned_work:boolean; rules:{timezone:string; pools:{key:string;weight_bps:number}[]} }
export interface SimulationOptions {policies:SimulationPolicy[]; can_save:boolean; notice:string}
export interface RoundedLine {key:string;weight:number;denominator:number;floor_cents:number;remainder_numerator:number;rounding_cent:number;amount_cents:number}
export interface PoolResult {key:string;weight_bps:number;pool_rounding:RoundedLine;denominator_atoms:number;amount_cents:number;
  status:'blocked'|'calculated';blockers:string[];unallocated_cents:number;allocations:RoundedLine[]}
export interface SimulationResult { engine_version:string;currency:'USD';hypothetical:true;payable:false;amount_cents:number;
  pools:PoolResult[];people:{user_id:string;amount_cents:number}[];allocated_cents:number;unallocated_cents:number;status:'blocked'|'calculated' }
export interface SimulationRecord {kind:'hypothetical_simulation';payable:false;notice:string;input:SimulationInput;captured_at:string;
  snapshot_hash:string;result_hash:string;result:SimulationResult;
  snapshot:{source_policy:SimulationPolicy;calculation_policy:SimulationPolicy;
    period:{month:string;timezone:string;start_inclusive:string;end_exclusive:string};ledger_revision:string;
    source_award_count:number;source_event_count:number;excluded_source_award_count:number;excluded_other_policy_award_count:number;
    pending_planned_atoms:number;pending_by_pool:Record<string,number>;warnings:string[];
    pool_dispute_ids:Record<string,string[]>;people:{user_id:string;display_name:string}[];
    eligible_awards:{award_id:string;package_id:string;pool_key:string;milestone_id:string;accepted_at:string;budget_atoms:number;
      current_attributions:{user_id:string;role:string;atoms:number}[];open_dispute_ids:string[]}[];
    planning:{milestone_id:string;name:string;version:number;total_atoms:number;planned_atoms:number;issued_atoms:number;
      pending_planned_atoms:number;protected_reserve_atoms:number;available_to_plan_atoms:number}[];
  };
}
export interface SavedScenario {id:string;title:string;created_by:string;created_at:string;record_hash:string;record:SimulationRecord;reproduced:boolean;notice:string}
export interface ScenarioSummary {id:string;title:string;created_at:string;month:string;amount_cents:number;status:string;payable:false}

export function parseMoney(value:string):number {
  const trimmed=value.trim();
  if(!/^\d{1,11}(?:\.\d{1,2})?$/.test(trimmed))throw new Error('Enter a nonnegative USD amount with up to two decimal places, without commas or a currency symbol.');
  const [whole,fraction='']=trimmed.split('.');const cents=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
  if(cents>BigInt(maxCents))throw new Error('This local simulator supports up to $10,000,000,000.00.');
  return Number(cents);
}
export function formatCents(value:number):string {
  if(!Number.isSafeInteger(value)||value<0||value>maxCents)throw new Error('Invalid exact USD amount.');
  const cents=BigInt(value);
  return '$'+String(cents/100n).replace(/\B(?=(\d{3})+(?!\d))/g,',')+'.'+String(cents%100n).padStart(2,'0');
}
export function moneyInput(value:number):string {formatCents(value);return `${BigInt(value)/100n}.${String(BigInt(value)%100n).padStart(2,'0')}`;}
export function poolWeight(bps:number):string {return formatShare(bps,10000);}
export function validateMonth(value:string):string {
  if(!/^(?:[2-9]\d{3})-(?:0[1-9]|1[0-2])$/.test(value)||Number(value.slice(0,4))>9998)throw new Error('Choose a calendar month from 2000 through 9998.');
  return value;
}
export function monthInTimezone(zone:string,instant=new Date()):string {
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:zone,year:'numeric',month:'2-digit'}).formatToParts(instant);
  return `${parts.find(p=>p.type==='year')!.value}-${parts.find(p=>p.type==='month')!.value}`;
}
const uuid='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const scenarioPattern=new RegExp(`^#scenario/(${uuid})/(${uuid})/(${uuid})$`);
export function parseScenarioHash(value:string):{workspaceId:string;projectId:string;scenarioId:string}|null {
  const m=scenarioPattern.exec(value);return m?{workspaceId:m[1],projectId:m[2],scenarioId:m[3]}:null;
}
export function scenarioHash(workspaceId:string,projectId:string,scenarioId:string):string {
  const value=`#scenario/${workspaceId}/${projectId}/${scenarioId}`;
  if(!parseScenarioHash(value))throw new Error('Invalid scoped scenario identifiers.');
  return value;
}
export function assertNonPayable(record:SimulationRecord):SimulationRecord {
  if(record.kind!=='hypothetical_simulation'||record.payable!==false||record.result?.payable!==false||record.result?.hypothetical!==true)
    throw new Error('The server did not return a non-payable hypothetical example.');
  return record;
}
