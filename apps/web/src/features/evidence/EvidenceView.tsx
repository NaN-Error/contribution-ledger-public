import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback, Loading, Submit, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { evidenceRevisionPath, formatBytes, safeSourceURL, type EvidenceRecord } from '../../lib/evidence.js';
import { PreservedGitHubSource } from '../github/GitHubSources.js';
import { humanLabel } from '../../lib/planning.js';
import type { AnalysisOutcome } from '../../lib/analysis.js';
import { SourceTiming } from '../analysis/SourceTiming.js';

function PreservedAnalysis({path}:{path:string}) {
  const state=useResource<{document:{outcome:AnalysisOutcome;work_window:{start_at:string;end_before:string};identity_resolutions:{external_key:string;disposition:string;user_id:string|null;reason:string}[]};content_hash:string}>(path);
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  const d=state.data.document;
  return <><h4>Preserved dashboard review: {d.outcome.title}</h4><p>{d.outcome.summary}</p><p className="small">Work window: {d.work_window.start_at} through {d.work_window.end_before} (end excluded). This review remains fixed when dashboard drafts or evidence explanations change.</p>
    {d.outcome.findings?.map(f=><p key={f.label}><strong>{f.label}:</strong> {f.text}</p>)}
    <ul>{d.outcome.limitations.map(l=><li key={l}>{l}</li>)}</ul>
    {d.outcome.sources.map(s=><details key={s.id}><summary>{s.kind} · {s.title}</summary><SourceTiming source={s}/><pre>{s.excerpt||'No captured text excerpt.'}</pre>{s.url&&<SourceLink value={s.url}/>}<p className="small">{s.omissions.join('; ')}</p></details>)}
    <details><summary>Preserved identities, scope and review provenance</summary><pre className="evidence-text">{JSON.stringify(d,null,2)}</pre><p className="small wrap">Fingerprint: {state.data.content_hash}</p></details></>;
}

function PinnedAnalysis({path}:{path:string}) {
  const [open,setOpen]=useState(false);
  return <details className="form-details" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Inspect pinned dashboard review</summary>{open&&<PreservedAnalysis path={path}/>}</details>;
}

