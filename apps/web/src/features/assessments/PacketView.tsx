import { useState } from 'react';
import { ArchivedEvidence } from '../evidence/EvidenceView.js';
import { humanLabel } from '../../lib/planning.js';
import type { Packet,Citation } from '../../lib/assessments.js';
import { citedLines } from '../../lib/assessments.js';

export function EvidenceCitations({packet,refs,inspect}:{packet:Packet;refs:Citation[];inspect:(id:string,revision:number)=>void}) {
  return <div>{refs.map((ref,index)=>{const source=packet.capture.sources[ref.source_id];let lines:string[]=[];
    try{lines=citedLines(packet.payload,ref);}catch{return <p key={index} role="alert">Invalid archived reference. Stop and investigate.</p>;}
    return <details className="form-details" key={`${ref.source_id}-${ref.start_line}-${index}`}><summary>{ref.source_id} · packet lines {ref.start_line}–{ref.end_line}</summary>
      <pre className="code-block">{lines.join('\n')}</pre>{source&&<button className="button" onClick={()=>inspect(source.evidence_id,source.revision)}>Inspect original evidence revision {source.revision}</button>}</details>;
  })}</div>;
}

export function PacketView({projectRoot,packet}:{projectRoot:string;packet:Packet}) {
  const [artifact,setArtifact]=useState<{id:string;revision:number}|null>(null);
  return <section className="panel assessment-packet"><h3>Exact outbound evidence packet</h3>
    <p className="planning-warning">{packet.capture.privacy_notice}</p>
    {packet.stale&&<p className="error-panel">This packet no longer matches current submitted work. It cannot authorize another request.</p>}
    <p>{packet.payload.notice}</p><h4>Outcome and independently reviewed portion</h4><p className="preserve-text">{packet.payload.outcome}</p><p>{packet.payload.deliverable}</p>
    <h4>Criteria sent to the evaluator</h4>{packet.payload.criteria.map(c=><p className="preserve-text" key={c.id}><strong>{c.id}:</strong> {c.text}</p>)}
    <h4>Explicit omissions</h4>{packet.payload.omissions.length?<ul>{packet.payload.omissions.map(o=><li key={o.code}>{humanLabel(o.code)} · {o.count}</li>)}</ul>:<p>No omissions were recorded by this bounded preparation process. This does not prove that all relevant work was supplied.</p>}
    <h4>Redacted source excerpts</h4>{!packet.payload.sources.length&&<p>No readable text sources. The model must not treat that as zero contribution.</p>}
    {packet.payload.sources.map(source=><section className="assessment-source" key={source.id}><h4>{source.id}: {source.title}</h4><p>{humanLabel(source.kind)}</p>
      <pre className="code-block assessment-lines">{source.lines.map((line,index)=>`${index+1}: ${line}`).join('\n')}</pre>
      {packet.capture.sources[source.id]&&<button className="button" onClick={()=>{const original=packet.capture.sources[source.id];setArtifact({id:original.evidence_id,revision:original.revision});}}>Inspect the original evidence</button>}
    </section>)}
    <details className="form-details"><summary>Full outbound JSON and local capture metadata</summary><p>Only the outbound payload is included in the provider request. Local provenance and alias-to-account mapping below remain local.</p>
      <h4>Outbound payload</h4><pre className="code-block">{JSON.stringify(packet.payload,null,2)}</pre>
      <h4>Local capture</h4><pre className="code-block">{JSON.stringify(packet.capture,null,2)}</pre></details>
    <p className="small wrap">Packet: <code>{packet.content_hash}</code><br/>Prompt and schema: <code>{packet.prompt_hash}</code></p>
    {artifact&&<ArchivedEvidence root={`${projectRoot}/work-packages/${packet.package_id}/evidence`} evidenceId={artifact.id} revision={artifact.revision} close={()=>setArtifact(null)}/>} 
  </section>;
}
