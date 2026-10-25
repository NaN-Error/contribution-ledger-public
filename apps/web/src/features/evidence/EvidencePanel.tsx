import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback, Loading } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { reviewStateLabel, type EvidenceCollection, type EvidenceRecord } from '../../lib/evidence.js';
import type { WorkPackageDetail } from '../../lib/workPackages.js';
import { EvidenceEditor } from './EvidenceEditor.js';
import { ArchivedEvidence, EvidenceView, RetireArtifact, RevisionHistory } from './EvidenceView.js';
import { SnapshotHistory, SnapshotView } from './Snapshots.js';

export function EvidencePanel({packagePath,packageRecord,refreshPackage}:{packagePath:string;packageRecord:WorkPackageDetail;refreshPackage:()=>void}) {
  const root=`${packagePath}/evidence`;const [offset,setOffset]=useState(0);const state=useResource<EvidenceCollection>(`${root}?offset=${offset}`);
  const [editing,setEditing]=useState<EvidenceRecord | 'new' | null>(null);const [history,setHistory]=useState<string|null>(null);
  const [snapshot,setSnapshot]=useState<string|null>(null);const [showHistory,setShowHistory]=useState(false);
  const [archive,setArchive]=useState<{id:string;revision:number}|null>(null);const action=useAction();
  const inspect=(id:string,revision:number)=>setArchive({id,revision});
  if(state.loading || state.error || !state.data)return <section className="panel"><h3>Contribution evidence</h3><Loading error={state.error} refresh={state.refresh}/></section>;
  const data=state.data;
  const stalePackage=data.package_version!==packageRecord.version;
  return <section className="evidence-section" aria-label="Contribution evidence"><div className="section-heading"><div><p className="eyebrow">Claims, sources and artifacts</p><h3>Contribution evidence</h3><p>{data.total_entries} entries · {data.restricted_entries} restricted from this view</p></div>
    <div className="button-row"><button className="button" onClick={refreshPackage}>Refresh evidence and package</button>{data.can_add && !stalePackage && <button className="button primary" onClick={()=>setEditing('new')}>Add evidence</button>}</div></div>
    <Badge tone={data.review_state==='stale' || data.review_state==='legacy_without_evidence'?'warning':'muted'}>{reviewStateLabel(data.review_state)}</Badge>
    {(data.review_state==='stale' || data.review_state==='legacy_without_evidence') && <p className="planning-warning">The last submission is not tied to the current evidence packet. A coordinator or administrator must review the changes and use “Resubmit with current evidence”. Earlier submissions remain unchanged.</p>}
    {stalePackage && <p className="planning-warning">This package changed in another request. Refresh before adding evidence, capturing a packet or changing its state.</p>}
    <p className="small muted">Evidence supports human review. It does not establish objective contribution value, verify every author claim, or award units.</p>
    {editing && data.can_add && !stalePackage && <EvidenceEditor key={editing==='new'?'new':editing.evidence_id+editing.number} root={root} packageRecord={packageRecord} initial={editing==='new'?undefined:editing} saved={refreshPackage} cancel={()=>setEditing(null)}/>}
    <Feedback error={action.error}/>
    {!data.items.length && <div className="panel empty-panel"><h4>{data.total_entries?'No evidence visible on this page':'No evidence supplied yet'}</h4><p>Add a contributor statement, a source link, an artifact, or an explicit missing-evidence entry. Non-code work does not need a GitHub commit.</p></div>}
    <div className="evidence-list">{data.items.map(record=><section className="panel" key={record.evidence_id+record.number}><EvidenceView root={root} record={record}/><div className="button-row">
      {record.can_edit && data.can_add && !stalePackage && <button className="button" onClick={()=>setEditing(record)}>Add a revision</button>}
      <button className="button" onClick={()=>setHistory(history===record.evidence_id?null:record.evidence_id)}>{history===record.evidence_id?'Hide revision history':'View revision history'}</button></div>
      {history===record.evidence_id && <RevisionHistory root={root} record={record} inspect={number=>inspect(record.evidence_id,number)}/>}
      {data.can_retire && !stalePackage && <RetireArtifact root={root} record={record} packageVersion={packageRecord.version} onDone={refreshPackage}/>}</section>)}</div>
    <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Previous evidence</button><button className="button" disabled={data.next_offset===null} onClick={()=>data.next_offset!==null && setOffset(data.next_offset)}>Next evidence</button></div>
    <section className="panel"><h3>Review packet</h3><p>Every evidence revision automatically preserves a new content-addressed packet. Submitting work captures the exact current scope and evidence, including omissions.</p>
      <div className="button-row">{data.current_snapshot_id && <button className="button" onClick={()=>setSnapshot(data.current_snapshot_id)}>Inspect current packet</button>}
      {data.can_snapshot && !stalePackage && <button className="button" disabled={action.pending} onClick={()=>void action.run(()=>api<{id:string}>(`${root}/snapshots`,'POST',{
        expected_package_version:packageRecord.version,reviewed_hash:packageRecord.review_hash,reviewed:true,
        reason:'Capture the current scope, evidence references and explicit omissions for review.'}),result=>{setSnapshot(result.id);state.refresh();})}>Capture current packet</button>}
      <button className="button" onClick={()=>setShowHistory(!showHistory)}>{showHistory?'Hide snapshot history':'View snapshot history'}</button></div><p className="small muted">{data.retention_notice}</p></section>
    {showHistory && <SnapshotHistory key={data.current_content_hash} root={root} open={setSnapshot}/>}
    {snapshot && <SnapshotView key={snapshot} root={root} id={snapshot} close={()=>setSnapshot(null)} inspect={inspect}/>}
    {archive && <ArchivedEvidence key={archive.id+archive.revision} root={root} evidenceId={archive.id} revision={archive.revision} close={()=>setArchive(null)} canRetire={data.can_retire && !stalePackage} packageVersion={packageRecord.version} onRetired={refreshPackage}/>}
  </section>;
}
