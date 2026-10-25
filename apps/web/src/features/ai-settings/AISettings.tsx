import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Project } from '../../lib/accounts.js';
import { parseMicroUSD, formatMicroUSD, type AIConnection, type AIOverview } from '../../lib/ai.js';
import { Catalog } from './Catalog.js';
import { AIJobs } from './Jobs.js';
import { Profiles } from './Profiles.js';

function ConnectionForm({root,providers,onCreated}:{root:string;providers:string[];onCreated:(c:AIConnection)=>void}) {
  const [provider,setProvider]=useState('mock');const [label,setLabel]=useState('');
  const [limit,setLimit]=useState('0');const [permission,setPermission]=useState('');
  const [share,setShare]=useState(false);const [reason,setReason]=useState('');
  const [requestId,setRequestId]=useState(()=>crypto.randomUUID());const a=useAction();
  return <section className="panel"><h2>Add your AI connection</h2><p>You own and pay for this connection. It belongs only to this project. Never enter a consumer-account password or session token.</p>
    <Feedback error={a.error}/><form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const raw=new FormData(form).get('api_key');
      // The field is immediately cleared. Keys are never put in persistent browser storage.
      const input=form.elements.namedItem('api_key');if(input instanceof HTMLInputElement) input.value='';
      void a.run(()=>api<AIConnection>(`${root}/connections`,'POST',{request_id:requestId,provider,label,permission_reference:permission,
        monthly_limit_microusd:parseMicroUSD(limit),allow_project_use:share,reason,...(provider==='mock'?{}:{api_key:String(raw??'')})}),c=>{setRequestId(crypto.randomUUID());onCreated(c);});}}>
      <SelectField label="Provider" value={provider} onChange={e=>setProvider(e.target.value)}>{providers.map(p=><option key={p} value={p}>{p==='mock'?'Synthetic test provider — no key or charge':p}</option>)}</SelectField>
      <TextField label="Connection label" value={label} onChange={e=>setLabel(e.target.value)} minLength={2} maxLength={100} required/>
      {provider!=='mock' && <><TextField label="Permitted API key" type="password" name="api_key" autoComplete="off" minLength={8} maxLength={4096} required hint="Sent only to your local backend over this session. It is never returned by the API."/>
        <p className="small">The operator must review this provider’s credential and data terms. Configuring a key is not permission to send project evidence.</p></>}
      <TextField label="Per-connection monthly USD limit" value={limit} onChange={e=>setLimit(e.target.value)} inputMode="decimal" required hint="0 blocks live paid probes. This is not a provider account-wide invoice cap."/>
      <TextArea label="Permission / payer authorization reference" value={permission} onChange={e=>setPermission(e.target.value)} minLength={8} maxLength={500} required/>
      <label className="check-row"><input type="checkbox" checked={share} onChange={e=>setShare(e.target.checked)}/>Authorize project administrators to select this connection for future official use. They cannot run paid probes on my behalf.</label>
      <TextArea label="Reason for connection" value={reason} onChange={e=>setReason(e.target.value)} minLength={8} maxLength={500} required/>
      <Submit pending={a.pending}>Create connection and queue discovery</Submit></form></section>;
}

