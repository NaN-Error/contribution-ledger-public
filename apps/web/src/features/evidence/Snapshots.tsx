import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Loading } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import { humanLabel } from '../../lib/planning.js';
import type { EvidenceSnapshot, SnapshotSummary } from '../../lib/evidence.js';

export function SnapshotView({root,id,close,inspect}:{root:string;id:string;close:()=>void;inspect:(evidenceId:string,revision:number)=>void}) {
  const state=useResource<EvidenceSnapshot>(`${root}/snapshots/${id}`);
  return <section className="panel archive-panel"><div className="section-heading"><h3>Evidence snapshot</h3><button className="button" onClick={close}>Close snapshot</button></div>{state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
    <Badge tone={state.data.stale?'warning':'good'}>{state.data.stale?'Historical packet — current evidence or scope differs':'Matches the current evidence and scope'}</Badge>
    <p>Scope revision {state.data.scope_revision} · captured {new Date(state.data.created_at).toLocaleString()}</p><p className="small wrap">Fingerprint: <code>{state.data.content_hash}</code></p>
    <p>{state.data.document.notice}</p>{state.data.redacted && <p className="planning-warning">Some archived entries are restricted. This is a redacted view, not the full canonical document used to compute the fingerprint.</p>}
    <details className="form-details"><summary>Captured acceptance criteria</summary><h4>{state.data.document.scope.title}</h4><p className="preserve-text">{state.data.document.scope.outcome}</p><ul>{state.data.document.scope.acceptance_criteria.map(c=><li key={c}>{c}</li>)}</ul><p className="preserve-text">Required evidence: {state.data.document.scope.evidence_requirements}</p></details>
    <div className="evidence-snapshot-grid">{state.data.document.entries.map((entry,index)=>entry.restricted?<div className="evidence-snapshot-entry" key={`hidden-${index}`}><Badge>Restricted</Badge><p>An archived entry is not visible with your current access.</p></div>:<div className="evidence-snapshot-entry" key={entry.evidence_id}><h4>{entry.document.metadata.title}</h4><p>Evidence revision {entry.revision}</p><p>At capture: {humanLabel(entry.availability_at_capture)}</p><p>Current artifact status: {humanLabel(state.data!.current_artifact_states?.[entry.evidence_id] || 'not checked')}</p><button className="button" onClick={()=>inspect(entry.evidence_id,entry.revision)}>Inspect captured revision</button></div>)}</div>
    <h4>Omissions and limitations</h4>{state.data.document.omissions.length?<ul>{state.data.document.omissions.map((entry,index)=><li key={index}>{humanLabel(entry.status)}: {entry.reason}</li>)}</ul>:<p>No declared or detected omissions at capture. This does not establish that all required evidence was supplied.</p>}
    <p className="small muted">{state.data.historical_notice}</p></>}</section>;
}
export function SnapshotHistory({root,open}:{root:string;open:(id:string)=>void}) {
  const [offset,setOffset]=useState(0);const state=useResource<{items:SnapshotSummary[];next_offset:number|null}>(`${root}/snapshots?offset=${offset}`);
  return <section className="panel"><h3>Snapshot history</h3>{state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
    {!state.data.items.length && <p>No evidence packet has been captured yet.</p>}{state.data.items.map(s=><div className="work-history" key={s.id}><div><strong>Scope revision {s.scope_revision}</strong><small>{new Date(s.created_at).toLocaleString()}</small><code className="small wrap">{s.content_hash}</code></div><button className="button" onClick={()=>open(s.id)}>Inspect snapshot</button></div>)}
    <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer snapshots</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>state.data?.next_offset!==null && setOffset(state.data!.next_offset!)}>Older snapshots</button></div></>}</section>;
}
