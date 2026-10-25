import {useState} from 'react';
import {TextField,Badge} from '../../components/shared.js';
import {Feedback,Loading,Submit} from '../../components/forms.js';
import {ConfirmCheck} from '../../components/planning.js';
import {useAction,useResource} from '../../hooks/useApi.js';
import {api} from '../../lib/api.js';
import type {GitHubRepository,GitHubPage} from '../../lib/github.js';
import {humanLabel} from '../../lib/planning.js';
import {displayInstant,retryReady,summaryCounts,syncPayload,jobActionPayload,type SyncOverview,type SyncConfiguration,type SyncJob,type Delivery,type Observation} from '../../lib/sync.js';

function Configuration({root,repo,config,manage,operatorEnabled,refresh}:{root:string;repo:GitHubRepository;config:SyncConfiguration|null;manage:boolean;operatorEnabled:boolean;refresh:()=>void}) {
  const action=useAction();const [enabled,setEnabled]=useState(config?.enabled??false);
  const [interval,setInterval]=useState(String(config?.interval_minutes??360));const [lookback,setLookback]=useState(String(config?.lookback_days??7));
  const [requests,setRequests]=useState(String(config?.request_limit??200));const [entities,setEntities]=useState(String(config?.entity_limit??50));
  const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);
  return <article className="panel"><div className="section-heading"><h3>{repo.full_name}</h3><Badge tone={config?.enabled?'good':'muted'}>{config?.enabled?'Scheduled':'Paused / not enabled'}</Badge></div>
    <p>Last finished capture: {displayInstant(config?.last_success_at??null)}. This includes captures with omissions.</p>
    <p className="small">Last capture without recorded omissions: {displayInstant(config?.last_complete_at??null)}. This is not proof of complete GitHub history.</p>
    <p className="small">Next eligible run: {config?.enabled?displayInstant(config.next_due_at):'Not scheduled'} · Active import: {config?.active_import_id?.slice(0,8)||'None'}</p>
    {config?.last_error&&<p className="planning-warning">{humanLabel(config.last_error)}</p>}
    {repo.retry_not_before&&!retryReady(repo.retry_not_before)&&<p className="planning-warning">Repository cooldown until {displayInstant(repo.retry_not_before)}. Creating another job cannot bypass it.</p>}
    {!repo.enabled&&<p className="planning-warning">The repository is disabled. A new verified connection is required before enabling it again.</p>}
    {manage&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/sync/${repo.id}`,'PUT',syncPayload(config?.version??0,enabled,{interval,lookback,requests,entities},reason,confirmed)),refresh);}}>
      <Feedback error={action.error} success={action.success}/>
      <ConfirmCheck checked={enabled} onChange={setEnabled} disabled={action.pending||((!operatorEnabled||!repo.enabled)&&!enabled)}>Enable recurring read-only synchronization for this selected repository.</ConfirmCheck>
      <div className="github-form-grid"><TextField label="Interval in minutes" required type="number" min={60} max={10080} value={interval} onChange={e=>setInterval(e.target.value)}/>
      <TextField label="Updated-activity lookback in days" required type="number" min={1} max={90} value={lookback} onChange={e=>setLookback(e.target.value)}/>
      <TextField label="Data-request budget per run" required type="number" min={10} max={1000} value={requests} onChange={e=>setRequests(e.target.value)}/>
      <TextField label="Maximum per root type per run" required type="number" min={1} max={200} value={entities} onChange={e=>setEntities(e.target.value)}/></div>
      <p className="small">Signed events provide hints. Runs refetch API state, scan recently updated issues/PRs, and revisit up to 20 known older root records. Bounds and inaccessible history may leave gaps. GitHub authority still needs renewal within 24 hours.</p>
      <TextField label="Reason for changing or requesting synchronization" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I reviewed these limits. Saving cancels any unfinished run under the previous settings. Captured versions and approved credit are preserved.</ConfirmCheck>
      <div className="button-row"><Submit pending={action.pending}>Save synchronization settings</Submit>
      {config?.enabled&&<button className="button" type="button" disabled={action.pending||!confirmed||!!config.active_import_id||!operatorEnabled} onClick={()=>void action.run(()=>api(`${root}/sync/${repo.id}/request`,'POST',{expected_version:config.version,reviewed:confirmed,reason}),refresh)}>Request next eligible run</button>}</div>
    </form>}
  </article>;
}
function Job({root,job,manage,refresh}:{root:string;job:SyncJob;manage:boolean;refresh:()=>void}) {
  const action=useAction();const [reason,setReason]=useState('');
  const command=(name:'resume'|'cancel')=>void action.run(()=>api(`${root}/imports/${job.id}/${name}`,'POST',jobActionPayload(job.version,reason)),refresh);
  return <article className="panel"><div className="section-heading"><h3>{job.capture_mode==='sync'?'Synchronization':'Historical import'} {job.id.slice(0,8)}</h3><Badge tone={job.state==='completed'?'good':'warning'}>{humanLabel(job.state)}</Badge></div>
    <p>{job.tasks.done||0} fetches processed · {job.tasks.pending||0} pending · {job.data_requests}/{job.request_limit} data requests.</p>
    <p className="small">Last broker publication: {displayInstant(job.dispatch?.last_published_at??null)} · Publication attempts: {job.dispatch?.publish_attempts??0}</p>
    {job.dispatch?.publish_error&&<p className="planning-warning">{humanLabel(job.dispatch.publish_error)}. The durable job remains in the database; the scheduler retries publication.</p>}
    {job.error_code&&<p className="planning-warning">{humanLabel(job.error_code)}. Next eligible attempt: {displayInstant(job.next_attempt_at)}.</p>}
    {job.dead_letter&&<p className="planning-warning">Retry limit or non-retryable failure. Review before resuming; five failures require a new bounded run after the cooldown. An operator cannot manufacture GitHub authorization by retrying.</p>}
    <details><summary>Recorded omissions ({job.omissions.length})</summary><p className="small">{job.scope}</p>{job.omissions.map((o,i)=><p className="small wrap" key={i}>{o}</p>)}</details>
    {manage&&['queued','running','paused','failed'].includes(job.state)&&<form onSubmit={e=>{e.preventDefault();command('cancel');}}><Feedback error={action.error}/>
      <TextField label="Reason for job action" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <div className="button-row"><Submit pending={action.pending}>{job.capture_mode==='sync'?'Cancel job and pause its synchronization':'Cancel historical import'}</Submit>
        {['paused','failed'].includes(job.state)&&<button className="button" type="button" disabled={action.pending||job.failures>=5||!retryReady(job.next_attempt_at)||reason.trim().length<8} onClick={()=>command('resume')}>Resume after reviewing failure</button>}</div>
      <p className="small">Cancellation cannot retract a request already sent, but stale responses cannot be committed. A resumed failed run does not silently re-enable its recurring schedule.</p></form>}
  </article>;
}
function Pages({offset,next,setOffset,label}:{offset:number;next:number|null;setOffset:(n:number)=>void;label:string}) {
  return <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous {label}</button><button className="button" disabled={next===null} onClick={()=>next!==null&&setOffset(next)}>Next {label}</button></div>;
}
export function GitHubSync({root,repositories}:{root:string;repositories:GitHubRepository[]}) {
  const overview=useResource<SyncOverview>(`${root}/sync`);const [tab,setTab]=useState<'settings'|'jobs'|'deliveries'|'observations'>('settings');
  const [offset,setOffset]=useState(0);const list=useResource<GitHubPage<SyncJob|Delivery|Observation>>(tab==='settings'?null:`${root}/${tab}?offset=${offset}`);
  const refresh=()=>{overview.refresh();list.refresh();};
  if(overview.loading||overview.error||!overview.data)return <Loading error={overview.error} refresh={overview.refresh}/>;
  const data=overview.data;
  return <><div className="section-heading"><div><h2>Synchronization and recovery</h2><p>{data.notice}</p></div><button className="button" onClick={refresh}>Refresh synchronization status</button></div>
    <section className="panel"><p>Scheduler deployment: {data.sync_configured?'enabled':'disabled'} · Signed webhook intake: {data.webhook_configured?'enabled':'disabled'}</p>
      <p className="small">Jobs: {summaryCounts(data.job_counts)}</p><p className="small">Repository delivery signals: {summaryCounts(data.delivery_counts)}</p>
      {data.heartbeat.length?data.heartbeat.map(h=><p className="small" key={h.component}>{h.component}: {humanLabel(h.status)} · {displayInstant(h.last_seen_at)}{h.stale?' · no recent heartbeat':''}</p>):<p>No worker or scheduler heartbeat has been recorded.</p>}
      <p className="small">An idle worker may not have a recent task heartbeat. Missing heartbeats do not prove a service is down; inspect deployment logs.</p>
      {data.linked_sources_with_new_observations>0&&<p className="planning-warning">{data.linked_sources_with_new_observations} pinned source links have a newer or unavailable observation. Inspect Source versions before explicitly attaching a replacement. Previous evidence, unfinished reviews of that unchanged snapshot, and finalized credit are not overwritten.</p>}
      {!data.sync_configured&&<p>Use <code>docs/github_sync.md</code> for the optional local worker/broker deployment. It needs an authorized GitHub connection. Normal startup keeps it disabled.</p>}
    </section>
    <div className="tab-buttons" aria-label="Synchronization sections">{(['settings','jobs','deliveries','observations'] as const).map(t=><button className={`button ${tab===t?'primary':''}`} key={t} aria-pressed={tab===t} onClick={()=>{setOffset(0);setTab(t);}}>{t==='settings'?'Repository schedules':t==='jobs'?'Jobs and retries':t==='deliveries'?'Signed deliveries':'Latest observations'}</button>)}</div>
    {tab==='settings'?repositories.length?repositories.map(repo=><Configuration key={`${repo.id}:${data.configurations.find(c=>c.repository_id===repo.id)?.version??0}`} root={root} repo={repo} config={data.configurations.find(c=>c.repository_id===repo.id)??null} manage={data.can_manage} operatorEnabled={data.sync_configured} refresh={refresh}/>):<p className="panel">Connect and select a repository first.</p>
    :list.loading||list.error||!list.data?<Loading error={list.error} refresh={list.refresh}/>:<>
      {!list.data.items.length&&<p className="panel">No {tab} on this page.</p>}
      {tab==='jobs'?(list.data.items as SyncJob[]).map(job=><Job key={`${job.id}:${job.version}`} root={root} job={job} manage={data.can_manage} refresh={refresh}/>)
      :tab==='deliveries'?(list.data.items as Delivery[]).map(d=><article className="panel" key={d.id}><h3>{humanLabel(d.event)} {d.action&&`· ${humanLabel(d.action)}`}</h3><p>{humanLabel(d.state)} · {displayInstant(d.received_at)}</p><p className="small wrap">Delivery: {d.delivery_id} · Body fingerprint: <code>{d.payload_hash}</code></p><p className="small">{humanLabel(d.note)} · {d.target_count} routing hints · Import: {d.import_id?.slice(0,8)||'None'}</p><p className="small">The raw event body is not stored. This record is a signal, not evidence of accepted work.</p></article>)
      :(list.data.items as Observation[]).map(o=><article className="panel" key={o.id}><h3>{humanLabel(o.kind)} · {o.remote_key}</h3><p>{humanLabel(o.state)} · observed {displayInstant(o.observed_at)}</p><p className="small wrap">Preserved source ID: {o.source_id||'None'} · Remote update: {displayInstant(o.remote_updated_at)}</p><p className="small">Unavailable now does not erase a previous capture or make its contribution zero.</p></article>)}
      <Pages offset={offset} next={list.data.next_offset} setOffset={setOffset} label={tab}/>
    </>}
  </>;
}