function TextPreview({ path }: { path: string }) {
  const state=useResource<{text:string;truncated:boolean;notice?:string}>(path);
  if(state.loading || state.error || !state.data) return <Loading error={state.error} refresh={state.refresh}/>;
  return <><pre className="evidence-text">{state.data.text}</pre>{state.data.truncated && <p className="planning-warning">Preview truncated at 20,000 characters. The protected original download contains the full artifact.</p>}<p className="small muted">{state.data.notice || 'Plain text: never rendered as HTML or Markdown.'}</p></>;
}
function ImagePreview({ path }: { path:string }) {
  const [failed,setFailed]=useState(false);
  return failed ? <p className="error-panel" role="alert">The protected preview is unavailable. Refresh your session or check the evidence status.</p> : <figure className="evidence-image"><img src={path} alt="Contributor-supplied evidence preview" onError={()=>setFailed(true)} /><figcaption>Regenerated preview. Inspect the original only when needed.</figcaption></figure>;
}
export function SourceLink({ value }:{value:string}) {
  try { const href=safeSourceURL(value);return <a href={href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="source-link">Open external source (not verified)</a>; }
  catch { return <p>External URL unavailable.</p>; }
}
export function EvidenceView({root,record}:{root:string;record:EvidenceRecord}) {
  const [preview,setPreview]=useState(false);const doc=record.document;const meta=doc.metadata;
  const path=evidenceRevisionPath(root,record.evidence_id,record.number);const ready=record.availability==='available';
  return <div className="evidence-entry"><div className="section-heading"><div><h4>{meta.title}</h4><p className="small">Revision {record.number} · {humanLabel(doc.kind)} · {humanLabel(meta.category)}</p></div><Badge tone={ready?'good':'warning'}>{humanLabel(record.availability)}</Badge></div>
    <p className="preserve-text">{meta.description}</p><dl className="evidence-facts"><div><dt>Claimed authors</dt><dd>{meta.claimed_authors}</dd></div><div><dt>Claimed work date</dt><dd>{meta.occurred_on}</dd></div><div><dt>Visibility</dt><dd>{humanLabel(meta.visibility)}</dd></div></dl>
    <p className="small preserve-text"><strong>Provenance:</strong> {meta.provenance}</p><p className="small muted">{record.claims_notice}</p>
    {meta.omission_reason && <p className="planning-warning preserve-text">{meta.omission_reason}</p>}
    {record.historical && <p className="planning-warning">Archived revision. Its metadata and content have not been replaced by newer versions.</p>}
    {doc.text && <pre className="evidence-text">{doc.text}</pre>}
    {doc.external_source?.provider==='github' && <details className="form-details"><summary>Inspect pinned GitHub source</summary><p className="small">The editable statement above is a contributor explanation. This source remains pinned to the imported version and the mapping reviewed when it was attached.</p><PreservedGitHubSource path={`${path}/github-source`}/></details>}
    {doc.external_source?.provider==='repository_analysis' && <PinnedAnalysis path={`${path}/analysis-source`}/>}
    {doc.source_url && <SourceLink value={doc.source_url} />}
    {doc.file && <><p><strong>{doc.file.filename}</strong> · {formatBytes(doc.file.size_bytes)} · {doc.file.media_type}</p>
      <p className="small wrap">SHA-256: <code>{doc.file.sha256}</code></p>
      {ready && <div className="button-row"><button className="button" onClick={()=>setPreview(!preview)}>{preview?'Hide preview':'Open protected preview'}</button>
        <a className="button" href={`${path}/download`} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" download>Download original</a></div>}
      {preview && ready && (doc.file.media_type.startsWith('image/')?<ImagePreview key={path} path={`${path}/image`}/>:<TextPreview path={`${path}/preview`}/>)}
      <p className="small muted">Original downloads are not malware-scanned and may contain identifying metadata. Access is checked on every request.</p></>}
    <details className="form-details"><summary>Revision information</summary><p className="small preserve-text">{record.reason}</p><p className="small wrap">Submitted by account {record.created_by} · {new Date(record.created_at).toLocaleString()}</p><p className="small wrap">Content fingerprint: <code>{record.content_hash}</code></p></details>
  </div>;
}
export function RetireArtifact({root,record,packageVersion,onDone}:{root:string;record:EvidenceRecord;packageVersion:number;onDone:()=>void}) {
  const [open,setOpen]=useState(false);const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);const action=useAction();
  if(record.kind!=='file')return null;
  return <div className="retirement-panel"><button className="button" onClick={()=>setOpen(!open)}>{open?'Close retirement form':'Retire stored bytes'}</button>{open && <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<{deletion_pending_objects:number}>(`${evidenceRevisionPath(root,record.evidence_id,record.number)}/retire`,'POST',{
    expected_package_version:packageVersion,reviewed:true,reason}),result=>{if(result.deletion_pending_objects){setOpen(true);}else onDone();},'Artifact delivery is blocked. Metadata and historical snapshots remain.');}}>
    <p className="planning-warning">This blocks original and preview downloads for every revision referencing these bytes, then attempts to delete the stored objects. It does not delete evidence metadata, snapshots, backups or copies people already saved.</p>
    <Feedback error={action.error} success={action.success}/>{action.success && <p>Refresh the package. A storage deletion may need an operator retry; access remains blocked meanwhile.</p>}
    <TextArea label="Reason for retiring artifact bytes" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
    <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I reviewed this irreversible retention action. I am not deleting contribution or financial history.</ConfirmCheck>
    <Submit pending={action.pending}>Retire artifact bytes</Submit></form>}</div>;
}
export function ArchivedEvidence({root,evidenceId,revision,close,canRetire=false,packageVersion,onRetired}:{root:string;evidenceId:string;revision:number;close:()=>void;canRetire?:boolean;packageVersion?:number;onRetired?:()=>void}) {
  const state=useResource<EvidenceRecord>(evidenceRevisionPath(root,evidenceId,revision));
  return <section className="panel archive-panel"><div className="section-heading"><h3>Archived evidence</h3><button className="button" onClick={close}>Close archived evidence</button></div>{state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<><EvidenceView root={root} record={state.data}/>{canRetire && packageVersion!==undefined && onRetired && <RetireArtifact root={root} record={state.data} packageVersion={packageVersion} onDone={onRetired}/>}</>}</section>;
}
export function RevisionHistory({root,record,inspect}:{root:string;record:EvidenceRecord;inspect:(number:number)=>void}) {
  const state=useResource<{items:{number:number;reason:string;created_at:string}[]}>(`${root}/${record.evidence_id}/revisions`);
  if(state.loading || state.error || !state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  return <div className="evidence-history">{state.data.items.map(r=><div className="work-history" key={r.number}><div><strong>Revision {r.number}</strong><p className="small preserve-text">{r.reason}</p><small>{new Date(r.created_at).toLocaleString()}</small></div><button className="button" onClick={()=>inspect(r.number)}>Inspect revision {r.number}</button></div>)}</div>;
}
