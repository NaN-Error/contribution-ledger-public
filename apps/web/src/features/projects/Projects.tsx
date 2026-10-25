import { Finance } from '../distributions/Finance.js';
import { Reconstruction } from '../reconstruction/Reconstruction.js';
import { ContributionOverview } from '../overview/ContributionOverview.js';
import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, Submit, TextArea } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Items, Project, Workspace } from '../../lib/accounts.js';
import { Members } from './Members.js';
import { Invitations } from './Invitations.js';
import { Audit } from './Audit.js';
import { Policies } from '../policies/Policies.js';
import { Milestones } from '../milestones/Milestones.js';
import { Reviews } from '../reviews/Reviews.js';
import { Disputes } from '../reviews/Disputes.js';
import { Contributions } from '../contributions/Contributions.js';
import { Simulator } from '../simulator/Simulator.js';
import { AISettings } from '../ai-settings/AISettings.js';
import { GitHub } from '../github/GitHub.js';
import { WorkPackages } from '../work-packages/WorkPackages.js';
import { RepositoryAnalysis } from '../analysis/RepositoryAnalysis.js';
import { SharedAnalysis } from '../analysis/SharedAnalysis.js';

function projectSelection() {
  const q=new URLSearchParams(window.location.hash.split('?')[1]||'');
  const id=(key:string)=>/^[0-9a-f-]{36}$/.test(q.get(key)||'')?q.get(key)!:null;
  return {workspace:id('workspace'),project:id('project'),section:['reconstruction','github','ai'].includes(q.get('section')||'')?q.get('section') as 'reconstruction'|'github'|'ai':'analysis' as const};
}

function ProjectSettings({ project, refresh }: { project: Project; refresh: () => void }) {
  const [name, setName] = useState(project.name); const [description, setDescription] = useState(project.description);
  const [timezone, setTimezone] = useState(project.timezone); const [reason, setReason] = useState(''); const action = useAction();
  if (!project.can_manage) return <section className="panel"><h2>Project details</h2><p>{project.description || 'No description added.'}</p><p>{project.timezone} · {project.currency}</p><Badge>{project.role} access</Badge></section>;
  return <section className="panel"><h2>Project settings</h2><Feedback error={action.error} /><form onSubmit={event => { event.preventDefault(); void action.run(() => api(`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}`, 'PATCH', {
    name, description, timezone, currency: project.currency, reason, expected_version: project.version }), refresh); }}>
    <TextField label="Project name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} />
    <TextArea label="Project description" maxLength={1000} rows={3} value={description} onChange={e => setDescription(e.target.value)} />
    <TextField label="Project timezone" required maxLength={80} value={timezone} onChange={e => setTimezone(e.target.value)} hint="Use an IANA name, such as UTC or America/Puerto_Rico." />
    <TextField label="Project currency" value={project.currency} readOnly hint="USD-only synthetic simulations and closed records. No actual payment transmission or real-use authorization." />
    <TextField label="Reason for settings change" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /><Submit pending={action.pending}>Save project settings</Submit></form></section>;
}

