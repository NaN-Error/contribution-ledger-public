import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { categories, humanLabel, type Category } from '../../lib/planning.js';
import { historicalCommand, boundedHistoricalBody, makeCandidateDocument, questionLines,
  type BatchDetail, type Candidate, type CandidateDocument, type IdentityResolution, type HistoricalResult } from '../../lib/reconstruction.js';

export function CandidateEditor({base,batch,candidate,done,cancel}:{base:string;batch:BatchDetail;candidate?:Candidate;done:()=>void;cancel:()=>void}){
  const [title,setTitle]=useState(candidate?.document.title??'');const [category,setCategory]=useState<Category>(candidate?.document.category??'art');
  const [summary,setSummary]=useState(candidate?.document.summary??'');const [questions,setQuestions]=useState(candidate?.document.unresolved_questions.join('\n')??'');
  const [resolutions,setResolutions]=useState<IdentityResolution[]>(candidate?.document.identity_resolutions??[]);const [reason,setReason]=useState('');const action=useAction();
  function update(key:string,value:Partial<IdentityResolution>,remove=false){setResolutions(old=>remove?old.filter(x=>x.external_key!==key):[...old.filter(x=>x.external_key!==key),{external_key:key,disposition:'context_only',user_id:null,reason:'',...old.find(x=>x.external_key===key),...value}]);}
  return <section className="panel"><div className="section-heading"><h3>{candidate?'Review candidate outcome':'Add missing non-code or other work'}</h3><button className="button" disabled={action.pending} onClick={cancel}>Close candidate editor</button></div>
    <p>These are claims and grouping decisions, not accepted work. Clear a question only after reviewing it. Identity suggestions never assign contribution units.</p>
    <Feedback error={action.error}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>{
      const document:CandidateDocument=makeCandidateDocument({title,category,summary,unresolved_questions:questionLines(questions),identity_resolutions:resolutions});
      return api<HistoricalResult>(base+(candidate?`/candidates/${candidate.id}/revisions`:'/candidates'),'POST',boundedHistoricalBody({...historicalCommand(batch.version,reason),document}));
    },done);}}><fieldset disabled={action.pending}>
    <TextField label="Candidate title" value={title} onChange={e=>setTitle(e.target.value)} required minLength={2} maxLength={120}/>
    <SelectField label="Contribution category" value={category} onChange={e=>setCategory(e.target.value as Category)}>{categories.map(x=><option key={x} value={x}>{humanLabel(x)}</option>)}</SelectField>
    <TextArea label="Useful historical outcome" required minLength={8} maxLength={2000} value={summary} onChange={e=>setSummary(e.target.value)}/>
    <TextArea label="Unresolved questions — one per line, empty when resolved" value={questions} onChange={e=>setQuestions(e.target.value)} rows={3}/>
    {candidate?.identities.map(identity=>{const value=resolutions.find(x=>x.external_key===identity.external_key);return <fieldset key={identity.external_key}><legend>Observed identity: {String(identity.display_name??identity.login??identity.external_key)}</legend>
      <p className="small">Claim key: {identity.external_key}. This may be an author, committer, reviewer, bot or contextual mention; it is not a verified recipient.</p>
      <SelectField label={`Disposition for ${identity.external_key}`} value={value?.disposition??''} onChange={e=>update(identity.external_key,{disposition:e.target.value as 'participant'|'context_only',user_id:e.target.value==='participant'?(identity.suggested_user_id??''):null},!e.target.value)}>
        <option value="">Unresolved</option><option value="participant">Identify a local participant</option><option value="context_only">Context only, not an asserted recipient</option></SelectField>
      {value?.disposition==='participant'&&<SelectField label={`Local participant for ${identity.external_key}`} required value={value.user_id??''} onChange={e=>update(identity.external_key,{user_id:e.target.value})}>
        <option value="">Choose explicitly</option>{batch.participants?.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name} · {p.role}</option>)}</SelectField>}
      {value&&<TextArea label={`Reason for ${identity.external_key}`} required minLength={8} maxLength={500} value={value.reason} onChange={e=>update(identity.external_key,{reason:e.target.value})}/>}</fieldset>;})}
    <TextArea label="Reason for candidate decision" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
    <Submit pending={action.pending}>Save candidate revision</Submit></fieldset></form></section>;
}
