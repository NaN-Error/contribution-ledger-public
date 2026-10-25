import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback,SelectField,Submit,TextArea } from '../../components/forms.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { categories,humanLabel,type Category } from '../../lib/planning.js';
import { boundedHistoricalBody,historicalCommand,type BatchDetail,type MissingClaim,type HistoricalResult } from '../../lib/reconstruction.js';

function ClaimDecision({claim,base,batch,done}:{claim:MissingClaim;base:string;batch:BatchDetail;done:()=>void}){
  const[disposition,setDisposition]=useState<'included'|'declined'>('included');const[candidate,setCandidate]=useState('');const[reason,setReason]=useState('');const action=useAction();
  return <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<HistoricalResult>(base+'/resolve-claim','POST',{...historicalCommand(batch.version,reason),claim_id:claim.id,disposition,candidate_id:disposition==='included'?candidate:null}),done);}}>
    <Feedback error={action.error}/><fieldset disabled={action.pending}><SelectField label={`Disposition for ${claim.document.title}`} value={disposition} onChange={e=>setDisposition(e.target.value as 'included'|'declined')}><option value="included">Include through a candidate</option><option value="declined">Decline with a preserved explanation</option></SelectField>
    {disposition==='included'&&<SelectField label="Reviewed candidate for missing work" required value={candidate} onChange={e=>setCandidate(e.target.value)}><option value="">Choose a current candidate</option>{batch.candidates?.filter(c=>c.state==='draft'||c.state==='linked').map(c=><option key={c.id} value={c.id}>{c.document.title}</option>)}</SelectField>}
    <TextArea label="Explanation of missing-work decision" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Record reviewed disposition</Submit></fieldset></form>;
}
export function MissingClaims({base,batch,done}:{base:string;batch:BatchDetail;done:()=>void}){
  const[title,setTitle]=useState('');const[category,setCategory]=useState<Category>('art');const[description,setDescription]=useState('');const action=useAction();
  return <section className="panel"><h3>{batch.can_inspect?'Missing-work review queue':'Your missing-work claims'}</h3><p>Include art, design, testing, production and other work absent from GitHub. Original claims are visible to their author and authorized administrators/reviewers, not automatically to every member.</p>
    {!batch.my_claims_or_review_queue.length&&<p>No visible claims recorded. That does not establish complete contribution coverage.</p>}
    {batch.my_claims_or_review_queue.map(claim=><article key={claim.id} className="work-deliverable"><h4>{claim.document.title}</h4><p>{claim.document.description}</p><p>{humanLabel(claim.document.category)} · {claim.state}</p>{claim.resolution_reason&&<p>Decision: {claim.resolution_reason}</p>}
      {batch.can_manage&&batch.state!=='frozen'&&<ClaimDecision claim={claim} base={base} batch={batch} done={done}/>}</article>)}
    {batch.can_submit_claim&&batch.state!=='frozen'&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api<HistoricalResult>(base+'/missing-claims','POST',boundedHistoricalBody({request_id:crypto.randomUUID(),title,category,description})),done);}}>
      <Feedback error={action.error}/><fieldset disabled={action.pending}><TextField label="Missing-work title" required minLength={2} maxLength={120} value={title} onChange={e=>setTitle(e.target.value)}/>
      <SelectField label="Missing-work category" value={category} onChange={e=>setCategory(e.target.value as Category)}>{categories.map(x=><option key={x} value={x}>{humanLabel(x)}</option>)}</SelectField>
      <TextArea label="Describe the missing contribution" required minLength={8} maxLength={2000} value={description} onChange={e=>setDescription(e.target.value)}/><Submit pending={action.pending}>Submit missing-work claim</Submit></fieldset></form>}
    {batch.state==='frozen'&&<p>This snapshot is archived. Concerns about accepted credit use the Disputes tab; newly discovered work requires a new explicit historical scope.</p>}
  </section>;
}
