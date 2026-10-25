import { useState } from 'react';
import { api } from '../../lib/api.js';
import { useAction } from '../../hooks/useApi.js';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit } from '../../components/forms.js';
import { repositoryLinks, type AnalysisOverview, type RepositoryConnection } from '../../lib/analysis.js';

const tokenHelp='https://github.com/settings/personal-access-tokens/new?name=Contribution%20Ledger&description=Read%20selected%20repository%20activity%20locally&expires_in=30&contents=read&issues=read&pull_requests=read&metadata=read';

export function PrivateConnection({root,data,urls,changed}:{root:string;data:AnalysisOverview;urls:string;changed:(connection:RepositoryConnection|null)=>void}) {
  const [method,setMethod]=useState(data.cli_available?'cli':'token');
  const [token,setToken]=useState('');const [confirmed,setConfirmed]=useState(false);
  const action=useAction();const c=data.connection;
  if(!data.private_reads_enabled)return <details><summary>Private repositories</summary><p>Direct private reads require a local installation with protected credential storage. The complete Windows Start.cmd package enables this. GitHub App imports remain available for configured team installations.</p></details>;
  return <details className="panel"><summary><strong>{c?.active?'GitHub connected as @'+c.username:'Connect GitHub for private repositories'}</strong></summary>
    <p>Use the links in the repository field above to select exactly which repositories this project may read. Connecting does not start analysis or share a report.</p>
    {c&&<p>{c.active?'Connected':'Disconnected or expired'} as @{c.username} · {c.repository_urls.length} selected repositories · local authorization expires {new Date(c.expires_at).toLocaleDateString()}.</p>}
    <Feedback error={action.error} success={action.success}/>
    <form aria-label="Connect private repositories" onSubmit={e=>{e.preventDefault();const value=token;setToken('');void action.run(()=>api<{connection:RepositoryConnection}>(root+'/connection','PUT',{expected_version:c?.version||0,method,...(method==='token'?{token:value}:{}),repository_urls:repositoryLinks(urls),access_confirmed:confirmed}),result=>{setConfirmed(false);changed(result.connection);},'GitHub connected. Select Connected GitHub account below, then analyze.');}}>
      <SelectField label="GitHub connection method" value={method} onChange={e=>{setMethod(e.target.value);setToken('');setConfirmed(false);}}>
        {data.cli_available&&<option value="cli">Use the GitHub CLI account signed in on this computer</option>}
        <option value="token">Use a fine-grained read-only token</option>
      </SelectField>
      {method==='token'?<><p><a href={tokenHelp} target="_blank" rel="noreferrer">Create a fine-grained GitHub token</a>. Choose Only select repositories, then the repositories you entered. Use read-only Contents, Issues, Pull requests and Metadata permissions.</p><TextField label="GitHub fine-grained token" type="password" autoComplete="off" required maxLength={256} value={token} onChange={e=>setToken(e.target.value)} hint="Saved encrypted in your local data folder. Never paste this into chat or a repository."/></>:<p>The app reads your existing github.com CLI login without saving its token. That account may have broader permissions; this program only sends read requests to the selected repositories. It does not install GitHub CLI or change your login.</p>}
      <label className="analysis-check"><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Allow this project to read the selected repositories using my GitHub access.</label>
      <Submit pending={action.pending} disabled={!urls.trim()}>{c?.active?'Update selected repositories or reconnect':'Connect GitHub'}</Submit>
    </form>
    {c?.active&&<button className="button" type="button" disabled={action.pending} onClick={()=>void action.run(()=>api<{connection:RepositoryConnection}>(root+'/connection/disconnect','POST',{expected_version:c.version}),result=>changed(result.connection),'Disconnected. Saved reports are preserved; revoke a saved token in GitHub separately if needed.')}>Disconnect GitHub</button>}
    <p className="small">Private captures remain available to this project's administrators and reviewers. Sharing with contributors requires a separate reviewed disclosure. No repository code is run and no private source is sent to an AI provider.</p>
  </details>;
}
