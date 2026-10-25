import { useState } from 'react';
import { api } from '../../lib/api.js';
import { useAction } from '../../hooks/useApi.js';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit, TextArea } from '../../components/forms.js';
import { analysisUtcDayRange, repositoryActivityRange, repositoryLinks, type AnalysisOverview, type AnalysisRun } from '../../lib/analysis.js';
import { PrivateConnection } from './PrivateConnection.js';

export function AddRepositories({root,data,created,onGitHub}:{root:string;data:AnalysisOverview;created:(r:AnalysisRun)=>void;onGitHub?:()=>void}) {
  const [connection,setConnection]=useState(data.connection||null);const [access,setAccess]=useState(connection?.active?'connected':'public');
  const [urls,setUrls]=useState(connection?.active?connection.repository_urls.join('\n'):'');const [imports,setImports]=useState<string[]>([]);
  const [start,setStart]=useState(new Date(Date.now()-90*86400000).toISOString().slice(0,10));const [end,setEnd]=useState(new Date().toISOString().slice(0,10));const [confirmed,setConfirmed]=useState(false);const action=useAction();
  const activityRange=repositoryActivityRange(data.dashboard.report.repositories);
  const [activity,setActivity]=useState<{full_name:string;private:boolean;latest_commit_at:string|null}[]>([]);const dates=useAction();
  const noSources=!!data.dashboard.report_id&&data.dashboard.report.source_count===0;
  return <details className="panel analysis-input" open={!data.runs.length||noSources}><summary><strong>Add repositories or refresh analysis</strong></summary><p>Paste repository links, choose the dates, and analyze. Public repositories work without signing in.</p>
      <TextArea label="GitHub repository links" placeholder="https://github.com/team/project" rows={2} value={urls} onChange={e=>setUrls(e.target.value)} maxLength={2000}/>
    <PrivateConnection root={root} data={{...data,connection}} urls={urls} changed={c=>{setConnection(c);setAccess(c?.active?'connected':'public');setConfirmed(false);}}/>
    {onGitHub&&<details><summary>Advanced GitHub App imports</summary><button type="button" className="text-button" onClick={onGitHub}>Open GitHub App connection and imports</button></details>}
    <Feedback error={action.error||dates.error}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>api<AnalysisRun>(root+'/runs','POST',{request_id:crypto.randomUUID(),repository_urls:urls.trim()?repositoryLinks(urls):[],import_ids:imports,...(access==='connected'&&connection?.active?{connection_id:connection.id}:{}),...analysisUtcDayRange(start,end),public_read_confirmed:confirmed}),created);}}>
      <SelectField label="Repository access" value={access} onChange={e=>{setAccess(e.target.value);setConfirmed(false);}}><option value="public">Public repositories (no account needed)</option>{connection?.active&&<option value="connected">Connected GitHub account (@{connection.username})</option>}</SelectField>
      <p className="small">The initial dates cover the last 90 days, not the repository's entire history. Older projects need an earlier period; each report covers at most 366 days.</p>
      <div className="form-grid"><TextField label="Analysis start (UTC)" type="date" required value={start} onChange={e=>setStart(e.target.value)}/><TextField label="Analysis end, excluded (UTC)" type="date" required value={end} max={new Date(Date.now()+86400000).toISOString().slice(0,10)} onChange={e=>setEnd(e.target.value)}/></div>
      {end===new Date(Date.now()+86400000).toISOString().slice(0,10)&&<p className="small">This range includes today's activity only up to the time you start analysis.</p>}
      {activityRange&&<div><button type="button" className="button" onClick={()=>{setStart(activityRange.start);setEnd(activityRange.end);setUrls(data.dashboard.report.repositories.filter(r=>access==='connected'||!r.private).map(r=>'https://github.com/'+r.full_name).join('\n'));}}>Use latest year of repository activity</button><p className="small">Suggested UTC period: {activityRange.start} through {activityRange.end} (end excluded). For multiple repositories, this is one shared period ending after the most recent captured commit. Confirm the links and dates before analyzing again.</p></div>}
      {!!data.imports.length&&<fieldset><legend>Completed authorized imports</legend>{data.imports.map(i=><label className="analysis-check" key={i.id}><input type="checkbox" checked={imports.includes(i.id)} onChange={e=>setImports(v=>e.target.checked?[...v,i.id]:v.filter(id=>id!==i.id))}/>{i.repository} · {i.private?'private':'public'} · {i.start_at.slice(0,10)} to {i.end_before.slice(0,10)}</label>)}</fieldset>}
      <label className="analysis-check"><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Read these selected repositories or reuse authorized evidence within this project.</label>
      <button className="button" type="button" disabled={dates.pending||!confirmed||!urls.trim()} onClick={()=>void dates.run(()=>api<{repositories:{full_name:string;private:boolean;latest_commit_at:string|null}[]}>(root+'/activity','POST',{repository_urls:repositoryLinks(urls),...(access==='connected'&&connection?.active?{connection_id:connection.id}:{}),read_confirmed:confirmed}),result=>{setActivity(result.repositories);const range=repositoryActivityRange(result.repositories);if(range){setStart(range.start);setEnd(range.end);}})}>{dates.pending?'Reading activity dates…':'Find repository activity dates'}</button>
      {!!activity.length&&<div role="status"><p>{activity.some(r=>r.latest_commit_at)?'Dates are set to the latest year of observed activity. Check them before analyzing; multiple repositories use one shared period.':'No commit history was available; the dates were left unchanged.'}</p>{activity.map(r=><p className="small" key={r.full_name}>{r.full_name}: {r.latest_commit_at?'latest default-branch commit '+r.latest_commit_at.slice(0,10):'no default-branch commits found'}</p>)}</div>}
      <p className="small">Up to eight repositories per report. Capture is bounded; pagination, request limits and missing sources remain visible. Imported project code is never run.</p><Submit pending={action.pending} disabled={dates.pending||(!urls.trim()&&!imports.length)}>Analyze repositories</Submit>
    </form></details>;
}
