import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatMicroUSD,parseMicroUSD,modelStatus,selectableModel,probeRequest,type AIConnection,type AIModel,type AIQuote,type AIPrice,type Page } from '../../lib/ai.js';

function ModelActions({root,c,m,canApprove,onProbeQueued}:{root:string;c:AIConnection;m:AIModel;canApprove:boolean;onProbeQueued:()=>void}) {
  const path=`${root}/connections/${c.id}`;const a=useAction();
  const [input,setInput]=useState('0');const [output,setOutput]=useState('0');
  const [source,setSource]=useState(c.provider==='mock'?'Synthetic zero-cost fixture':'');const [reason,setReason]=useState('');
  const [days,setDays]=useState('7');const [q,setQ]=useState<{quote:AIQuote;requestId:string}|null>(null);
  const [dataPolicy,setDataPolicy]=useState('');const [title,setTitle]=useState('');const [outputCap,setOutputCap]=useState('4096');
  const prices=useResource<Page<AIPrice>>(`${path}/prices`);
  return <section className="panel"><h3>{m.document.name||m.remote_id}</h3><p><code>{m.remote_id}</code> · {modelStatus(m,c)}</p>
    <p>Provider-reported input limit: {m.document.input_limit??'Unknown'}; output limit: {m.document.output_limit??'Unknown'}.</p>
    <Feedback error={a.error} success={a.success}/>
    <details><summary>Recent price records for this model</summary>{prices.data?.items.filter(x=>x.model_id===m.id).map(p=><p key={p.id}>Input {formatMicroUSD(p.input_rate)} / million; output {formatMicroUSD(p.output_rate)} / million. Valid until {p.valid_until}. {p.source_reference}</p>)}
      {prices.error&&<p>{prices.error}</p>}<p className="small">Shows matching entries within the 50 most recent connection price records. The quotation uses the newest applicable record.</p></details>
    {c.can_manage && selectableModel(m,c)&&<>
      <details><summary>Add a reviewed price version</summary><p>Enter standard text input/output USD rates per one million tokens, covering this probe. Include billable reasoning output. No tool calls, cache creation or priority tier are requested. Rates are not discovered or verified automatically.</p>
        <form onSubmit={e=>{e.preventDefault();void a.run(()=>{
          if(!/^\d{1,2}$/.test(days)||Number(days)<1||Number(days)>30)throw new Error('Use 1–30 days.');
          return api(`${path}/prices`,'POST',{model_id:m.id,input_rate:parseMicroUSD(input,10_000_000_000),output_rate:parseMicroUSD(output,10_000_000_000),source_reference:source,
            valid_until:new Date(Date.now()+Number(days)*86400000).toISOString(),reason});
        },()=>{prices.refresh();setQ(null);},'Price version saved. Review a new quotation before a paid request.');}}>
          <TextField label="Input USD per million tokens" inputMode="decimal" value={input} onChange={e=>setInput(e.target.value)} required/>
          <TextField label="Output USD per million tokens" inputMode="decimal" value={output} onChange={e=>setOutput(e.target.value)} required/>
          <TextField label="Official pricing reference (or synthetic fixture)" value={source} onChange={e=>setSource(e.target.value)} minLength={8} maxLength={500} required/>
          <TextField label="Price review valid for days" inputMode="numeric" value={days} onChange={e=>setDays(e.target.value)} required/>
          <TextArea label="Price review reason" value={reason} onChange={e=>setReason(e.target.value)} minLength={8} maxLength={500} required/>
          <Submit pending={a.pending}>Save reviewed price version</Submit></form></details>
      <button className="button" disabled={a.pending} onClick={()=>void a.run(()=>api<AIQuote>(`${path}/models/${m.id}/probe-quote`),v=>setQ({quote:v,requestId:crypto.randomUUID()}))}>Prepare compatibility-test quotation (no generation)</button>
      {q&&<div className="panel"><h4>Review before requesting a probe</h4><p>Reserved estimate: <strong>{formatMicroUSD(q.quote.specification.reservation_microusd)}</strong> from {q.quote.specification.month}.</p>
        <p>Input allowance {q.quote.specification.input_token_allowance} tokens; output cap {q.quote.specification.max_output_tokens}. A model’s full behavior or provider bill is not guaranteed by this estimate.</p>
        <pre className="code-block">{q.quote.synthetic_prompt}</pre><p>No source files or personal contribution data are sent.</p>
        <button className="button primary" disabled={a.pending} onClick={()=>void a.run(()=>api(`${path}/models/${m.id}/probe`,'POST',probeRequest(q.quote,q.requestId)),()=>{setQ(null);onProbeQueued();})}>I approve this reservation and one synthetic probe</button>
        <button className="button" onClick={()=>setQ(null)} disabled={a.pending}>Discard quotation</button></div>}
    </>}
    {canApprove&&m.probe_state==='passed'&&selectableModel(m,c)&&<details><summary>Create an evaluator-profile draft</summary>
      <p>The payer must allow project use. This creates a new frozen evidence-review prompt, rubric and schema—not permission to disclose data or issue credit. Every actual packet needs separate data and payer approvals.</p>
      <form onSubmit={e=>{e.preventDefault();void a.run(()=>api(`${root}/profiles`,'POST',{connection_id:c.id,model_id:m.id,title,purpose:'evidence',max_output_tokens:Number(outputCap),data_policy_reference:dataPolicy,reason:'Create a frozen evidence-review configuration for explicit human approval'}),undefined,'Profile draft saved. Refresh the profiles list and inspect it before approval.');}}>
        <TextField label="Profile title" minLength={2} maxLength={100} required value={title} onChange={e=>setTitle(e.target.value)}/>
        <TextArea label="Project data-sharing policy reference and review" minLength={12} maxLength={500} required value={dataPolicy} onChange={e=>setDataPolicy(e.target.value)}/>
        <SelectField label="Evidence response output-token cap" value={outputCap} onChange={e=>setOutputCap(e.target.value)}>{[512,1024,2048,4096,8192].map(n=><option key={n} value={n}>{n}</option>)}</SelectField>
        <Submit pending={a.pending}>Save profile draft (not approved)</Submit></form></details>}
  </section>;
}

