import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Feedback,Loading,Submit,TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel } from '../../lib/planning.js';
import { formatCreditUnits,formatDelta,formatShare,type Contributions as Totals,type CreditAward,type Paged,type DisputeRecord } from '../../lib/reviews.js';
import { CreditTable,ReviewDetail } from '../reviews/ReviewDetail.js';

function OpenDispute({root,award,changed}:{root:string;award:CreditAward;changed:()=>void}) {
  const [reason,setReason]=useState('');const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  return <section className="panel"><h3>Dispute this award</h3><p>Describe a specific concern. This creates an open case and blocks the affected pool from a future financial close; it does not change credit yet. The explanation is visible to project members.</p><Feedback error={action.error}/>
    <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<DisputeRecord>(`${root}/disputes`,'POST',{request_id:requestId,award_id:award.id,reason}),changed);}}>
      <TextArea label="Reason for disputing the award" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Open credit dispute</Submit>
    </form></section>;
}
export function AwardDetail({root,id,canDispute,close}:{root:string;id:string;canDispute:boolean;close:()=>void}) {
  const [offset,setOffset]=useState(0);const [review,setReview]=useState<string|null>(null);const [disputing,setDisputing]=useState(false);const [message,setMessage]=useState('');
  const state=useResource<CreditAward>(`${root}/contributions/awards/${id}?offset=${offset}`);
  if(review)return <ReviewDetail root={root} id={review} close={()=>setReview(null)}/>;
  if(state.loading || state.error || !state.data)return <section className="panel"><button className="button" onClick={close}>Back to contributions</button><Loading error={state.error} refresh={state.refresh}/></section>;
  const award=state.data;
  return <><div className="section-heading"><button className="button" onClick={close}>Back to contributions</button><button className="button" onClick={state.refresh}>Refresh award</button></div>
    <Feedback success={message}/><section className="panel"><h2>{award.title}</h2><Badge tone="good">Finalized contribution credit</Badge><p>{formatCreditUnits(award.budget_atoms)} units · policy version {award.policy_version} · {award.pool_key} pool</p>
      <p className="preserve-text">{award.reason}</p><small className="wrap">Award {award.id}</small>
      <CreditTable entries={award.current_attributions} caption="Current attribution reconstructed from preserved ledger events"/>
      <details className="form-details"><summary>Original attribution at acceptance</summary><CreditTable entries={award.original_attributions} caption="Original award — never overwritten by a correction"/></details>
      <button className="button" onClick={()=>setReview(award.review_id)}>Inspect original acceptance and evidence</button>
      {canDispute && <button className="button" onClick={()=>setDisputing(!disputing)}>{disputing?'Hide dispute form':'Raise an attribution concern'}</button>}
    </section>
    {disputing && <OpenDispute root={root} award={award} changed={()=>{setDisputing(false);setMessage('Dispute recorded. Continue in the project Disputes section.');state.refresh();}}/>}
    <section className="panel"><h3>Append-only contribution history</h3><p>Positive and negative entries reflect reviewed changes. Adjustment entries do not create extra budget.</p><div className="table-scroll"><table><caption>Ledger entries for this award</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Role</th><th scope="col">Change</th><th scope="col">Decision</th></tr></thead><tbody>{award.events?.map(e=><tr key={e.id}><th scope="row">{e.display_name}<small>{humanLabel(e.kind)}</small></th><td>{humanLabel(e.role)}</td><td>{formatDelta(e.delta_atoms)} units</td><td><button className="button" onClick={()=>setReview(e.review_id)}>Inspect decision</button></td></tr>)}</tbody></table></div>
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>Earlier entries</button><button className="button" disabled={award.next_offset==null} onClick={()=>setOffset(award.next_offset!)}>Later entries</button></div></section>
  </>;
}
export function Contributions({root,role}:{root:string;role:string}) {
  const state=useResource<Totals>(`${root}/contributions`);const [offset,setOffset]=useState(0);const [selected,setSelected]=useState<string|null>(null);
  const awards=useResource<Paged<CreditAward>>(`${root}/contributions/awards?offset=${offset}`);
  if(selected)return <AwardDetail root={root} id={selected} canDispute={role!=='viewer'} close={()=>{setSelected(null);state.refresh();awards.refresh();}}/>;
  return <><section className="panel"><div className="section-heading"><h2>Recognized contribution credit</h2><button className="button" onClick={()=>{state.refresh();awards.refresh();}}>Refresh contribution records</button></div>
    {state.loading || state.error || !state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
      <p>{state.data.notice}</p><div className="budget-metrics"><div className="budget-metric"><span>Finalized credit</span><strong>{formatCreditUnits(state.data.total_issued_atoms)}</strong><small>units, not dollars</small></div><div className="budget-metric"><span>Planned but unissued</span><strong>{formatCreditUnits(state.data.pending_planned_atoms)}</strong><small>units; no contributor owns these yet</small></div><div className="budget-metric"><span>Open disputes</span><strong>{state.data.open_dispute_count}</strong><small>affected pool closes are blocked</small></div></div>
      {!state.data.groups.length && <p>No credit has been finalized. Independent review and explicit finalization are required; commits, uploads and submissions do not award units.</p>}
      {state.data.groups.map(group=><section className="contribution-group" key={group.policy_id+group.milestone_id+group.pool_key}><h3>{group.milestone_name} · {group.pool_key} pool</h3><p>Policy version {group.policy_version}. Denominator: {formatCreditUnits(group.denominator_atoms)} finalized units. Pending planned work: {formatCreditUnits(group.pending_planned_atoms)} units.</p>
        {group.close_blocked && <p className="planning-warning">Future close blocked: {formatCreditUnits(group.disputed_atoms)} units are linked to unresolved disputes. Existing credit remains preserved.</p>}
        <div className="table-scroll"><table><caption>Share of finalized units in this named pool — not permanent ownership</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Finalized units</th><th scope="col">Scoped share</th><th scope="col">Roles</th></tr></thead><tbody>{group.people.map(p=><tr key={p.user_id}><th scope="row">{p.display_name}{p.user_id===state.data!.my_user_id?' (you)':''}</th><td>{formatCreditUnits(p.atoms)}</td><td>{formatShare(p.share.numerator,p.share.denominator)}</td><td>{Object.entries(p.roles).map(([name,n])=><div key={name}>{humanLabel(name)}: {formatCreditUnits(n)}</div>)}</td></tr>)}</tbody></table></div>
        <small>A temporary 100% of issued units is not 100% of all future work. Unissued reserves are never assigned to the owner.</small></section>)}</>}
    </section><section className="panel"><h3>Finalized awards</h3>{awards.loading || awards.error || !awards.data?<Loading error={awards.error} refresh={awards.refresh}/>:<>
      {!awards.data.items.length && <p>No finalized awards on this page.</p>}{awards.data.items.map(a=><div className="work-history" key={a.id}><div><strong>{a.title}</strong><p>{formatCreditUnits(a.budget_atoms)} units · policy {a.policy_version} · {a.pool_key}</p></div><button className="button" onClick={()=>setSelected(a.id)}>Inspect credit history</button></div>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer awards</button><button className="button" disabled={awards.data.next_offset===null} onClick={()=>setOffset(awards.data!.next_offset!)}>Older awards</button></div></>}
    </section></>;
}
