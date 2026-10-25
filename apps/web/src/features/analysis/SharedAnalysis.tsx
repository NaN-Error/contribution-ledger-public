import { useEffect, useState } from 'react';
import { api } from '../../lib/api.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { analysisHash, type AnalysisDashboard, type AnalysisOverview, type AnalysisPublication, type AnalysisSharingPreview } from '../../lib/analysis.js';
import type { Project } from '../../lib/accounts.js';
import { RepositoryAnalysis } from './RepositoryAnalysis.js';

export function SharedAnalysis({project,publication='',person='',outcome='',navigate}:{project:Project;publication?:string;person?:string;outcome?:string;navigate?:(publication:string,person:string,outcome:string)=>void}) {
  const root=`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/analysis`;
  const [chosen,setChosen]=useState(publication);
  useEffect(()=>setChosen(publication),[publication]);
  const state=useResource<AnalysisOverview>(root+'/shared'+(chosen?'?publication_id='+chosen:''));
  if(!state.data)return <><Loading error={state.error} refresh={state.refresh}/>{state.error&&<button className="button" onClick={()=>{setChosen('');navigate?.('','','');}}>Open available shared reports</button>}</>;
  const data=state.data;const id=data.shared?.publication_id||'';
  return <><section className="panel"><h2>Shared contribution reports</h2><p>{data.shared?.notice}</p>
    <SelectField label="Shared report snapshot" value={id} onChange={e=>{setChosen(e.target.value);navigate?.(e.target.value,'','');}}><option value="">{id?'Latest shared snapshot':'No shared snapshot'}</option>{data.shared?.items.map(p=><option key={p.id} value={p.id}>{new Date(p.created_at).toLocaleString()} · draft revision {p.draft_version}</option>)}</SelectField>
    {!id&&<p>A project administrator can preview and share a draft report here. Your approved contributions remain below.</p>}
    {id&&<p className="small">Shared {new Date(data.shared!.created_at!).toLocaleString()}. This snapshot stays fixed; approved credit below is current.</p>}
  </section><RepositoryAnalysis key={id} project={project} initialPerson={person} initialOutcome={outcome} providedData={data} onRefresh={state.refresh} navigate={(_,p,o)=>navigate?.(id,p,o)}/></>;
}

function RevokeSharedReport({root,publication,refresh}:{root:string;publication:AnalysisPublication;refresh:()=>void}) {
  const [reason,setReason]=useState('');const action=useAction();
  return <details><summary>Revoke access to this snapshot</summary><form onSubmit={e=>{e.preventDefault();void action.run(()=>api(root+'/sharing/'+publication.id+'/revoke','POST',{request_id:crypto.randomUUID(),reason}),refresh);}}>
    <TextArea label="Reason for revoking report access" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Revoke shared report</Submit><Feedback error={action.error}/>
    <p className="small">Stops in-app member access. The snapshot and its sharing history remain preserved; copies already received cannot be recalled.</p>
  </form></details>;
}

function SharingPreview({root,project,dashboard,done}:{root:string;project:Project;dashboard:AnalysisDashboard;done:()=>void}) {
  const state=useResource<AnalysisSharingPreview>(root+'/sharing/preview?report_id='+dashboard.report_id);
  const [confirmed,setConfirmed]=useState(false);const [reason,setReason]=useState('');const action=useAction();
  if(!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  const view=state.data;const document=view.document;
  const data:AnalysisOverview={can_manage:false,runs:[],imports:[],dashboard:{...document,recognized:dashboard.recognized}};
  return <><p>{view.notice}</p><p>Review the contributor profiles, outcome evidence and repository context below. Private-source text in this preview will become visible to current project members.</p>
    <details className="analysis-sharing-preview"><summary>Inspect the exact report snapshot</summary><RepositoryAnalysis key={view.review_hash} project={project} providedData={data}/></details>
    <button className="button" type="button" onClick={()=>{setConfirmed(false);state.refresh();}}>Refresh sharing preview</button><Feedback error={action.error}/>
    <form aria-label="Share reviewed contribution report" onSubmit={e=>{e.preventDefault();void action.run(()=>api(root+'/sharing','POST',{request_id:crypto.randomUUID(),report_id:document.report_id,expected_version:document.draft_version,reviewed_hash:view.review_hash,sharing_confirmed:confirmed,reason}),done);}}>
      <label className="analysis-check"><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I reviewed this exact snapshot and may share its identities, evidence excerpts, repository context and proposed values with this project's members.</label>
      <TextArea label="Reason for sharing this report" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Share reviewed report</Submit>
    </form></>;
}

export function ReportSharing({root,project,dashboard}:{root:string;project:Project;dashboard:AnalysisDashboard}) {
  const [preview,setPreview]=useState(false);const history=useResource<{items:AnalysisPublication[]}>(root+'/sharing/history');
  return <details className="panel"><summary><strong>Share a contribution report</strong></summary><p>Give project members a fixed report to browse. This does not approve contributions or issue credit.</p>
    {dashboard.report_id&&<button className="button" type="button" onClick={()=>setPreview(v=>!v)}>{preview?'Close sharing preview':'Preview report for sharing'}</button>}
    {preview&&<SharingPreview key={dashboard.report_id+':'+dashboard.draft_version} root={root} project={project} dashboard={dashboard} done={()=>{setPreview(false);history.refresh();}}/>}
    <h3>Preserved sharing history</h3>{history.error&&<Loading error={history.error} refresh={history.refresh}/>}{history.data?.items.map(p=><article className="analysis-manual-entry" key={p.id}><h4>Shared {new Date(p.created_at).toLocaleString()} · draft revision {p.draft_version}</h4><p>{p.reason}</p>
      {p.revoked_at?<p>Revoked {new Date(p.revoked_at).toLocaleString()}: {p.revocation_reason}</p>:<><a className="button" href={analysisHash({workspace:project.workspace_id,project:project.id,report:'',publication:p.id,person:'',outcome:''})}>Open shared snapshot</a><RevokeSharedReport root={root} publication={p} refresh={history.refresh}/></>}
    </article>)}{history.data&&!history.data.items.length&&<p>No report has been shared yet.</p>}
  </details>;
}