function ProjectDetail({ workspaceId, projectId, onBack }: { workspaceId: string; projectId: string; onBack: () => void }) {
  const state = useResource<Project>(`/api/v1/workspaces/${workspaceId}/projects/${projectId}`);
  const [section, setSection] = useState<'analysis' | 'settings' | 'policies' | 'milestones' | 'work' | 'reviews' | 'contributions' | 'disputes' | 'simulator' | 'github' | 'ai' | 'reconstruction' | 'overview' | 'finance'>(()=>projectSelection().section);
  return <><button className="button back-button" onClick={onBack}>← Back to workspace</button>
    {state.loading || state.error || !state.data ? <Loading error={state.error} refresh={state.refresh} /> : <>
      <div className="page-heading"><div><p className="eyebrow">Project access</p><h1>{state.data.name}</h1><p>{state.data.timezone} · {state.data.currency} · {state.data.role}</p></div><button className="button" onClick={state.refresh}>Refresh project</button></div>
      <div className="tab-buttons" aria-label="Project sections">{(['analysis', 'overview', 'reconstruction', 'policies', 'milestones', 'work', 'reviews', 'contributions', 'disputes', 'simulator', 'finance', 'github', 'ai', 'settings'] as const).map(value => <button key={value} className={`button ${section === value ? 'primary' : ''}`} aria-pressed={section === value} onClick={() => setSection(value)}>{value === 'analysis' ? 'Repository dashboard' : value === 'overview' ? 'Contribution overview' : value === 'reconstruction' ? 'Historical review' : value === 'policies' ? 'Policies' : value === 'milestones' ? 'Milestones' : value === 'work' ? 'Work packages' : value === 'reviews' ? 'Human reviews' : value === 'contributions' ? 'Contributions' : value === 'disputes' ? 'Disputes' : value === 'finance' ? 'Financial records' : value === 'simulator' ? 'Revenue simulator' : value === 'github' ? 'GitHub' : value === 'ai' ? 'AI settings' : 'Settings and access'}</button>)}</div>
      {section === 'analysis' ? (['admin','reviewer'].includes(state.data.role) ? <RepositoryAnalysis key={state.data.id} project={state.data} onReview={()=>setSection('reconstruction')} onGitHub={()=>setSection('github')} /> : <SharedAnalysis key={state.data.id} project={state.data} />) : section === 'finance' ? <section className="finance-view"><Finance key={state.data.id} project={state.data} /></section> : section === 'overview' ? <ContributionOverview key={state.data.id} root={`/api/v1/workspaces/${workspaceId}/projects/${projectId}`} /> : section === 'reconstruction' ? <Reconstruction key={state.data.id} project={state.data} /> : section === 'policies' ? <Policies key={state.data.id} project={state.data} /> : section === 'milestones' ? <Milestones key={state.data.id} project={state.data} /> : section === 'work' ? <WorkPackages key={state.data.id} project={state.data} /> : section === 'reviews' ? <Reviews root={`/api/v1/workspaces/${workspaceId}/projects/${projectId}`} /> : section === 'contributions' ? <Contributions root={`/api/v1/workspaces/${workspaceId}/projects/${projectId}`} role={state.data.role} /> : section === 'disputes' ? <Disputes root={`/api/v1/workspaces/${workspaceId}/projects/${projectId}`} /> : section === 'ai' ? <AISettings key={state.data.id} project={state.data} /> : section === 'github' ? <GitHub key={state.data.id} project={state.data} /> : section === 'simulator' ? <Simulator key={state.data.id} project={state.data} /> : <div className="guide-grid"><ProjectSettings key={state.data.version} project={state.data} refresh={state.refresh} />
      {state.data.can_manage ? <Members path={`/api/v1/workspaces/${workspaceId}/projects/${projectId}/members`} /> : <section className="panel"><h2>Your access</h2><p>You can read this project's details. Only project administrators can manage settings and explicit project members.</p></section>}</div>}
      <p className="small muted">Human-approved contribution units and dispute history are available. Hypothetical revenue simulation is available; this application does not send payments or issue ownership.</p></>}
  </>;
}

function ProjectList({ workspace, open }: { workspace: Workspace; open: (id: string) => void }) {
  const base = `/api/v1/workspaces/${workspace.id}/projects`; const state = useResource<Items<Project>>(base);
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [timezone, setTimezone] = useState('UTC'); const action = useAction();
  return <><Feedback error={action.error} /><div className="section-heading"><h2>Accessible projects</h2><button className="button" onClick={state.refresh}>Refresh projects</button></div>
    {state.loading || state.error ? <Loading error={state.error} refresh={state.refresh} /> : <div className="project-grid">{!state.data?.items.length && <section className="panel"><h2>No accessible projects</h2><p>{workspace.can_manage ? 'Create the first project below.' : 'Ask a workspace administrator to grant you access to a project.'}</p></section>}
      {state.data?.items.map(project => <button className="project-card" key={project.id} onClick={() => open(project.id)}><strong>{project.name}</strong><p>{project.description || 'No description added.'}</p><Badge>{project.role}</Badge><small>{project.timezone} · {project.currency}</small></button>)}</div>}
    {workspace.can_manage && <section className="panel form-panel"><h2>Create a project</h2><form onSubmit={event => { event.preventDefault(); void action.run(() => api<Project>(base, 'POST', { name, description, timezone, currency: 'USD' }), value => { setName(''); state.refresh(); open(value.id); }); }}>
      <TextField label="New project name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} />
      <TextArea label="Description" maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} />
      <TextField label="New project timezone" required maxLength={80} value={timezone} onChange={e => setTimezone(e.target.value)} /><Submit pending={action.pending}>Create project</Submit></form></section>}
  </>;
}

function WorkspaceDetail({ workspaceId, back }: { workspaceId: string; back: () => void }) {
  const state = useResource<Workspace>(`/api/v1/workspaces/${workspaceId}`);
  const [tab, setTab] = useState<'projects' | 'members' | 'invitations' | 'audit'>('projects'); const [project, setProject] = useState<string | null>(()=>projectSelection().workspace===workspaceId?projectSelection().project:null);
  if (project) return <ProjectDetail workspaceId={workspaceId} projectId={project} onBack={() => { setProject(null); state.refresh(); }} />;
  return <><button className="button back-button" onClick={back}>← All workspaces</button>
    {state.loading || state.error || !state.data ? <Loading error={state.error} refresh={state.refresh} /> : <>
      <div className="page-heading"><div><p className="eyebrow">Workspace</p><h1>{state.data.name}</h1><p>Your role: {state.data.role}</p></div><button className="button" onClick={state.refresh}>Refresh workspace</button></div>
      <div className="tab-buttons" aria-label="Workspace sections"><button className={`button ${tab === 'projects' ? 'primary' : ''}`} onClick={() => setTab('projects')}>Projects</button>
        {state.data.can_manage && (['members', 'invitations', 'audit'] as const).map(value => <button className={`button ${tab === value ? 'primary' : ''}`} key={value} onClick={() => setTab(value)}>{value === 'members' ? 'Team access' : value === 'invitations' ? 'Invitations' : 'History'}</button>)}</div>
      {tab === 'projects' || !state.data.can_manage ? <ProjectList workspace={state.data} open={setProject} /> : tab === 'members' ? <Members path={`/api/v1/workspaces/${workspaceId}/members`} workspace owner={state.data.role === 'owner'} />
        : tab === 'invitations' ? <Invitations workspaceId={workspaceId} owner={state.data.role === 'owner'} /> : <Audit workspaceId={workspaceId} />}
    </>}
  </>;
}

export function Projects() {
  const state = useResource<Items<Workspace>>('/api/v1/workspaces'); const [selected, setSelected] = useState<string | null>(()=>projectSelection().workspace);
  const [name, setName] = useState(''); const action = useAction();
  if (selected) return <WorkspaceDetail key={selected} workspaceId={selected} back={() => { setSelected(null); state.refresh(); }} />;
  return <><div className="page-heading"><div><p className="eyebrow">Team collaboration</p><h1>Your workspaces</h1><p>Keep each team's members and projects separate.</p></div><button className="button" onClick={state.refresh}>Refresh workspaces</button></div>
    <Feedback error={action.error} />{state.loading || state.error ? <Loading error={state.error} refresh={state.refresh} /> : <div className="project-grid">
      {!state.data?.items.length && <section className="panel"><h2>No active workspace memberships</h2><p>Create a workspace or ask an administrator for an invitation.</p></section>}
      {state.data?.items.map(workspace => <button className="project-card" key={workspace.id} onClick={() => setSelected(workspace.id)}><strong>{workspace.name}</strong><p>Open projects and team access</p><Badge>{workspace.role}</Badge></button>)}</div>}
    <section className="panel form-panel"><h2>Create another workspace</h2><p>You become its first owner. This does not grant access to anyone else's workspace.</p><form onSubmit={event => { event.preventDefault(); void action.run(() => api<Workspace>('/api/v1/workspaces', 'POST', { name }), workspace => { setName(''); state.refresh(); setSelected(workspace.id); }); }}>
      <TextField label="New workspace name" required minLength={2} maxLength={120} value={name} onChange={e => setName(e.target.value)} /><Submit pending={action.pending}>Create workspace</Submit></form></section></>;
}
