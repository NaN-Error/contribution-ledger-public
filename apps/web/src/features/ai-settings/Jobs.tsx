import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, Loading, Submit, TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatMicroUSD,parseMicroUSD,type AIConnection,type AIJob,type Page } from '../../lib/ai.js';
function JobActions({path,job,refresh}:{path:string;job:AIJob;refresh:()=>void}) {
  const a=useAction();const [amount,setAmount]=useState('');const [source,setSource]=useState('');const [reason,setReason]=useState('');
  return <><Feedback error={a.error} success={a.success}/>{job.status==='queued'&&<button className="button" disabled={a.pending} onClick={()=>void a.run(()=>api(`${path}/jobs/${job.id}/cancel`,'POST',{reason:'Owner cancelled the queued operation'}),refresh)}>Cancel queued operation</button>}
    {job.accounting_state==='uncertain'&&<details><summary>Reconcile uncertain usage</summary><p>Check the provider’s actual usage records first. Recording zero merely to free the budget can conceal a real charge. This does not retry the request or verify an invoice.</p>
      <form onSubmit={e=>{e.preventDefault();void a.run(()=>api(`${path}/jobs/${job.id}/reconcile`,'POST',{actual_microusd:parseMicroUSD(amount,1_000_000_000_000),source_reference:source,reason}),refresh);}}>
        <TextField label="Reviewed actual USD usage" required value={amount} onChange={e=>setAmount(e.target.value)} inputMode="decimal"/>
        <TextField label="Usage or invoice reference" minLength={8} maxLength={500} required value={source} onChange={e=>setSource(e.target.value)}/>
        <TextArea label="Reconciliation reason" minLength={8} maxLength={500} required value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={a.pending}>Record payer reconciliation</Submit>
      </form></details>}</>;
}
export function AIJobs({root,connection:c}:{root:string;connection:AIConnection}) {
  const path=`${root}/connections/${c.id}`;const [offset,setOffset]=useState(0);
  const s=useResource<Page<AIJob>>(`${path}/jobs?offset=${offset}`);
  const usage=useResource<Page<{month:string;held_microusd:number;estimated_microusd:number}>>(`${path}/usage`);
  const events=useResource<Page<{id:string;kind:string;created_at:string;document:Record<string,unknown>}>>(`${path}/events`);
  const refresh=()=>{s.refresh();usage.refresh();events.refresh();};
  return <section className="panel"><div className="section-heading"><h3>Jobs and usage estimates</h3><button className="button" onClick={refresh}>Refresh jobs and usage</button></div>
    <p>Paid requests are never automatically retried. Ambiguous dispatches retain their reservation until reconciled.</p>
    {usage.data?.items.map(b=><p key={b.month}>{b.month}: estimated {formatMicroUSD(b.estimated_microusd)}, held {formatMicroUSD(b.held_microusd)}.</p>)}
    <p className="small">Usage summary shows the latest 24 connection months.</p>{usage.error&&<p role="alert">{usage.error}</p>}
    {s.loading||s.error||!s.data?<Loading error={s.error} refresh={refresh}/>:<>
      {!s.data.items.length&&<p>No AI jobs yet.</p>}
      {s.data.items.map(j=><details key={j.id}><summary>{j.kind} · {j.status} · {j.created_at}</summary><p>Attempts: {j.attempts}; accounting: {j.accounting_state}; reservation: {formatMicroUSD(j.reserved_microusd)}; recorded: {formatMicroUSD(j.accounted_microusd)}.</p>
        <p>Request {j.id}. Eligible after {j.not_before}.</p>{j.last_error&&<p>Result code: {j.last_error}</p>}
        {j.result&&<pre className="code-block">{JSON.stringify(j.result,null,2)}</pre>}
        {c.can_manage&&<JobActions path={path} job={j} refresh={refresh}/>}</details>)}
      <button className="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous jobs</button>
      <button className="button" disabled={s.data.next_offset===null} onClick={()=>setOffset(s.data!.next_offset!)}>Next jobs</button>
    </>}
    <details><summary>Recent immutable operation events</summary>
      {events.error&&<p role="alert">{events.error}</p>}
      {events.data?.items.map(e=><p key={e.id}>{e.created_at} · {e.kind} <code>{JSON.stringify(e.document)}</code></p>)}
      <p className="small">Latest 50 events. The protected API provides pagination for older history.</p>
    </details>
  </section>;
}
