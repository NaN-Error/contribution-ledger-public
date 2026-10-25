import { useEffect, useState } from 'react';
import { api } from '../../lib/api.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { TextField } from '../../components/shared.js';
import type { Items, Project, Workspace } from '../../lib/accounts.js';
import { analysisHash, parseAnalysisRoute, type AnalysisRoute } from '../../lib/analysis.js';
import { RepositoryAnalysis } from './RepositoryAnalysis.js';
import { SharedAnalysis } from './SharedAnalysis.js';

export function AnalysisHome() {
  const workspaces=useResource<Items<Workspace>>('/api/v1/workspaces');const [route,setRoute]=useState<AnalysisRoute>(()=>parseAnalysisRoute(window.location.hash));
  const workspace=workspaces.data?.items.find(w=>w.id===route.workspace)||workspaces.data?.items[0];
  const projects=useResource<Items<Project>>(workspace?`/api/v1/workspaces/${workspace.id}/projects`:null);
  const selected=projects.data?.items.find(p=>p.id===route.project)||projects.data?.items[0];
  const [name,setName]=useState('');const [description,setDescription]=useState('');const action=useAction();
  useEffect(()=>{const change=()=>setRoute(parseAnalysisRoute(window.location.hash));window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change);},[]);
  function go(next:AnalysisRoute){setRoute(next);window.location.hash=analysisHash(next);}
  if(workspaces.loading||workspaces.error)return <Loading error={workspaces.error} refresh={workspaces.refresh}/>;
  return <><div className="page-heading"><div><p className="eyebrow">Project contributions</p><h1>Repository dashboard</h1><p>Select a project, paste repository links, and explore contributor reports.</p></div></div>
    {!workspace?<section className="panel"><p>Create a workspace in Workspaces to begin.</p><a className="button primary" href="#projects">Open workspaces</a></section>:<>
      <div className="analysis-filters"><SelectField label="Workspace" value={workspace.id} onChange={e=>go({workspace:e.target.value,project:'',report:'',person:'',outcome:''})}>{workspaces.data?.items.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</SelectField><SelectField label="Project" value={selected?.id||''} onChange={e=>go({workspace:workspace.id,project:e.target.value,report:'',person:'',outcome:''})}><option value="">Select a project</option>{projects.data?.items.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</SelectField></div>
      {projects.loading||projects.error?<Loading error={projects.error} refresh={projects.refresh}/>:selected?<><h2>{selected.name}</h2>{!route.publication&&['admin','reviewer'].includes(selected.role)?<RepositoryAnalysis key={selected.id} project={selected} initialReport={route.report} initialPerson={route.person} initialOutcome={route.outcome} navigate={(report,person,outcome)=>go({workspace:workspace.id,project:selected.id,report,person,outcome})} onGitHub={()=>{window.location.hash=`#projects?workspace=${workspace.id}&project=${selected.id}&section=github`;}} onReview={()=>{window.location.hash=`#projects?workspace=${workspace.id}&project=${selected.id}&section=reconstruction`;}}/>:<SharedAnalysis key={selected.id} project={selected} publication={route.publication} person={route.person} outcome={route.outcome} navigate={(publication,person,outcome)=>go({workspace:workspace.id,project:selected.id,report:'',publication,person,outcome})}/>}</>:<section className="panel"><p>No accessible projects yet. Create one below or ask a workspace administrator for access.</p></section>}
      {workspace.can_manage&&<details className="panel analysis-new-project"><summary><strong>Create another project</strong></summary><Feedback error={action.error}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>api<Project>(`/api/v1/workspaces/${workspace.id}/projects`,'POST',{name,description,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',currency:'USD'}),p=>{setName('');projects.refresh();go({workspace:workspace.id,project:p.id,report:'',person:'',outcome:''});});}}><TextField label="New project name" required minLength={2} maxLength={120} value={name} onChange={e=>setName(e.target.value)}/><TextArea label="Project description" maxLength={1000} value={description} onChange={e=>setDescription(e.target.value)}/><Submit pending={action.pending}>Create project</Submit></form></details>}
    </>}
  </>;
}
