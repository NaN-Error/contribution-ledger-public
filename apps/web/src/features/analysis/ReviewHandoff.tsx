import { useState } from 'react';
import { SourceTiming } from './SourceTiming.js';
import { api } from '../../lib/api.js';
import { useResource } from '../../hooks/useApi.js';
import { Feedback, Loading, SelectField, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { ScopeEditor } from '../work-packages/ScopeEditor.js';
import { WorkPackageDetail as PackageView } from '../work-packages/WorkPackageDetail.js';
import { unitInput } from '../../lib/planning.js';
import type { WorkOptions, WorkPackageDetail, ScopeDraft } from '../../lib/workPackages.js';
import type { AnalysisOutcome, ManualEntry } from '../../lib/analysis.js';

interface Options {batches:{id:string;title:string;start_at:string;end_before:string}[];notice:string}
interface Preview extends WorkOptions {
  review_hash:string;blockers:string[];
  document:{report_id:string;draft_version:number;batch_id:string;batch_version:number;notice:string;work_category:string;outcome:AnalysisOutcome;manual_entry:ManualEntry|null;
    identities:{external_key:string;name:string;usernames:string[];aliases:{key:string;name:string;username:string|null}[];suggested_user_id:string|null}[];
    work_window:{start_at:string;end_before:string};report_omissions:string[]};
}
type Resolution={external_key:string;disposition:'participant'|'context_only';user_id:string|null;reason:string};

function PreparedScope({root,view,done,cancel}:{root:string;view:Preview;done:(id:string)=>void;cancel:()=>void}) {
  const [mapping,setMapping]=useState<Record<string,string>>(()=>Object.fromEntries(view.document.identities.map(i=>[i.external_key,i.suggested_user_id||''])));
  const [reason,setReason]=useState('');const [shared,setShared]=useState(false);const [scope,setScope]=useState<ScopeDraft|null>(null);const [error,setError]=useState<string|null>(null);
  const doc=view.document;const proposal=doc.outcome.proposal;
  const identities=():Resolution[]=>doc.identities.map(i=>({external_key:i.external_key,disposition:mapping[i.external_key]==='context'?'context_only':'participant',
    user_id:mapping[i.external_key]==='context'?null:mapping[i.external_key],reason}));
  return <section className="panel"><h3>Review this contribution for a work package</h3><p>{doc.notice}</p>
    <p>Work window: {doc.work_window.start_at} through {doc.work_window.end_before} (end excluded). This preview pins draft revision {doc.draft_version}.</p>
    <p>Analysis category: {doc.outcome.category}. Approved policy category: {doc.work_category}.</p>
    <details><summary>Exact evidence and findings to share with project participants</summary><p>{doc.outcome.summary}</p>
      {doc.outcome.findings?.map(f=><p key={f.label}><strong>{f.label}:</strong> {f.text}</p>)}
      {doc.manual_entry&&<p>Manual performed time: {doc.manual_entry.performed_at}. {doc.manual_entry.description}</p>}
      {doc.outcome.sources.map(s=><article key={s.id}><h4>{s.title}</h4>{s.url&&<a href={s.url} target="_blank" rel="noreferrer">Open captured source address</a>}<SourceTiming source={s}/><pre>{s.excerpt||'No source text was captured.'}</pre><p className="small">{s.content_hash} {s.omissions.join('; ')}</p></article>)}
      <ul>{[...doc.outcome.limitations,...doc.report_omissions].map((s,n)=><li key={n}>{s}</li>)}</ul>
    </details>
    {!!view.blockers.length?<><ul role="alert">{view.blockers.map(b=><li key={b}>{b}</li>)}</ul><button className="button" onClick={cancel}>Close package preparation</button></>:scope?<>
      <p>Recipient mapping and exact proposed units are pinned to this review. Enter measurable acceptance criteria and required evidence below.</p>
      <button className="button" onClick={()=>setScope(null)}>Back to identity review</button>
      <ScopeEditor root={root.replace(/\/analysis$/,'')+'/work-packages'} options={{...view,can_create:true,notice:doc.notice}} initialDraft={scope} onCancel={cancel} onSaved={p=>done(p.id)}
        submitCreate={async(planned,allocation,scopeReason)=>{
          const result=await api<{package_id:string}>(root+'/handoff','POST',{request_id:crypto.randomUUID(),expected_version:doc.draft_version,
            report_id:doc.report_id,outcome_id:doc.outcome.id,batch_id:doc.batch_id,expected_batch_version:doc.batch_version,
            reviewed_hash:view.review_hash,project_sharing_confirmed:shared,identities:identities(),allocation_id:allocation.id,
            expected_allocation_version:allocation.version,scope:planned,reason:scopeReason});
          return api<WorkPackageDetail>(root.replace(/\/analysis$/,'')+'/work-packages/'+result.package_id);
        }}/>
    </>:<form onSubmit={e=>{e.preventDefault();setError(null);try{
        const resolutions=identities();if(resolutions.some(i=>i.disposition==='participant'&&!i.user_id))throw new Error('Resolve every identity before continuing.');
        if(!shared)throw new Error('Review and confirm project-visible evidence sharing before continuing.');
        const weights:Record<string,number>={};
        for(const entry of proposal?.entries||[]){if(!entry.atoms)continue;const uid=mapping[entry.contributor_key];if(!uid||uid==='context')throw new Error('A positive proposed recipient needs an explicit project participant.');weights[uid]=(weights[uid]||0)+entry.atoms;}
        const title=doc.outcome.title.slice(0,120);const outcome=doc.outcome.summary.slice(0,2000);
        setScope({title,outcome,criteria:'',evidence:'Inspect the pinned source excerpts, recorded limitations and participant evidence against the acceptance criteria.',
          coordinator:view.my_user_id,intended:[...new Set(resolutions.filter(r=>r.disposition==='participant').map(r=>r.user_id!))],
          deliverables:[{id:crypto.randomUUID(),title,outcome,criteria:'',evidence:'Inspect the pinned findings and source evidence against these specific criteria.',units:unitInput(proposal!.proposed_atoms),
            mode:'units',entries:Object.entries(weights).sort(([a],[b])=>a.localeCompare(b)).map(([uid,atoms])=>({key:crypto.randomUUID(),user_id:uid,role:'other',amount:unitInput(atoms)}))}]});
      }catch(err){setError(err instanceof Error?err.message:String(err));}}}>
      <Feedback error={error}/><p>Map each observed identity to a current participant, or explicitly mark it as context with no proposed credit. Names and emails are not matched automatically.</p>
      {doc.identities.map(i=><SelectField key={i.external_key} label={'Review identity: '+i.name} required value={mapping[i.external_key]} onChange={e=>setMapping(old=>({...old,[i.external_key]:e.target.value}))}>
        <option value="">Choose an explicit disposition</option><option value="context">Context only — no proposed credit</option>{view.participants.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name} · {p.role}</option>)}</SelectField>)}
      <TextArea label="Reason for these identity dispositions" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={shared} onChange={setShared}>I reviewed these precise findings, identities and evidence excerpts and permit sharing them with this project's participants.</ConfirmCheck>
      <div className="button-row"><button className="button primary" type="submit">Continue to acceptance criteria and scope</button><button className="button" type="button" onClick={cancel}>Close package preparation</button></div>
    </form>}
  </section>;
}

