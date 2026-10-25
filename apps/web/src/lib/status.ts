export interface SystemStatus {
  status: 'ready' | 'degraded';
  api: 'ok';
  environment: string;
  version: string;
  phase: number;
  checked_at: string;
  database: { status: 'ok' | 'unavailable'; message: string };
  migrations: { status: 'current' | 'pending' | 'unavailable'; current_revision: string | null; expected_revision: string };
  persistence: { status: 'present' | 'empty' | 'unavailable'; marker_id: string | null; created_at: string | null };
  development_tools_enabled: boolean;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

export function isSystemStatus(value: unknown): value is SystemStatus {
  if (!record(value)) return false;
  const { database, migrations, persistence } = value;
  return (value.status === 'ready' || value.status === 'degraded') && value.api === 'ok'
    && typeof value.environment === 'string' && typeof value.version === 'string'
    && Number.isInteger(value.phase) && (value.phase as number) > 0 && typeof value.checked_at === 'string'
    && Number.isFinite(Date.parse(value.checked_at))
    && typeof value.development_tools_enabled === 'boolean'
    && record(database) && (database.status === 'ok' || database.status === 'unavailable')
    && typeof database.message === 'string'
    && record(migrations) && (migrations.status === 'current' || migrations.status === 'pending' || migrations.status === 'unavailable')
    && nullableString(migrations.current_revision) && typeof migrations.expected_revision === 'string'
    && record(persistence) && (persistence.status === 'present' || persistence.status === 'empty' || persistence.status === 'unavailable')
    && nullableString(persistence.marker_id) && nullableString(persistence.created_at)
    && (persistence.status !== 'present' || (typeof persistence.marker_id === 'string'
      && typeof persistence.created_at === 'string' && Number.isFinite(Date.parse(persistence.created_at))))
    && (value.status !== 'ready' || (database.status === 'ok' && migrations.status === 'current'));
}

export type Page = 'overview' | 'setup' | 'roadmap';
export function pageFromHash(hash: string): Page {
  const page = hash.replace(/^#\/?/, '');
  return page === 'setup' || page === 'roadmap' ? page : 'overview';
}

export function formatDate(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Not available';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value));
}

export class ApiFailure extends Error {
  constructor(message: string, public readonly requestId: string | null = null) {
    super(message);
    this.name = 'ApiFailure';
  }
}

export async function fetchStatus(signal: AbortSignal, fetcher: typeof fetch = fetch): Promise<SystemStatus> {
  const response = await fetcher('/api/v1/system/status', { signal, cache: 'no-store', headers: { Accept: 'application/json' } });
  const requestId = response.headers.get('X-Request-ID');
  if (response.status !== 200 && response.status !== 503) {
    throw new ApiFailure('The API could not complete the status check.', requestId);
  }
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new ApiFailure('The API returned an unreadable response.', requestId); }
  if (!isSystemStatus(value)) throw new ApiFailure('The API returned an unexpected response.', requestId);
  if ((response.status === 200) !== (value.status === 'ready')) {
    throw new ApiFailure('The API returned inconsistent readiness information.', requestId);
  }
  return value;
}
