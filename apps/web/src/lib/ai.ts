export interface AIConnection {
  id: string; owner_id: string; provider: string; label: string; permission_reference: string;
  enabled: boolean; version: number; generation: number; can_manage: boolean;
  allow_project_use: boolean; monthly_limit_microusd: number; next_refresh_at: string;
  last_catalog_at: string | null; last_error: string | null; retry_not_before: string | null;
  credential_state: string;
}
export interface AIOverview {
  connections: AIConnection[]; can_create: boolean; can_approve: boolean;
  active_profile_id: string | null; live_enabled: boolean; paid_probes_enabled: boolean;
  providers: string[]; notice: string; budget_notice: string;
}
export interface AIModel {
  id: string; remote_id: string; fingerprint: string; generation: number; available: boolean;
  probe_state: string; probe_at: string | null; probe_job_id: string | null;
  document: {name: string; input_limit: number | null; output_limit: number | null;
    text_generation: boolean | null; structured_output: boolean | null};
}
export interface AIQuote {
  quote_hash: string; synthetic_prompt: string; notice: string;
  specification: {reservation_microusd: number; month: string; remote_id: string;
    max_output_tokens: number; input_token_allowance: number; price_valid_until: string};
}
export interface AIPrice {
  id: string; model_id: string; input_rate: number; output_rate: number;
  source_reference: string; valid_until: string; reason: string;
}
export interface AIJob {
  id: string; kind: string; status: string; accounting_state: string; attempts: number;
  reserved_microusd: number; accounted_microusd: number | null; last_error: string | null;
  created_at: string; not_before: string; result: Record<string, unknown> | null;
}
export interface AIProfile {
  id: string; version: number; fingerprint: string; approved: boolean;
  definition: {title: string; provider: string; requested_model: string; data_policy_reference: string;
    prompt_version?: string; schema_version?: string; rubric_version?: string;
    credential_generation: number; adapter_version: string; settings: Record<string, unknown>;
    notice: string; reason: string};
}
export interface Page<T> {items: T[]; next_offset: number | null}
export function parseMicroUSD(value: string, max=1_000_000_000): number {
  if (!/^\d{1,7}(?:\.\d{1,6})?$/.test(value)) throw new Error('Use a nonnegative USD amount with up to six decimal places.');
  const [whole, frac=''] = value.split('.');
  const result = BigInt(whole)*1_000_000n + BigInt(frac.padEnd(6,'0'));
  if (result>BigInt(max)) throw new Error('This amount exceeds the allowed limit.');
  return Number(result);
}
export function formatMicroUSD(value: number | null): string {
  if (value === null) return 'Unknown';
  if (!Number.isSafeInteger(value) || value < 0) return 'Invalid amount';
  const n=BigInt(value);return `$${n/1_000_000n}.${String(n%1_000_000n).padStart(6,'0')}`;
}
export function selectableModel(m: AIModel, connection: AIConnection): boolean {
  return connection.enabled && m.available && m.generation===connection.generation
    && m.document.text_generation!==false && m.document.structured_output!==false;
}
export function probeRequest(quote: AIQuote, requestId: string) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(requestId) || !/^[0-9a-f]{64}$/.test(quote.quote_hash)) throw new Error('Refresh the probe quotation.');
  return {request_id:requestId,quote_hash:quote.quote_hash,
    confirmed_reservation_microusd:quote.specification.reservation_microusd,payer_approved:true};
}
export function modelStatus(m: AIModel, connection: AIConnection): string {
  if (!m.available) return 'Not in the last complete catalog';
  if (m.generation!==connection.generation) return 'Credential or sharing settings changed; refresh required';
  if (!selectableModel(m,connection)) return 'Incompatible or connection revoked';
  return m.probe_state==='passed' ? 'Synthetic JSON probe passed — quality not evaluated' : m.probe_state==='failed' ? 'Probe failed — inspect the job' : 'Discovered; compatibility not verified';
}
