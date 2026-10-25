import { AssessmentReview } from '../assessments/AssessmentReview.js';
import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback,Loading,SelectField,Submit,TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel } from '../../lib/planning.js';
import { formatCreditUnits,initialFindings,validateDecision,type CreditLine,type ReviewRecord,type Finding } from '../../lib/reviews.js';
import { SnapshotView } from '../evidence/Snapshots.js';
import { ArchivedEvidence,SourceLink } from '../evidence/EvidenceView.js';

export function CreditTable({entries,caption}:{entries:CreditLine[];caption:string}) {
  return <div className="table-scroll"><table><caption>{caption}</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Role</th><th scope="col">Units</th></tr></thead><tbody>{entries.map(e=><tr key={e.user_id+e.role}><th scope="row">{e.display_name}<small className="wrap">{e.user_id}</small></th><td>{humanLabel(e.role)}</td><td>{formatCreditUnits(e.atoms)}</td></tr>)}</tbody></table></div>;
}
function DecisionForm({root,review,refresh}:{root:string;review:ReviewRecord;refresh:()=>void}) {
  const [decision,setDecision]=useState('request_evidence');const [findings,setFindings]=useState(()=>initialFindings(review.target.criteria));
  const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const [independent,setIndependent]=useState(false);
  const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  const sources=review.target.evidence_sources.filter(s=>!s.restricted && s.ref);
  const update=(index:number,change:Partial<Finding>)=>setFindings(old=>old.map((f,i)=>i===index?{...f,...change}:f));
  return <section className="panel"><h3>Your independent decision</h3><p>Inspect the captured packet above. A checkbox records your declaration; it does not establish that the evidence is correct. A vote alone does not issue units.</p><Feedback error={action.error}/>
    <form onSubmit={event=>{event.preventDefault();void action.run(()=>{
      validateDecision(review,decision,findings,reviewed,independent);
      return api(`${root}/reviews/${review.id}/decisions`,'POST',{request_id:requestId,reviewed_target_hash:review.target_hash,
        decision,findings,evidence_reviewed:reviewed,independent,reason});},refresh);}}>
      {review.target.criteria.map((c,index)=><fieldset className="review-criterion" key={c.id}><legend>{c.id.startsWith('package')?'Package criterion':c.id.startsWith('evidence')?'Evidence requirement':'Deliverable criterion'}</legend><p className="preserve-text">{c.text}</p>
        <SelectField label={`Finding ${index+1}`} value={findings[index].result} onChange={e=>update(index,{result:e.target.value as Finding['result']})}><option value="insufficient">Insufficient evidence</option><option value="supported">Supported</option><option value="unsupported">Unsupported</option></SelectField>
        <SelectField label={`Supporting references for finding ${index+1}`} multiple size={Math.min(4,Math.max(2,sources.length))} value={findings[index].evidence_refs} onChange={e=>update(index,{evidence_refs:Array.from(e.target.selectedOptions,o=>o.value)})}>
          {sources.map(s=><option key={s.ref} value={s.ref}>{s.title} · {s.ref}</option>)}</SelectField>
        {!sources.length && <p className="planning-warning">No available supporting references. Acceptance is blocked; request the missing evidence.</p>}
        <TextArea label={`Explanation for finding ${index+1}`} required minLength={8} maxLength={500} value={findings[index].explanation} onChange={e=>update(index,{explanation:e.target.value})}/></fieldset>)}
      <SelectField label="Review decision" value={decision} onChange={e=>setDecision(e.target.value)}><option value="request_evidence">Request additional evidence</option><option value="reject">Reject this acceptance proposal</option><option value="accept">Accept this exact proposal</option></SelectField>
      <TextArea label="Reason for your decision" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={reviewed} onChange={setReviewed} disabled={action.pending}>I inspected the captured evidence, criteria, policy and exact attribution.</ConfirmCheck>
      <ConfirmCheck checked={independent} onChange={setIndependent} disabled={action.pending}>I am independent of the proposed outcome and have disclosed relevant conflicts.</ConfirmCheck>
      <Submit pending={action.pending}>Record independent decision</Submit>
    </form></section>;
}
function FinalizeForm({root,review,refresh}:{root:string;review:ReviewRecord;refresh:()=>void}) {
  const [requestId]=useState(()=>crypto.randomUUID());const [reason,setReason]=useState('');const [checked,setChecked]=useState(false);const action=useAction();
  return <section className="panel credit-finalize"><h3>Finalize the reviewed decision set</h3><p>{review.kind==='award'?`This issues ${formatCreditUnits(review.target.budget_atoms)} contribution units using the displayed attribution.`:'This closes the dispute under the displayed resolution. A reallocation adds linked adjustment entries; it does not rewrite the original award.'} No money is sent.</p><Feedback error={action.error}/>
    <form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/reviews/${review.id}/finalize`,'POST',{
      request_id:requestId,reviewed_decisions_hash:review.decisions_hash,reviewed:checked,reason}),refresh);}}>
      <TextArea label="Finalization reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={checked} onChange={setChecked} disabled={action.pending}>I reviewed every independent decision and confirm this exact finalization. Historical records will be preserved.</ConfirmCheck>
      <Submit pending={action.pending}>Finalize human-reviewed record</Submit>
    </form></section>;
}
export function ReviewDetail({root,id,close}:{root:string;id:string;close:()=>void}) {
  const state=useResource<ReviewRecord>(`${root}/reviews/${id}`);const [showPacket,setShowPacket]=useState(true);
  const [artifact,setArtifact]=useState<{id:string;revision:number}|null>(null);
  if(state.loading || state.error || !state.data)return <section className="panel"><button className="button" onClick={close}>Back to reviews</button><Loading error={state.error} refresh={state.refresh}/></section>;
  const review=state.data;const evidenceRoot=`${root}/work-packages/${review.package_id}/evidence`;
  return <div className="review-detail"><div className="section-heading"><button className="button" onClick={close}>Back to reviews</button><button className="button" onClick={()=>{setArtifact(null);state.refresh();}}>Refresh review</button></div>
    <section className="panel"><p className="eyebrow">Independent review · round {review.number}</p><h2>{review.target.title}</h2><Badge tone={review.state==='finalized'?'good':review.state==='stale'?'warning':'muted'}>{humanLabel(review.state)}</Badge>
      <p>{review.target.package_title} · policy version {review.target.policy_version} · {review.target.pool_key} pool</p>
      {review.blocker && <p className="planning-warning">{review.blocker}</p>}<p className="preserve-text">{review.reason}</p><p>{review.target.notice}</p>
      {review.target.before_attributions && <CreditTable entries={review.target.before_attributions} caption="Current finalized credit before the proposed correction"/>}
      <CreditTable entries={review.target.attributions} caption={review.state==='finalized'?'Preserved attribution in this finalized decision':'Exact proposed attribution — no credit is issued by this preview'}/>
      <p className="small wrap">Target fingerprint: <code>{review.target_hash}</code></p>
      {review.finalized_record_id && <p className="small wrap">Finalized record: <code>{review.finalized_record_id}</code>. See Contributions or Disputes for its current history.</p>}
    </section>
    {review.target.context && <section className="panel"><h3>Resolution evidence</h3><p className="preserve-text">{review.target.context.opening_reason}</p>
      {review.target.context.notes.map(note=><div className="dispute-note" key={note.id}><p className="preserve-text">{note.text}</p>{note.source_url && <SourceLink value={note.source_url}/>}<small className="wrap">Reference: note:{note.id}</small></div>)}</section>}
    <button className="button" onClick={()=>setShowPacket(!showPacket)}>{showPacket?'Hide':'Inspect'} captured evidence packet</button>
    {showPacket && <SnapshotView root={evidenceRoot} id={review.target.evidence_snapshot_id} close={()=>setShowPacket(false)} inspect={(entryId,revision)=>setArtifact({id:entryId,revision})}/>}
    {artifact && <ArchivedEvidence root={evidenceRoot} evidenceId={artifact.id} revision={artifact.revision} close={()=>setArtifact(null)}/>}
    {review.kind==='award'&&review.can_read_assessments&&<AssessmentReview key={review.id} projectRoot={root} review={review}/>}
    <section className="panel"><h3>Recorded decisions</h3><p>{review.decisions.length} of {review.minimum_reviewers} required independent decisions.</p>{!review.decisions.length && <p>No reviewer has decided yet.</p>}
      {review.decisions.map(d=><details className="form-details" key={d.id}><summary>{humanLabel(d.decision)} · reviewer {d.reviewer_id}</summary><p className="preserve-text">{d.reason || 'Detailed findings are restricted to authorized reviewers.'}</p>{d.findings.map(f=><div key={f.criterion_id}><strong>{f.criterion_id}: {humanLabel(f.result)}</strong><p className="preserve-text">{f.explanation}</p><p className="small wrap">{f.evidence_refs.join(', ')}</p></div>)}</details>)}</section>
    {review.can_decide && <DecisionForm key={review.target_hash+review.id} root={root} review={review} refresh={state.refresh}/>}
    {review.can_finalize && <FinalizeForm key={review.decisions_hash} root={root} review={review} refresh={state.refresh}/>}
  </div>;
}
