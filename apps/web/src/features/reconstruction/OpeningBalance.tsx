import { useState } from 'react';
import { ConfirmCheck } from '../../components/planning.js';
import { Feedback,Loading,Submit,TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatUnits } from '../../lib/planning.js';
import { formatFraction,historicalCommand,type BatchDetail,type OpeningPreview,type OpeningRecord,type HistoricalResult } from '../../lib/reconstruction.js';

export function OpeningComparison({record}:{record:OpeningRecord}){
  return <><p className="planning-warning">{record.notice}</p><p>Accepted units from this batch: <strong>{formatUnits(record.batch_issued_atoms)}</strong>. This is not a financial distribution.</p>
    {record.blockers.length>0&&<div className="error-panel"><h4>Opening balance is blocked</h4>{record.blockers.map((b,i)=><p key={i}>{b}</p>)}</div>}
    {record.share_comparison.map(pool=><section key={pool.pool_key}><h4>{pool.pool_key} pool</h4>
      <p>Baseline denominator: {formatUnits(pool.baseline_denominator_atoms)} units. Current denominator: {formatUnits(pool.current_denominator_atoms)} units. This batch: {formatUnits(pool.batch_denominator_atoms)} units.</p>
      <div className="table-scroll"><table><caption>Recognized share before and after historical review; other intervening awards and corrections are included in current credit.</caption><thead><tr><th>Contributor</th><th>Baseline units / share</th><th>Current units / share</th><th>Units in this batch</th></tr></thead><tbody>{pool.people.map(p=><tr key={p.user_id}><th scope="row">{p.display_name}</th><td>{formatUnits(p.baseline_atoms)} · {formatFraction(p.baseline_share)}</td><td>{formatUnits(p.current_atoms)} · {formatFraction(p.current_share)}</td><td>{formatUnits(p.batch_atoms)}</td></tr>)}</tbody></table></div></section>)}
    <details><summary>Full preserved comparison and decision inputs</summary><pre className="json-block">{JSON.stringify(record,null,2)}</pre></details></>;
}
export function OpeningBalance({base,batch,done}:{base:string;batch:BatchDetail;done:()=>void}){
  const frozen=batch.frozen_snapshot;const state=useResource<OpeningPreview>(frozen?null:base+'/opening-preview');const action=useAction();const[reason,setReason]=useState('');const[confirmed,setConfirmed]=useState(false);
  return <section className="panel"><div className="section-heading"><h3>{frozen?'Archived opening balance':'Review opening balance'}</h3>{!frozen&&<button className="button" onClick={()=>{setConfirmed(false);state.refresh();}}>Refresh balance comparison</button>}</div>
    <Feedback error={action.error}/>{frozen?<><p>Archived at {frozen.created_at}. Hash: <code>{frozen.record_hash}</code></p><OpeningComparison record={frozen.record}/></>:state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
      <OpeningComparison record={state.data.record}/><p>Review fingerprint: <code>{state.data.review_hash}</code></p>
      {batch.can_manage&&<form onSubmit={e=>{e.preventDefault();if(!state.data||!confirmed)return;void action.run(()=>api<HistoricalResult>(base+'/freeze','POST',{...historicalCommand(batch.version,reason),reviewed:true,reviewed_hash:state.data!.review_hash}),done);}}>
        <fieldset disabled={action.pending||state.data.record.blockers.length>0}><TextArea label="Reason for archiving this opening balance" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
        <ConfirmCheck checked={confirmed} onChange={setConfirmed}>I reviewed the exact scope, missing-work dispositions and share comparison. This preserves existing independently accepted credit, not new payments or permanent release shares.</ConfirmCheck>
        {confirmed&&<Submit pending={action.pending}>Archive reviewed opening balance</Submit>}</fieldset></form>}</>}
  </section>;
}
