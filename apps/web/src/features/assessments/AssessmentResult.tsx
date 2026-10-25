import { useState } from 'react';
import { Feedback,Loading,SelectField,Submit,TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useResource,useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel } from '../../lib/planning.js';
import type { ReviewRecord } from '../../lib/reviews.js';
import type { Page } from '../../lib/ai.js';
import { feedbackEligible,type AssessmentResult as Result,type AssessmentFinding,type ReviewerObservation } from '../../lib/assessments.js';
import { PacketView,EvidenceCitations } from './PacketView.js';
import { ArchivedEvidence } from '../evidence/EvidenceView.js';

function ObservationForm({root,result,review,finding,refresh}:{root:string;result:Result;review:ReviewRecord;finding:AssessmentFinding;refresh:()=>void}) {
  const [choice,setChoice]=useState('request_evidence');const [reason,setReason]=useState('');const [replacement,setReplacement]=useState('');
  const [inspected,setInspected]=useState(false);const [requestId,setRequestId]=useState(()=>crypto.randomUUID());const a=useAction();
  return <details className="form-details"><summary>Record your observation about this suggestion</summary><Feedback error={a.error} success={a.success}/>
    <form onSubmit={e=>{e.preventDefault();void a.run(()=>api(`${root}/results/${result.id}/feedback`,'POST',{
      request_id:requestId,review_id:review.id,reviewed_result_hash:result.content_hash,criterion_id:finding.criterion_id,
      action:choice,reason,replacement_text:choice==='modify'?replacement:null,original_evidence_reviewed:inspected}),()=>{setRequestId(crypto.randomUUID());setInspected(false);refresh();},
      'Observation preserved. Complete the separate independent decision form to accept work; this did not issue credit.');}}>
      <SelectField label="Response to the AI suggestion" value={choice} onChange={e=>setChoice(e.target.value)}>
        <option value="request_evidence">Request additional evidence</option><option value="reject">Reject this suggestion</option>
        <option value="modify">Record a modified observation</option><option value="accept">Agree with this observation only</option></SelectField>
      <TextArea label="Your evidence-based explanation" minLength={8} maxLength={800} required value={reason} onChange={e=>setReason(e.target.value)}/>
      {choice==='modify'&&<TextArea label="Your replacement observation (original AI output is preserved)" minLength={8} maxLength={1200} required value={replacement} onChange={e=>setReplacement(e.target.value)}/>}
      <ConfirmCheck checked={inspected} onChange={setInspected} disabled={a.pending}>I inspected original evidence, not only this AI suggestion. This is commentary, not independent acceptance.</ConfirmCheck>
      <Submit pending={a.pending}>Record reviewer observation</Submit>
    </form></details>;
}

