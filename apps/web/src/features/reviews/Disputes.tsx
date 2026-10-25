import { useState } from 'react';
import { Badge,TextField } from '../../components/shared.js';
import { Feedback,Loading,SelectField,Submit,TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel,unitInput } from '../../lib/planning.js';
import { workRoles } from '../../lib/workPackages.js';
import { correctionRows,formatCreditUnits,type DisputeRecord,type DisputeSummary,type ReviewRecord,type Paged } from '../../lib/reviews.js';
import { CreditTable,ReviewDetail } from './ReviewDetail.js';
import { SourceLink } from '../evidence/EvidenceView.js';

function Assignment({root,item,refresh}:{root:string;item:DisputeRecord;refresh:()=>void}) {
  const [id,setId]=useState('');const [reason,setReason]=useState('');const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  return <section className="panel"><h3>Assign an independent resolver</h3><p>Original recipients, the complainant, and original acceptance reviewers are excluded. Administrators cannot waive conflicts.</p><Feedback error={action.error}/>
    {!item.resolver_candidates.length?<p className="planning-warning">No eligible resolver. Add an independent reviewer through the normal access and policy process.</p>:<form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/disputes/${item.id}/assignments`,'POST',{request_id:requestId,reviewed_context_hash:item.context_hash,resolver_id:id,reason}),refresh);}}>
      <SelectField label="Independent resolver" required value={id} onChange={e=>setId(e.target.value)}><option value="">Select a reviewer</option>{item.resolver_candidates.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name}</option>)}</SelectField>
      <TextArea label="Reason for resolver assignment" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Record resolver assignment</Submit></form>}
  </section>;
}
function Note({root,item,refresh}:{root:string;item:DisputeRecord;refresh:()=>void}) {
  const [text,setText]=useState('');const [url,setUrl]=useState('');const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  return <section className="panel"><h3>Supplementary information</h3><p>Notes are project-visible and preserved. New notes invalidate unfinished resolution reviews. Do not paste secrets or restricted artifact contents.</p><Feedback error={action.error}/>
    <form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/disputes/${item.id}/notes`,'POST',{request_id:requestId,text,source_url:url.trim()||null}),refresh);}}>
      <TextArea label="Supplementary claim or supporting explanation" required minLength={12} maxLength={4000} value={text} onChange={e=>setText(e.target.value)}/>
      <TextField label="Optional HTTPS source link" type="url" maxLength={2000} value={url} onChange={e=>setUrl(e.target.value)} hint="Stored as an unverified reference; the application does not fetch the URL."/>
      <Submit pending={action.pending}>Add preserved note</Submit></form>
  </section>;
}
function Proposal({root,item,open}:{root:string;item:DisputeRecord;open:(id:string)=>void}) {
  const [kind,setKind]=useState<'uphold'|'reallocate'>('uphold');const [reason,setReason]=useState('');
  const [rows,setRows]=useState(()=>item.award.current_attributions.map(p=>({user_id:p.user_id,role:p.role as string,units:unitInput(p.atoms)})));
  const [reviewers,setReviewers]=useState<string[]>(item.resolver_id?[item.resolver_id]:[]);const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  const people=[...new Map([...item.current_participants,...item.award.original_attributions,...item.award.current_attributions].map(p=>[p.user_id,p])).values()];
  const update=(i:number,key:'user_id'|'role'|'units',value:string)=>setRows(old=>old.map((p,j)=>i===j?{...p,[key]:value}:p));
  return <section className="panel"><h3>Propose a reviewed resolution</h3><p>Only the assigned resolver may propose. The original policy requires {item.minimum_reviewers} independent reviewer(s), including the resolver. Selecting recipients below can further restrict reviewer eligibility.</p><Feedback error={action.error}/>
    <form onSubmit={e=>{e.preventDefault();void action.run(()=>{
      if(reviewers.length!==item.minimum_reviewers || !reviewers.includes(item.resolver_id!))throw new Error('Select the required independent quorum, including the current resolver.');
      const entries=kind==='reallocate'?correctionRows(rows,item.award.budget_atoms):[];
      return api<ReviewRecord>(`${root}/disputes/${item.id}/proposals`,'POST',{request_id:requestId,reviewed_context_hash:item.context_hash,disposition:kind,attributions:entries,reviewer_ids:reviewers,reason});},r=>open(r.id));}}>
      <SelectField label="Proposed resolution" value={kind} onChange={e=>setKind(e.target.value as typeof kind)}><option value="uphold">Uphold current attribution</option><option value="reallocate">Reallocate the accepted budget</option></SelectField>
      {kind==='reallocate' && <fieldset className="review-criterion"><legend>Complete replacement allocation</legend><p>Exactly {formatCreditUnits(item.award.budget_atoms)} units must remain assigned. No extra units can be created.</p>
        {rows.map((row,i)=><div className="correction-row" key={i}><SelectField label={`Contributor ${i+1}`} required value={row.user_id} onChange={e=>update(i,'user_id',e.target.value)}><option value="">Select contributor</option>{people.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name}</option>)}</SelectField>
          <SelectField label={`Role ${i+1}`} value={row.role} onChange={e=>update(i,'role',e.target.value)}>{workRoles.map(role=><option key={role} value={role}>{humanLabel(role)}</option>)}</SelectField>
          <TextField label={`Units ${i+1}`} required inputMode="decimal" value={row.units} onChange={e=>update(i,'units',e.target.value)}/><button type="button" className="button" onClick={()=>setRows(old=>old.filter((_,j)=>i!==j))}>Remove row {i+1}</button></div>)}
        <button type="button" className="button" disabled={rows.length>=100} onClick={()=>setRows(old=>[...old,{user_id:'',role:'implementation',units:''}])}>Add attribution row</button></fieldset>}
      <fieldset className="review-criterion"><legend>Independent decision quorum</legend>{item.resolver_candidates.map(p=><label className="review-choice" key={p.user_id}><input type="checkbox" checked={reviewers.includes(p.user_id)} onChange={e=>setReviewers(old=>e.target.checked?[...old,p.user_id]:old.filter(id=>id!==p.user_id))}/>{p.display_name}{p.user_id===item.resolver_id?' (assigned resolver)':''}</label>)}</fieldset>
      <TextArea label="Reason for the proposed resolution" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Create resolution review</Submit>
    </form></section>;
}
function DisputeDetail({root,id,close}:{root:string;id:string;close:()=>void}) {
  const state=useResource<DisputeRecord>(`${root}/disputes/${id}`);const [review,setReview]=useState<string|null>(null);
  if(review)return <ReviewDetail root={root} id={review} close={()=>{setReview(null);state.refresh();}}/>;
  if(state.loading || state.error || !state.data)return <section className="panel"><button className="button" onClick={close}>Back to disputes</button><Loading error={state.error} refresh={state.refresh}/></section>;
  const item=state.data;
  return <><div className="section-heading"><button className="button" onClick={close}>Back to disputes</button><button className="button" onClick={state.refresh}>Refresh dispute</button></div>
    <section className="panel"><h2>Credit dispute: {item.award.title}</h2><Badge tone={item.state==='open'?'warning':'good'}>{humanLabel(item.state)}</Badge><p>{item.notice}</p><p className="preserve-text">{item.reason}</p><small className="wrap">Filed by {item.opened_by} · case {item.id}</small>
      <CreditTable entries={item.award.current_attributions} caption="Current preserved credit — not changed merely by filing a dispute"/>
      <p>Assigned resolver: <code>{item.resolver_id || 'Not yet assigned'}</code></p>
      {item.resolution && <div className="success-panel"><h3>{humanLabel(item.resolution.disposition)}</h3><p className="preserve-text">{item.resolution.reason}</p><button className="button" onClick={()=>setReview(item.resolution!.review_id)}>Inspect finalized resolution</button></div>}
    </section>
    <section className="panel"><h3>Supporting notes and assignment history</h3>{!item.notes.length && <p>No supplementary notes.</p>}{item.notes.map(note=><div className="dispute-note" key={note.id}><p className="preserve-text">{note.text}</p>{note.source_url && <SourceLink value={note.source_url}/>}<small className="wrap">Author {note.created_by} · note {note.id}</small></div>)}
      <details className="form-details"><summary>Resolver assignments ({item.assignments.length})</summary>{item.assignments.map(a=><div className="dispute-note" key={a.number}><strong>Assignment {a.number}: {a.resolver_id}</strong><p className="preserve-text">{a.reason}</p></div>)}</details>
      {item.review_ids.map((reviewId,i)=><button className="button" key={reviewId} onClick={()=>setReview(reviewId)}>Inspect resolution review {item.review_ids.length-i}</button>)}
    </section>
    {item.can_assign && <Assignment key={'assignment'+item.context_hash} root={root} item={item} refresh={state.refresh}/>}
    {item.can_note && <Note key={'note'+item.context_hash} root={root} item={item} refresh={state.refresh}/>}
    {item.can_propose && <Proposal key={'proposal'+item.context_hash} root={root} item={item} open={setReview}/>}
  </>;
}
export function Disputes({root}:{root:string}) {
  const [offset,setOffset]=useState(0);const [selected,setSelected]=useState<string|null>(null);const state=useResource<Paged<DisputeSummary>>(`${root}/disputes?offset=${offset}`);
  if(selected)return <DisputeDetail root={root} id={selected} close={()=>{setSelected(null);state.refresh();}}/>;
  return <section className="panel"><div className="section-heading"><h2>Credit disputes</h2><button className="button" onClick={state.refresh}>Refresh disputes</button></div><p>Open a case from a finalized award in Contributions. Before acceptance, request changes or additional evidence through the review workflow instead.</p>
    {state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>{!state.data.items.length && <p>No disputes on this page.</p>}
      {state.data.items.map(item=><div className="work-history" key={item.id}><div><Badge tone={item.state==='open'?'warning':'good'}>{humanLabel(item.state)}</Badge><p className="preserve-text">{item.reason}</p></div><button className="button" onClick={()=>setSelected(item.id)}>Inspect dispute</button></div>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer cases</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>setOffset(state.data!.next_offset!)}>Older cases</button></div></>}
  </section>;
}