function ExistingPackage({root,id,close}:{root:string;id:string;close:()=>void}) {
  const base=root.replace(/\/analysis$/,'')+'/work-packages';const options=useResource<WorkOptions>(base+'/options');
  if(options.loading||options.error||!options.data)return <Loading error={options.error} refresh={options.refresh}/>;
  return <PackageView root={base} packageId={id} options={options.data} onBack={close}/>;
}

export function ReviewHandoff({root,reportId,outcome,refresh}:{root:string;reportId:string;outcome:AnalysisOutcome;refresh:()=>void}) {
  const [open,setOpen]=useState(false);const [batch,setBatch]=useState('');const [created,setCreated]=useState<string|null>(null);
  const options=useResource<Options>(open?root+'/handoff/options':null);
  const preview=useResource<Preview>(open&&batch?root+'/handoff/preview?'+new URLSearchParams({report_id:reportId,outcome_id:outcome.id,batch_id:batch}):null);
  if(created)return <ExistingPackage root={root} id={created} close={()=>{setCreated(null);setOpen(false);refresh();}}/>;
  if(outcome.handoff)return <button className="button primary" onClick={()=>setCreated(outcome.handoff!.package_id)}>Open the preserved review package</button>;
  if(!open)return <button className="button primary" onClick={()=>setOpen(true)}>Prepare this contribution for human review</button>;
  return <section className="panel"><h3>Choose the approved historical scope</h3><p>Use Historical review to define and approve a scope, then Milestones to allocate the exact proposed units. Analysis remains usable before this planning step.</p>
    <button className="button" onClick={()=>{options.refresh();preview.refresh();}}>Refresh review preparation</button>
    {options.loading||options.error?<Loading error={options.error} refresh={options.refresh}/>:<SelectField label="Approved historical scope" required value={batch} onChange={e=>setBatch(e.target.value)}>
      <option value="">Choose an approved historical scope</option>{options.data?.batches.map(b=><option key={b.id} value={b.id}>{b.title} · {b.start_at.slice(0,10)} through {b.end_before.slice(0,10)}</option>)}</SelectField>}
    {options.data&&!options.data.batches.length&&<p>No approved historical scope is available yet. Open Historical review to prepare one.</p>}
    {batch&&(preview.loading||preview.error?<Loading error={preview.error} refresh={preview.refresh}/>:preview.data&&<PreparedScope key={preview.data.review_hash} root={root} view={preview.data}
      done={id=>{setCreated(id);setOpen(false);}} cancel={()=>setOpen(false)}/>)}
    {!batch&&<button className="button" onClick={()=>setOpen(false)}>Close package preparation</button>}
  </section>;
}