export function AssessmentResultView({projectRoot,id,review,close}:{projectRoot:string;id:string;review?:ReviewRecord;close:()=>void}) {
  const root=`${projectRoot}/ai/assessments`;const state=useResource<Result>(`${root}/results/${id}`);
  const [offset,setOffset]=useState(0);const notes=useResource<Page<ReviewerObservation>>(`${root}/results/${id}/feedback?offset=${offset}`);
  const [artifact,setArtifact]=useState<{id:string;revision:number}|null>(null);const [showPacket,setShowPacket]=useState(true);
  if(state.loading||state.error||!state.data)return <section className="panel"><button className="button" onClick={close}>Close assessment</button><Loading error={state.error} refresh={state.refresh}/></section>;
  const result=state.data;const document=result.document;const mayComment=!!review&&feedbackEligible(result,review);
  const inspect=(sourceId:string,revision:number)=>setArtifact({id:sourceId,revision});
  return <div className="assessment-result"><section className="panel"><div className="section-heading"><h3>{result.mode==='official'?'Official-profile':'Advisory'} AI assessment</h3><button className="button" onClick={close}>Close assessment</button></div>
    <p className="planning-warning">{result.notice}</p>{result.metadata.synthetic&&<p className="planning-warning">Synthetic demonstration, not a real AI evaluation. This provider intentionally returns insufficient evidence for every criterion.</p>}
    {result.packet.stale&&<p className="error-panel">Historical assessment: submitted evidence or acceptance has changed. New feedback or generation requires current work and an explicit new run.</p>}
    <p>Status: {humanLabel(result.status)} · {result.metadata.provider} · requested model <code>{result.metadata.requested_model}</code> · returned model <code>{result.metadata.returned_model??'Not returned'}</code></p>
    <p className="small">Prompt {result.metadata.prompt_version}; schema {result.metadata.schema_version}; rubric {result.metadata.rubric_version}. A valid citation identifies supplied lines; it does not establish that the interpretation is true.</p>
    {!document&&<p>No validated suggestion was retained. The raw invalid/refused/truncated response is not saved. Inspect job accounting separately before considering an explicitly approved rerun.</p>}
    {document&&<><h4>Outcome summary</h4><p className="preserve-text">{document.summary}</p>
      {document.findings.map(finding=><section className="review-criterion" key={finding.criterion_id}><h4>{finding.criterion_id}: {humanLabel(finding.status)}</h4>
        <p className="preserve-text">{result.packet.payload.criteria.find(c=>c.id===finding.criterion_id)?.text}</p><p className="preserve-text">{finding.explanation}</p>
        <EvidenceCitations packet={result.packet} refs={finding.evidence_refs} inspect={inspect}/>
        {mayComment&&review&&<ObservationForm key={`${result.id}-${finding.criterion_id}`} root={root} result={result} review={review} finding={finding} refresh={notes.refresh}/>}</section>)}
      {document.proposed_roles.length>0&&<><h4>Optional role observations—not allocations</h4>{document.proposed_roles.map((role,index)=><div key={index}><p>{role.contributor_alias} · {humanLabel(role.role)}</p><p>{role.explanation}</p><EvidenceCitations packet={result.packet} refs={role.evidence_refs} inspect={inspect}/></div>)}</>}
      {document.overlap_flags.length>0&&<><h4>Possible overlap within this packet only</h4>{document.overlap_flags.map((flag,index)=><div key={index}><p>{flag.explanation}</p><EvidenceCitations packet={result.packet} refs={flag.evidence_refs} inspect={inspect}/></div>)}</>}
      {document.questions.length>0&&<><h4>Questions for the human reviewer</h4><ul>{document.questions.map((question,index)=><li key={index}>{question}</li>)}</ul></>}
    </>}
    <p className="small wrap">Result fingerprint: <code>{result.content_hash}</code></p>
    <button className="button" onClick={()=>setShowPacket(!showPacket)}>{showPacket?'Hide':'Inspect'} the exact outbound packet and originals</button>
  </section>
  {showPacket&&<PacketView projectRoot={projectRoot} packet={result.packet}/>}
  {artifact&&<ArchivedEvidence root={`${projectRoot}/work-packages/${result.packet.package_id}/evidence`} evidenceId={artifact.id} revision={artifact.revision} close={()=>setArtifact(null)}/>}
  <section className="panel"><h3>Preserved reviewer observations</h3>{notes.loading||notes.error||!notes.data?<Loading error={notes.error} refresh={notes.refresh}/>:<>
    {!notes.data.items.length&&<p>No observations recorded. The separate independent acceptance process remains required.</p>}
    {notes.data.items.map(note=><article className="work-history" key={note.id}><div><strong>{note.criterion_id}: {humanLabel(note.action)}</strong><p className="preserve-text">{note.reason}</p>{note.replacement_text&&<p className="preserve-text">Modified observation: {note.replacement_text}</p>}<small className="wrap">Reviewer {note.created_by} · {new Date(note.created_at).toLocaleString()}</small></div></article>)}
    <div className="button-row"><button className="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Earlier observations</button><button className="button" disabled={notes.data.next_offset===null} onClick={()=>setOffset(notes.data!.next_offset!)}>Later observations</button></div></>}
  </section></div>;
}