function ConnectionControls({root,c,refresh}:{root:string;c:AIConnection;refresh:()=>void}) {
  const [label,setLabel]=useState(c.label);const [limit,setLimit]=useState((c.monthly_limit_microusd/1_000_000).toFixed(6));
  const [share,setShare]=useState(c.allow_project_use);const [reason,setReason]=useState('');const a=useAction();
  if(!c.can_manage)return <p>Only the connection owner can change spending, rotate credentials, or request probes.</p>;
  return <section className="panel"><h3>Connection controls</h3><Feedback error={a.error} success={a.success}/>
    {!c.enabled?<p>This connection was revoked. Historical jobs and profiles remain; it cannot be reactivated.</p>:<>
    <button className="button" disabled={a.pending} onClick={()=>void a.run(()=>api(`${root}/connections/${c.id}/refresh`,'POST',{request_id:crypto.randomUUID()}),refresh,'Catalog refresh queued. The AI worker must be running.')}>Refresh available models</button>
    <form onSubmit={e=>{e.preventDefault();void a.run(()=>api(`${root}/connections/${c.id}`,'PATCH',{label,monthly_limit_microusd:parseMicroUSD(limit),allow_project_use:share,expected_version:c.version,reason}),refresh);}}>
      <TextField label="Edit connection label" required minLength={2} maxLength={100} value={label} onChange={e=>setLabel(e.target.value)}/>
      <TextField label="Monthly USD limit" required inputMode="decimal" value={limit} onChange={e=>setLimit(e.target.value)}/>
      <label className="check-row"><input type="checkbox" checked={share} onChange={e=>setShare(e.target.checked)}/>Allow future project evaluator use</label>
      <p className="small">Changing this authorization invalidates old model qualifications and profiles. It never silently restores an earlier approval.</p>
      <TextArea label="Reason for settings change or revocation" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <Submit pending={a.pending}>Save connection settings</Submit>
      <button type="button" className="button" disabled={a.pending||reason.trim().length<8} onClick={()=>{
        if(window.confirm('Revoke this connection? Queued work stops, but already-sent calls and provider-side keys cannot be recalled.'))
          void a.run(()=>api(`${root}/connections/${c.id}/revoke`,'POST',{expected_version:c.version,reason}),refresh);
      }}>Revoke connection</button></form>
    {c.provider!=='mock' && <form onSubmit={e=>{e.preventDefault();const f=e.currentTarget;const key=String(new FormData(f).get('replacement')??'');f.reset();
      void a.run(()=>api(`${root}/connections/${c.id}/rotate`,'POST',{expected_version:c.version,api_key:key,reason}),refresh);}}>
      <TextField label="Replacement permitted API key" name="replacement" type="password" autoComplete="off" minLength={8} maxLength={4096} required/>
      <button className="button" disabled={a.pending||reason.trim().length<8} type="submit">Rotate key and invalidate prior qualification</button></form>}
    </>}</section>;
}

export function AISettings({project}:{project:Project}) {
  const root=`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/ai`;
  const state=useResource<AIOverview>(root);const [selected,setSelected]=useState<string|null>(null);
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  const data=state.data;const c=data.connections.find(x=>x.id===selected);
  return <><div className="section-heading"><h2>AI connections and evaluator settings</h2><button className="button" onClick={state.refresh}>Refresh status</button></div>
    <section className="panel"><p>{data.notice}</p><p>{data.budget_notice}</p><p><strong>Nothing runs in the background unless the optional AI worker is explicitly started.</strong> Model discovery runs on creation, request, and approximately daily while the worker is running. Paid compatibility tests are never scheduled automatically.</p>
      <p className="small">Local setup: <code>scripts/ai.ps1 -Action init</code>, then <code>scripts/ai.ps1 -Action start</code>. Live providers require additional operator approval. See docs/ai_connections.md.</p></section>
    <SelectField label="Connection to inspect" value={selected??''} onChange={e=>setSelected(e.target.value||null)}><option value="">Choose a connection</option>{data.connections.map(v=><option key={v.id} value={v.id}>{v.label} — {v.provider}{v.enabled?'':' (revoked)'}</option>)}</SelectField>
    {c&&<><section className="panel"><h3>{c.label}</h3><Badge>{c.provider}</Badge><p>{c.credential_state} · generation {c.generation}</p>
      <p>Monthly local limit: {formatMicroUSD(c.monthly_limit_microusd)} · Last complete catalog: {c.last_catalog_at??'Not yet captured'}.</p>
      {c.last_error&&<p className="error-panel">Last discovery problem: {c.last_error}. Previously captured models are retained, not assumed current.</p>}
      {c.retry_not_before&&<p>Shared retry boundary: {c.retry_not_before}</p>}</section>
      <ConnectionControls key={`${c.id}-${c.version}`} root={root} c={c} refresh={state.refresh}/>
      <Catalog key={`${c.id}-${c.generation}`} root={root} connection={c} canApprove={data.can_approve}/>
      <AIJobs key={c.id} root={root} connection={c}/></>}
    <Profiles root={root} canApprove={data.can_approve}/>
    {data.can_create&&<ConnectionForm root={root} providers={data.providers} onCreated={v=>{setSelected(v.id);state.refresh();}}/>}
  </>;
}
