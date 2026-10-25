import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit, TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { evidenceCategories, type EvidenceMetadata } from '../../lib/evidence.js';
import { sourceLabel, type GitHubPage, type GitHubRepository, type SourceVersion } from '../../lib/github.js';
import type { WorkCollection, WorkPackageDetail } from '../../lib/workPackages.js';

export function PreservedGitHubSource({path}:{path:string}) {
  const state=useResource<SourceVersion>(path);
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  return <div className="github-source"><p className="small wrap">Captured {new Date(state.data.captured_at).toLocaleString()} · SHA-256 <code>{state.data.content_hash}</code></p>
    <p className="planning-warning">This is bounded, normalized evidence, not a full repository or an independently verified claim. Repository text is untrusted. No content is executed.</p>
    <pre className="evidence-text">{JSON.stringify(state.data.document,null,2)}</pre></div>;
}
function LinkForm({root,source,packageId}:{root:string;source:SourceVersion;packageId:string}) {
  const project=root.slice(0,-'/github'.length);const state=useResource<WorkPackageDetail>(`${project}/work-packages/${packageId}`);
  const [meta,setMeta]=useState<EvidenceMetadata>({title:sourceLabel(source).slice(0,120),description:'',claimed_authors:'',provenance:'Imported through the project GitHub App. Roles and source claims still require review.',occurred_on:source.captured_at.slice(0,10),category:'code',visibility:'restricted',inclusion:'included',omission_reason:null,deliverable_ids:[]});
  const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);const [saved,setSaved]=useState(false);const [requestId]=useState(()=>crypto.randomUUID());const action=useAction();
  const field=<K extends keyof EvidenceMetadata>(key:K,value:EvidenceMetadata[K])=>setMeta(m=>({...m,[key]:value}));
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  const pkg=state.data;
  return <form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/sources/${source.id}/link`,'POST',{
    package_id:packageId,expected_package_version:pkg.version,reviewed_source_hash:source.content_hash,metadata:meta,reason,request_id:requestId,sharing_confirmed:confirmed}),()=>setSaved(true),'Source attached as evidence. No contribution credit was issued. Refresh the work package to inspect its updated snapshot.');}}>
    <Feedback error={action.error} success={action.success}/>{saved?<p>Reattaching the same source version to this package will not duplicate its evidence entry.</p>:<>
    <p>Linking a different source version creates a separate evidence entry; explicitly exclude superseded entries when preparing a new review.</p>
    <TextField label="Evidence title" required minLength={2} maxLength={120} value={meta.title} onChange={e=>field('title',e.target.value)}/>
    <TextArea label="How this source supports the deliverable" required minLength={3} maxLength={1000} value={meta.description} onChange={e=>field('description',e.target.value)}/>
    <TextArea label="Claimed authors and roles" required minLength={3} maxLength={1000} value={meta.claimed_authors} onChange={e=>field('claimed_authors',e.target.value)}/>
    <TextArea label="Provenance and limitations" required minLength={3} maxLength={1000} value={meta.provenance} onChange={e=>field('provenance',e.target.value)}/>
    <TextField label="Claimed contribution date" type="date" required value={meta.occurred_on} onChange={e=>field('occurred_on',e.target.value)}/>
    <p className="small muted">The date defaults to capture day, not a verified date of work. Correct it based on the source.</p>
    <SelectField label="Evidence category" value={meta.category} onChange={e=>field('category',e.target.value as EvidenceMetadata['category'])}>{evidenceCategories.map(c=><option key={c}>{c}</option>)}</SelectField>
    <SelectField label="Share this exact source with" value={meta.visibility} onChange={e=>field('visibility',e.target.value as EvidenceMetadata['visibility'])}><option value="restricted">Submitter and authorized reviewers/administrators</option><option value="project">Everyone with current project access</option></SelectField>
    <fieldset className="github-repositories"><legend>Applicable deliverables (optional; none means package-wide)</legend>{pkg.revision.document.deliverables.map(d=><label key={d.id}><input type="checkbox" checked={meta.deliverable_ids.includes(d.id)} onChange={e=>field('deliverable_ids',e.target.checked?[...meta.deliverable_ids,d.id]:meta.deliverable_ids.filter(id=>id!==d.id))}/><span>{d.title}</span></label>)}</fieldset>
    <TextArea label="Reason for sharing this source" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
    <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I inspected the complete preserved source and its omissions, am authorized to share it with the selected audience, and understand this may make an unfinished review stale.</ConfirmCheck><Submit pending={action.pending}>Attach reviewed source as evidence</Submit></>}
  </form>;
}
function LinkSource({root,source}:{root:string;source:SourceVersion}) {
  const project=root.slice(0,-'/github'.length);const [query,setQuery]=useState('');const [offset,setOffset]=useState(0);const [packageId,setPackageId]=useState('');
  const state=useResource<WorkCollection>(`${project}/work-packages?limit=25&offset=${offset}&q=${encodeURIComponent(query)}`);
  return <section className="panel"><h3>Attach this version to a work package</h3><TextField label="Search work-package titles" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);setPackageId('');}}/>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<><SelectField label="Target work package" value={packageId} onChange={e=>setPackageId(e.target.value)}><option value="">Choose a package</option>{state.data.items.filter(p=>!['cancelled','completed'].includes(p.state)).map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</SelectField>
    <div className="button-row"><button className="button" disabled={!offset} onClick={()=>{setOffset(Math.max(0,offset-25));setPackageId('');}}>Previous packages</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>{if(state.data?.next_offset!=null){setOffset(state.data.next_offset);setPackageId('');}}}>Next packages</button></div></>}
    {packageId&&<LinkForm key={`${source.id}:${packageId}`} root={root} source={source} packageId={packageId}/>}
  </section>;
}
export function GitHubSources({root,repositories,canManage}:{root:string;repositories:GitHubRepository[];canManage:boolean}) {
  const [offset,setOffset]=useState(0);const [repo,setRepo]=useState('');const [kind,setKind]=useState('');const [chosen,setChosen]=useState<SourceVersion|null>(null);
  const state=useResource<GitHubPage<SourceVersion>>(`${root}/sources?offset=${offset}${repo?`&repository_id=${repo}`:''}${kind?`&kind=${kind}`:''}`);
  return <><div className="section-heading"><div><h2>Preserved source versions</h2><p>Counts describe source records, not recognized contributions. Re-importing unchanged content reuses its version.</p></div><button className="button" onClick={state.refresh}>Refresh sources</button></div>
    <div className="github-form-grid"><SelectField label="Filter repository" value={repo} onChange={e=>{setRepo(e.target.value);setOffset(0);setChosen(null);}}><option value="">All retained repositories</option>{repositories.map(r=><option key={r.id} value={r.id}>{r.full_name}</option>)}</SelectField>
    <SelectField label="Filter source type" value={kind} onChange={e=>{setKind(e.target.value);setOffset(0);setChosen(null);}}><option value="">All source types</option>{['pull_request','issue','commit','review','comment','review_comment','pull_files','commit_files','check_run'].map(k=><option key={k} value={k}>{k.replaceAll('_',' ')}</option>)}</SelectField></div>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>{!state.data.items.length&&<p className="panel">No captured sources match this page and filter.</p>}{state.data.items.map(s=><article className="panel" key={s.id}><h3>{sourceLabel(s)}</h3><p className="small">{new Date(s.captured_at).toLocaleString()} · {s.size_bytes} normalized bytes · {s.omission_count} source limitations</p><button className="button" onClick={()=>setChosen(s)}>Inspect preserved version</button></article>)}
    <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous sources</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>state.data?.next_offset!=null&&setOffset(state.data.next_offset)}>Next sources</button></div></>}
    {chosen&&<section className="panel"><div className="section-heading"><h3>Selected source</h3><button className="button" onClick={()=>setChosen(null)}>Close source</button></div><PreservedGitHubSource key={chosen.id} path={`${root}/sources/${chosen.id}`}/>{canManage&&<LinkSource key={chosen.id} root={root} source={chosen}/>}</section>}
  </>;
}