export function Catalog({root,connection:c,canApprove}:{root:string;connection:AIConnection;canApprove:boolean}) {
  const [offset,setOffset]=useState(0);const [selected,setSelected]=useState('');
  const [notice,setNotice]=useState<string|null>(null);
  const s=useResource<Page<AIModel>>(`${root}/connections/${c.id}/models?offset=${offset}`);
  if(s.loading||s.error||!s.data)return <Loading error={s.error} refresh={s.refresh}/>;
  const m=s.data.items.find(x=>x.id===selected);
  return <section><div className="section-heading"><h3>Available model catalog</h3><button className="button" onClick={s.refresh}>Reload captured catalog</button></div>
    <Feedback success={notice}/>
    <p>Capabilities are unknown unless documented or checked. A small schema probe tests protocol compatibility, not fairness, code quality, or reliable judgment.</p>
    {!s.data.items.length?<p>No captured models. Start the AI worker and inspect discovery jobs.</p>:<SelectField label="Captured model" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select a model</option>{s.data.items.map(x=><option key={x.id} value={x.id}>{x.remote_id}{selectableModel(x,c)?'':' — unavailable/incompatible'}</option>)}</SelectField>}
    <div className="tab-buttons"><button className="button" disabled={offset===0} onClick={()=>{setOffset(Math.max(0,offset-100));setSelected('');}}>Previous models</button><button className="button" disabled={s.data.next_offset===null} onClick={()=>{setOffset(s.data!.next_offset!);setSelected('');}}>Next models</button></div>
    {m&&<ModelActions key={`${m.id}-${m.probe_job_id??'new'}`} root={root} c={c} m={m} canApprove={canApprove} onProbeQueued={()=>{setNotice('Explicit probe queued. Inspect job history after the worker processes it.');s.refresh();}}/>}
  </section>;
}
