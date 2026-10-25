import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback,Loading,Submit,TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel } from '../../lib/planning.js';
import { formatCreditUnits,type ReviewOptions,type ReviewOption,type ReviewRecord,type ReviewSummary,type Paged } from '../../lib/reviews.js';
import { ReviewDetail } from './ReviewDetail.js';

function Assignment({root,options,item,changed,open}:{root:string;options:ReviewOptions;item:ReviewOption;changed:()=>void;open:(id:string)=>void}) {
  const [selected,setSelected]=useState<string[]>([]);const [reason,setReason]=useState('');const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  return <details className="form-details"><summary>{item.title} · {formatCreditUnits(item.budget_atoms)} units{item.award_id?' · credit finalized':''}</summary>
    {item.blocker?<p className="planning-warning">{item.blocker}</p>:<><p>{item.minimum_reviewers} independent reviewer(s) required. All assigned reviewers must accept the exact packet before finalization.</p>
      {options.can_assign?<form onSubmit={e=>{e.preventDefault();void action.run(()=>{
        if(selected.length!==item.minimum_reviewers)throw new Error('Select exactly the required number of reviewers.');
        return api<ReviewRecord>(`${root}/reviews`,'POST',{request_id:requestId,package_id:options.package_id,
          deliverable_id:item.deliverable_id,expected_package_version:options.package_version,
          reviewed_target_hash:item.target_hash,reviewer_ids:selected,reason});},record=>{changed();open(record.id);});}}>
        <Feedback error={action.error}/><fieldset className="review-criterion"><legend>Independent reviewers</legend>{!item.eligible_reviewers.length && <p>No eligible reviewer. Add an independent reviewer with proper access and policy acknowledgement; do not substitute a beneficiary account.</p>}
          {item.eligible_reviewers.map(p=><label className="review-choice" key={p.user_id}><input type="checkbox" checked={selected.includes(p.user_id)} onChange={e=>setSelected(old=>e.target.checked?[...old,p.user_id]:old.filter(id=>id!==p.user_id))}/>{p.display_name} · {p.role}</label>)}</fieldset>
        <TextArea label={`Reason for assigning review: ${item.title}`} required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
        <p className="small muted">A new round visibly supersedes unfinished decisions for this deliverable. Earlier rounds are never erased.</p><Submit pending={action.pending}>Assign independent review</Submit>
      </form>:<p>The coordinator or an administrator assigns review.</p>}</>}
  </details>;
}
export function ReviewAssignments({root,packageId,onChanged}:{root:string;packageId:string;onChanged:()=>void}) {
  const state=useResource<ReviewOptions>(`${root}/reviews/options?package_id=${packageId}`);const [selected,setSelected]=useState<string|null>(null);
  if(selected)return <ReviewDetail root={root} id={selected} close={()=>{setSelected(null);state.refresh();onChanged();}}/>;
  return <section className="panel"><div className="section-heading"><h3>Independent deliverable review</h3><button className="button" onClick={state.refresh}>Refresh review options</button></div>
    {state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<><p>{state.data.notice}</p>
      {state.data.items.map(item=><Assignment key={item.deliverable_id+state.data!.package_version} root={root} options={state.data!} item={item} changed={state.refresh} open={setSelected}/>)}</>}</section>;
}
export function Reviews({root}:{root:string}) {
  const [offset,setOffset]=useState(0);const [selected,setSelected]=useState<string|null>(null);
  const state=useResource<Paged<ReviewSummary>>(`${root}/reviews?offset=${offset}`);
  if(selected)return <ReviewDetail root={root} id={selected} close={()=>{setSelected(null);state.refresh();}}/>;
  return <><section className="panel"><div className="section-heading"><h2>Human review queue</h2><button className="button" onClick={state.refresh}>Refresh reviews</button></div><p>Assign reviews from a submitted work package. Scope approval is not independent acceptance, and reviewer votes are separate from credit finalization.</p>
    {state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
      {!state.data.items.length && <p>No review rounds on this page. Submit evidence in Work packages, then assign independent reviewers.</p>}
      {state.data.items.map(row=><div className="work-history" key={row.id}><div><strong>{row.title}</strong><p>{row.package_title} · round {row.number} · {humanLabel(row.kind)}</p><Badge tone={row.state==='finalized'?'good':row.state==='stale'?'warning':'muted'}>{humanLabel(row.state)}</Badge>{row.blocker && <p className="small">{row.blocker}</p>}</div><button className="button" onClick={()=>setSelected(row.id)}>Inspect review</button></div>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer reviews</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>setOffset(state.data!.next_offset!)}>Older reviews</button></div></>}
    </section><Notifications root={root}/></>;
}
function Notifications({root}:{root:string}) {
  const [offset,setOffset]=useState(0);const state=useResource<Paged<{id:string;kind:string;message:string;created_at:string}>>(`${root}/notifications?offset=${offset}`);
  return <section className="panel"><h3>Your project notifications</h3><p className="small muted">In-app records only; no email is sent. Refresh to check for new events.</p><button className="button" onClick={state.refresh}>Refresh notifications</button>
    {state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>{!state.data.items.length && <p>No notifications on this page.</p>}{state.data.items.map(n=><div className="dispute-note" key={n.id}><strong>{humanLabel(n.kind)}</strong><p>{n.message}</p><small>{new Date(n.created_at).toLocaleString()}</small></div>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer notifications</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>setOffset(state.data!.next_offset!)}>Older notifications</button></div></>}
    </section>;
}
