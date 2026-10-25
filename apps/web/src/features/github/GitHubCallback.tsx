import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, Submit } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { isProof, selectedRepositories, type GitHubCallback as Callback, type GitHubProof } from '../../lib/github.js';

export function GitHubCallback({ callback }:{callback:Callback|null}) {
  const [proof,setProof]=useState<GitHubProof|null>(null);const [selected,setSelected]=useState<number[]>([]);
  const [confirmed,setConfirmed]=useState(false);const [reason,setReason]=useState('');const [finished,setFinished]=useState(false);
  const action=useAction();const [attempted,setAttempted]=useState(false);
  return <section className="panel form-panel"><p className="eyebrow">External source authorization</p><h1>Connect verified repositories</h1>
    <p>This does not sign you into the ledger with GitHub or change your local account. Code and state were removed from the address bar; they are held only for this page's verification.</p>
    <Feedback error={action.error||callback?.error} success={action.success}/>
    {!callback && <p className="planning-warning">No pending callback is available. Start authorization again from your project's GitHub tab.</p>}
    {callback&&!callback.error&&!proof&&!finished&&<><button className="button primary" disabled={action.pending||attempted} onClick={()=>{
      setAttempted(true);void action.run(()=>api<unknown>('/api/v1/github/callback','POST',{code:callback.code,state:callback.state}),value=>{
        if(!isProof(value))throw new Error('The verified repository response was invalid.');setProof(value);
      });}}>Verify this GitHub authorization</button><p className="small muted">A failed or ambiguous exchange is not automatically repeated. Start a fresh authorization after an error.</p></>}
    {proof&&!finished&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api('/api/v1/github/connect','POST',{
        flow_id:proof.flow_id,reviewed_proof_hash:proof.proof_hash,repository_ids:selectedRepositories(proof,selected),
        sharing_confirmed:confirmed,reason}),()=>setFinished(true),'Repository selection was connected. Return to the project to create a bounded import.');}}>
      <p><strong>{proof.github_login}</strong> verified administrator access to the repositories below in <strong>{proof.account}</strong>.</p>
      <p className="small">Selection expires {new Date(proof.expires_at).toLocaleString()}.</p>
      <fieldset className="github-repositories"><legend>Repositories to share with this project</legend>{proof.repositories.map(repo=><label key={repo.github_id}>
        <input type="checkbox" checked={selected.includes(repo.github_id)} disabled={action.pending} onChange={e=>setSelected(values=>e.target.checked?[...values,repo.github_id]:values.filter(id=>id!==repo.github_id))}/>
        <span>{repo.full_name}<small>{repo.private?'Private repository':'Public repository'}</small></span></label>)}</fieldset>
      <p className="planning-warning">Raw imports are available to project administrators and reviewers. A later explicit evidence link can share a pinned source with other project members. Reauthorization replaces the selected repository set for this installation and cancels its unfinished old imports.</p>
      <TextField label="Reason for sharing these repositories" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I am authorized to share the selected repository data with this project. Imported activity must not automatically award credit.</ConfirmCheck>
      <Submit pending={action.pending}>Connect selected repositories</Submit>
    </form>}
    <p><a className="button" href="#projects">Return to workspaces</a></p>
  </section>;
}
