import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, Submit, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Project } from '../../lib/accounts.js';
import { authorizationURL, installationID, type GitHubConnection, type GitHubOverview } from '../../lib/github.js';
import { GitHubSync } from './GitHubSync.js';
import { GitHubImports } from './GitHubImports.js';
import { GitHubIdentities } from './GitHubIdentities.js';
import { GitHubSources } from './GitHubSources.js';

function Connection({root,connection,manage,refresh}:{root:string;connection:GitHubConnection;manage:boolean;refresh:()=>void}) {
  const action=useAction();const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);
  return <article className="panel"><h3>{connection.account} · installation {connection.installation_id}</h3><Badge tone={connection.enabled&&Date.parse(connection.verified_until)>Date.now()?'good':'warning'}>{connection.enabled?'Enabled (check expiry)':'Disconnected'}</Badge>
    <p>Verified as {connection.github_login}; authorization expires {new Date(connection.verified_until).toLocaleString()}.</p><p className="small">This is a time-limited permission snapshot. Reauthorize to renew it or change selected repositories. Current App installation access and the authorizer’s repository-admin role are rechecked before and after each worker step.</p>
    {manage&&connection.enabled&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/connections/${connection.id}/disconnect`,'POST',{expected_version:connection.version,reason,reviewed:confirmed}),refresh);}}>
    <Feedback error={action.error}/><TextField label="Reason for disconnecting this installation" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>Stop future imports and cancel unfinished jobs for this connection. Captured evidence remains protected and retained.</ConfirmCheck><Submit pending={action.pending}>Disconnect locally</Submit></form>}
  </article>;
}
function GitHubPanel({project}:{project:Project}) {
  const root=`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/github`;const state=useResource<GitHubOverview>(root);const action=useAction();
  const [tab,setTab]=useState<'connections'|'imports'|'sources'|'identities'|'sync'>('connections');const [installation,setInstallation]=useState('');const [reason,setReason]=useState('');
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  const data=state.data;
  return <><div className="section-heading"><div><p className="eyebrow">Evidence integration</p><h2>GitHub</h2><p>{data.notice}</p></div><button className="button" onClick={state.refresh}>Refresh connections</button></div>
    {!data.configured&&<section className="panel"><h3>GitHub is not configured</h3><p>The manual ledger remains usable. An operator must register a dedicated read-only GitHub App and mount its credentials using <code>docs/github_setup.md</code>. Do not paste App private keys or client secrets here or into chat.</p></section>}
    <div className="tab-buttons" aria-label="GitHub sections">{(['connections','imports','sources','identities','sync'] as const).map(t=><button key={t} className={`button ${tab===t?'primary':''}`} aria-pressed={tab===t} onClick={()=>setTab(t)}>{t==='connections'?'Connections':t==='imports'?'Historical imports':t==='sources'?'Source versions':t==='identities'?'Identity review':'Synchronization'}</button>)}</div>
    {tab==='connections'?<>{data.can_manage&&data.configured&&<section className="panel"><h3>Authorize or renew a connection</h3><p>Use the numeric installation ID from GitHub's App installation settings. The ID alone grants nothing: GitHub authorization must prove this account is an administrator of each selected repository.</p><Feedback error={action.error}/>
    <form onSubmit={e=>{e.preventDefault();void action.run(()=>api<{authorize_url:string}>(`${root}/authorize`,'POST',{installation_id:installationID(installation),reason}),value=>window.location.assign(authorizationURL(value.authorize_url)));}}>
      <TextField label="GitHub App installation ID" required inputMode="numeric" value={installation} onChange={e=>setInstallation(e.target.value)}/><TextArea label="Reason for sharing repositories with this project" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><Submit pending={action.pending}>Continue to GitHub authorization</Submit></form></section>}
    {!data.connections.length&&<p className="panel">No installation is connected yet.</p>}{data.connections.map(c=><Connection key={`${c.id}:${c.version}`} root={root} connection={c} manage={data.can_manage} refresh={state.refresh}/>)}
    <section className="panel"><h3>Selected repository history</h3>{data.repositories.length?data.repositories.map(r=><p key={r.id}><strong>{r.full_name}</strong> · {r.private?'private':'public'} · {r.enabled?'enabled':'disabled'}</p>):<p>No verified repositories.</p>}<p className="small">Disconnecting is not uninstalling the GitHub App or deleting retained source data. Repository code is never executed.</p></section>
    <section className="panel"><h3>Source-version counts</h3><p>{Object.entries(data.source_version_counts).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ')||'No captured versions.'}</p><p className="small">{data.metric_notice}</p><p className="small">{data.worker_notice}</p></section></>
    :tab==='imports'?<GitHubImports root={root} repositories={data.repositories} canManage={data.can_manage}/>:tab==='sources'?<GitHubSources root={root} repositories={data.repositories} canManage={data.can_manage}/>:tab==='identities'?<GitHubIdentities root={root}/>:<GitHubSync root={root} repositories={data.repositories}/>}
  </>;
}
export function GitHub({project}:{project:Project}) {
  if(!['admin','reviewer'].includes(project.role))return <section className="panel"><h2>GitHub source access</h2><p>The raw imported repository store is restricted to project administrators and reviewers. You can inspect exact source versions explicitly shared with you through work-package evidence.</p></section>;
  return <GitHubPanel project={project}/>;
}
