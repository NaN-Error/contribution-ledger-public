import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { utcDayRange, type GitHubPage, type GitHubRepository, type ImportJob } from '../../lib/github.js';
import { humanLabel } from '../../lib/planning.js';

function ImportDetails({root,job,canManage,refresh}:{root:string;job:ImportJob;canManage:boolean;refresh:()=>void}) {
  const action=useAction();const [reason,setReason]=useState('');
  return <article className="panel"><div className="section-heading"><h3>Import {job.id.slice(0,8)}</h3><Badge tone={job.state==='completed'?'good':'warning'}>{humanLabel(job.state)}</Badge></div>
    <p>{job.start_at} → {job.end_before} (end excluded)</p><p className="small">Request scope captured {new Date(job.requested_as_of).toLocaleString()}. This is not a point-in-time GitHub backup.</p>
    <p>{job.data_requests} / {job.request_limit} data requests consumed or reserved · {job.tasks.done||0} processed fetch tasks · {job.tasks.pending||0} pending</p>
    <p className="small wrap">Pinned default-branch commit: <code>{job.anchor_sha||'Not captured'}</code></p>
    <p className="small">{Object.entries(job.stats).map(([k,v])=>`${humanLabel(k)}: ${v}`).join(' · ')||'No sources captured yet.'}</p>
    {job.error_code&&<p className="planning-warning">{humanLabel(job.error_code)}. Retry is not permitted before {new Date(job.next_attempt_at).toLocaleString()}.</p>}
    <details><summary>Coverage and limitations ({job.omissions.length})</summary><p className="small">{job.scope}</p>{job.omissions.length?<ul>{job.omissions.map((o,i)=><li className="small wrap" key={i}>{o}</li>)}</ul>:<p>No additional omissions have been recorded. Pending tasks are not completed evidence.</p>}</details>
    <Feedback error={action.error} success={action.success}/>
    {canManage&&['queued','running','paused','failed'].includes(job.state)&&<form onSubmit={e=>e.preventDefault()}>
      <TextField label="Reason for import action" minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><div className="button-row">
      {['paused','failed'].includes(job.state)&&<button className="button" disabled={action.pending||reason.trim().length<8} onClick={()=>void action.run(()=>api(`${root}/imports/${job.id}/resume`,'POST',{expected_version:job.version,reason}),refresh)}>Resume when permitted</button>}
      <button className="button" disabled={action.pending||reason.trim().length<8} onClick={()=>void action.run(()=>api(`${root}/imports/${job.id}/cancel`,'POST',{expected_version:job.version,reason}),refresh)}>Cancel remaining import</button></div>
      <p className="small muted">Cancellation preserves captured history. It cannot retract a network request already sent, but stale workers cannot commit its result.</p></form>}
  </article>;
}
export function GitHubImports({root,repositories,canManage}:{root:string;repositories:GitHubRepository[];canManage:boolean}) {
  const [offset,setOffset]=useState(0);const state=useResource<GitHubPage<ImportJob>>(`${root}/imports?offset=${offset}`);
  const [repo,setRepo]=useState('');const [start,setStart]=useState('');const [end,setEnd]=useState('');
  const [limit,setLimit]=useState(200);const [entities,setEntities]=useState(20);const [reason,setReason]=useState('');
  const [confirmed,setConfirmed]=useState(false);const [requestId,setRequestId]=useState(()=>crypto.randomUUID());const action=useAction();
  return <><div className="section-heading"><div><h2>Historical imports</h2><p>Bounded, read-only capture with saved checkpoints. Run the separate worker to process queued imports.</p></div><button className="button" onClick={state.refresh}>Refresh import status</button></div>
    {canManage&&<section className="panel"><h3>Request an import</h3><Feedback error={action.error} success={action.success}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/imports`,'POST',{
      repository_id:repo,...utcDayRange(start,end),request_limit:limit,entity_limit:entities,request_id:requestId,reason,reviewed:confirmed}),()=>{
        setRequestId(crypto.randomUUID());setConfirmed(false);state.refresh();},'Import queued. No source is fetched by this browser request and no credit is issued.');}}>
      <SelectField label="Verified repository" required value={repo} onChange={e=>setRepo(e.target.value)}><option value="">Choose a repository</option>{repositories.filter(r=>r.enabled).map(r=><option key={r.id} value={r.id}>{r.full_name}</option>)}</SelectField>
      <div className="github-form-grid"><TextField label="Start date (UTC, included)" type="date" required value={start} onChange={e=>setStart(e.target.value)}/><TextField label="End date (UTC, excluded)" type="date" required value={end} onChange={e=>setEnd(e.target.value)}/>
      <TextField label="Data-request budget" type="number" required min={10} max={1000} value={limit} onChange={e=>setLimit(Number(e.target.value))}/><TextField label="Maximum per root type" type="number" required min={1} max={200} value={entities} onChange={e=>setEntities(Number(e.target.value))}/></div>
      <p className="small">The root limit applies separately to PRs, issues, and default-branch commits. Comments, reviews, files, and checks have additional page limits. Authentication calls are separately bounded per worker step and are not included in the displayed data-request budget.</p>
      <TextField label="Reason for importing this range" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I reviewed the UTC range and limits. Details are fetched as they exist now; this cannot reconstruct deleted data or all historical knowledge.</ConfirmCheck><Submit pending={action.pending}>Queue read-only import</Submit>
    </form></section>}
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>{!state.data.items.length&&<section className="panel empty"><h3>No imports on this page</h3><p>Connect a repository, then request a bounded date range.</p></section>}
      {state.data.items.map(job=><ImportDetails key={`${job.id}:${job.version}`} root={root} job={job} canManage={canManage} refresh={state.refresh}/>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous imports</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>state.data?.next_offset!=null&&setOffset(state.data.next_offset)}>Next imports</button></div></>}
  </>;
}
