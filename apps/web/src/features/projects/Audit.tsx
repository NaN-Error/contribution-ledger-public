import { useState } from 'react';
import { Loading } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import { formatDate } from '../../lib/status.js';
import type { AuditItem, Items } from '../../lib/accounts.js';

export function Audit({ workspaceId }: { workspaceId: string }) {
  const [offset, setOffset] = useState(0);
  const state = useResource<Items<AuditItem>>(`/api/v1/workspaces/${workspaceId}/audit?offset=${offset}`);
  return <section className="panel"><div className="section-heading"><h2>Access and project history</h2><button className="button" onClick={state.refresh}>Refresh history</button></div>
    <p>These records cannot be edited through the application. Operator-only account events are retained separately from workspace history.</p>
    {state.loading || state.error ? <Loading error={state.error} refresh={state.refresh} /> : <>{!state.data?.items.length && <p>No events yet.</p>}
      {state.data?.items.map(row => <details className="audit-row" key={row.id}><summary><span>{row.action.replaceAll('.', ' · ').replaceAll('_', ' ')}</span><small>{formatDate(row.created_at)}</small></summary>
        <p>{row.reason || 'Recorded application action.'}</p><p className="small wrap">Actor: {row.actor_id ?? 'Local operator'}<br />Subject: {row.subject_id ?? 'Workspace or installation'}<br />Project: {row.project_id ?? 'Workspace-wide'}</p>
        <pre>{JSON.stringify(row.details, null, 2)}</pre></details>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 50))}>Previous</button><button className="button" disabled={state.data?.next_offset == null} onClick={() => setOffset(state.data?.next_offset ?? offset)}>Next</button></div></>}
  </section>;
}
