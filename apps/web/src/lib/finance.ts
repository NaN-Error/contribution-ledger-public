/** Financial source records remain separate from credit, previews and external transfers. */
import { formatCents, parseMoney, type SimulationPolicy, type SimulationResult } from './simulator.js';
import type { PolicyRules } from './planning.js';
export const financeKinds = ['receipt','deduction','reserve_hold','reserve_release','adjustment_credit','adjustment_debit'] as const;
export type FinanceKind = typeof financeKinds[number];
export interface FinanceOptions {can_manage_finance:boolean;can_approve:boolean;viewer_id:string;notice:string;synthetic_only:true;policies:(SimulationPolicy&{rules:PolicyRules})[]}
export interface Preserved<T> {id:string;created_by:string;created_at:string;record_hash:string;record:T}
export interface PeriodSummary {id:string;month:string;timezone:string;state:'open'|'closed';close_id:string|null;created_at:string}
export interface PeriodRecord {month:string;timezone:string;start_inclusive:string;end_exclusive:string;source_policy_id:string;calculation_policy_id:string;agreement_reference:string;previous_period_id:string|null;accounting_rules:PolicyRules['accounting'];synthetic_only:true;deficit_rule:string;reason:string}
export interface DocumentRecord {title:string;provenance:string;filename:string;media_type:string;size_bytes:number;sha256:string;reason:string}
export type FinanceDocument=Preserved<DocumentRecord>;
export interface EntryData {document_id:string;kind:FinanceKind;amount_cents:number;source_name:string;statement_reference:string;line_reference:string;description:string;revenue_basis:string|null;already_deducted:string[];deduction_category:string|null;related_entry_id:string|null;separate_charge_confirmed:boolean}
export interface EntryDecision {action:'approve'|'reject'|'void';reason:string;previous_hash:string|null}
export interface FinancialEntry extends Preserved<{entry:EntryData;reason:string;document_hash:string}> {state:'pending'|'approve'|'reject'|'void';decision:Preserved<EntryDecision>|null;history:Preserved<EntryDecision>[]}
export interface Roster {award_ids:string[];denominator_atoms:number;recipients:{user_id:string;atoms:number}[];names:{user_id:string;display_name:string}[]}
export interface ReleaseRecord {version:number;initial_cutoff_exclusive:string;roster:Roster;roster_hash:string;predecessor_hash:string|null;synthetic_only:true}
export interface Cash {opening_reserve_cents:number;opening_deficit_cents:number;entries_by_kind_cents:Record<FinanceKind,number>;net_cents:number;distributable_cents:number;closing_reserve_cents:number;closing_deficit_cents:number;blockers:string[]}
export interface DistributionRecord {kind:'synthetic_distribution_close';synthetic_only:true;real_payment_authorized:false;period:Preserved<PeriodRecord>;cash:Cash;result:SimulationResult;release:{record:ReleaseRecord;proposed_initial_freeze:boolean};people:{user_id:string;display_name:string}[];blockers:string[];notice:string;coverage_notice:string;ledger_snapshot:{ledger_revision:string;pending_by_pool:Record<string,number>}}
export interface ReleaseCorrection {kind:'release_correction';before:ReleaseRecord;after:ReleaseRecord;blockers:string[];notice:string}
export type ReviewRecord=DistributionRecord|ReleaseCorrection;
export interface FinancePreview {record:ReviewRecord;preview_hash:string;captured_at:string;notice:string}
export interface FinanceProposal extends Preserved<{preview:ReviewRecord;preview_hash:string;reason:string}> {kind:'close'|'release_correction';state:'pending'|'approve'|'reject';decision:Preserved<{action:string;reason:string;close_id:string|null;release_snapshot_id:string|null}>|null}
export interface PeriodDetail extends Preserved<PeriodRecord> {state:'open'|'closed';month:string;close_id:string|null;entries:FinancialEntry[];documents:FinanceDocument[];proposals:FinanceProposal[];release_snapshot:Preserved<ReleaseRecord>|null;notice:string}
export interface ClosedDistribution extends Preserved<DistributionRecord> {reproduced:boolean;release_snapshot_id:string;period_id:string;notice:string}
export interface PaymentRecord {recipient_id:string;amount_cents:number;provider:string;external_reference:string;paid_at:string;reason:string;verification:string}
export interface PaymentView extends Preserved<PaymentRecord> {void:Preserved<{reason:string}>|null;status:string}
export interface PaymentBalance {user_id:string;display_name:string;distribution_cents:number;recorded_paid_cents:number;outstanding_cents:number;overpaid_cents:number;status:string}
export interface PaymentCollection {items:PaymentView[];balances:PaymentBalance[];notice:string}
export interface ContributorStatement {close_id:string;close_hash:string;month:string;closed_at:string;recipient:PaymentBalance;pool_explanations:unknown[];payments:PaymentView[];notice:string}
export function formatSignedCents(value:number):string {if(!Number.isSafeInteger(value))throw new Error('Use exact integer cents.');return (value<0?'−':'')+formatCents(Math.abs(value));}
export function positiveMoney(value:string):number {const amount=parseMoney(value);if(amount<=0)throw new Error('Enter a positive USD amount.');return amount;}
export function financeCommand(reason:string) {const text=reason.trim();if(text.length<8||text.length>500)throw new Error('Explain the reason using 8–500 characters.');return {request_id:crypto.randomUUID(),reason:text};}
export function requireReviewed(checked:boolean):true {if(checked!==true)throw new Error('Inspect the records and explicitly confirm the review.');return true;}
export function entryState(value:FinancialEntry['state']):string {return {pending:'Needs approval',approve:'Approved',reject:'Rejected',void:'Voided declaration'}[value];}
export function assertSyntheticClose(value:ClosedDistribution):ClosedDistribution {if(value.record?.kind!=='synthetic_distribution_close'||value.record.synthetic_only!==true||value.record.real_payment_authorized!==false||value.reproduced!==true)throw new Error('The response is not a reproduced synthetic distribution.');return value;}
export function financeDownloadPath(root:string,id:string,format:'json'|'csv'|'zip'):string {
 const uuid='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}';
 if(!new RegExp(`^/api/v1/workspaces/${uuid}/projects/${uuid}/finance$`).test(root)||!new RegExp(`^${uuid}$`).test(id)||!['json','csv','zip'].includes(format))throw new Error('Invalid scoped export path.');
 return `${root}/closes/${id}/export?format=${format}`;
}
export function parseDeducted(value:string):string[] {const values=value.split(',').map(s=>s.trim()).filter(Boolean);if(new Set(values).size!==values.length)throw new Error('Choose each already-deducted category only once.');return values;}

export function formatFinanceAtoms(value:number):string {
 if(!Number.isSafeInteger(value)||value<0)throw new Error('Invalid exact contribution total.');
 const atoms=BigInt(value);const fraction=String(atoms%1000n).padStart(3,'0').replace(/0+$/,'');
 return String(atoms/1000n).replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');
}
