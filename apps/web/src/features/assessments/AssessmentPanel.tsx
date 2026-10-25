import { useState } from 'react';
import { Feedback,Loading,SelectField,Submit,TextArea } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useResource,useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatMicroUSD,type Page } from '../../lib/ai.js';
import { parseExcludedPaths,assessmentRequest,planStatus,type AssessmentOptions,type Packet,type RunPlan,type AssessmentQuote } from '../../lib/assessments.js';
import { PacketView } from './PacketView.js';
import { AssessmentResultView } from './AssessmentResult.js';

function PreparePacket({root,options,onPrepared}:{root:string;options:AssessmentOptions;onPrepared:(packet:Packet)=>void}) {
  const [profile,setProfile]=useState(options.profiles.some(p=>p.id===options.active_profile_id)?options.active_profile_id??'':'');
  const [deliverable,setDeliverable]=useState('');const [selected,setSelected]=useState<string[]>([]);
  const [restricted,setRestricted]=useState(false);const [paths,setPaths]=useState('');const [reason,setReason]=useState('');const [requestId]=useState(()=>crypto.randomUUID());const a=useAction();
  return <section className="panel"><h3>Prepare a bounded evidence packet</h3><p>Preparation is local and makes no provider request. Only submitted text evidence is considered. Images, external links and unavailable material are explicitly omitted.</p>
    {options.profiles_truncated&&<p>Only the latest 1,000 profile versions are listed. Review the full version history in AI settings.</p>}{!options.profiles.length?<p>Create a new evidence-review profile in AI settings after a synthetic compatibility probe. Older protocol-only profiles do not authorize evidence evaluation.</p>:<form onSubmit={e=>{e.preventDefault();void a.run(()=>api<Packet>(`${root}/packets`,'POST',{
      request_id:requestId,package_id:options.package_id,deliverable_id:deliverable,profile_id:profile,expected_package_version:options.package_version,
      evidence_ids:selected,include_restricted:restricted,excluded_paths:parseExcludedPaths(paths),reason}),onPrepared);}}>
      <Feedback error={a.error}/><SelectField label="Independently reviewable deliverable" required value={deliverable} onChange={e=>setDeliverable(e.target.value)}><option value="">Select submitted work</option>{options.deliverables.map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</SelectField>
      <SelectField label="Frozen evidence-review profile" required value={profile} onChange={e=>setProfile(e.target.value)}><option value="">Select a profile</option>{options.profiles.map(p=><option key={p.id} value={p.id}>Version {p.version}: {p.definition.title}{p.id===options.active_profile_id?' — current official configuration':' — advisory unless explicitly approved'}</option>)}</SelectField>
      <SelectField label="Limit to selected evidence (no selection means all eligible entries)" multiple size={Math.min(5,Math.max(2,options.evidence.length))} value={selected} onChange={e=>setSelected(Array.from(e.target.selectedOptions,o=>o.value))}>
        {options.evidence.map(e=><option value={e.id} key={e.id}>{e.title} · {e.visibility} · {e.inclusion}</option>)}</SelectField>
      <ConfirmCheck checked={restricted} onChange={setRestricted} disabled={a.pending}>Include restricted evidence I am authorized to inspect. This is not yet permission to disclose it.</ConfirmCheck>
      <TextArea label="Additional excluded repository paths, one glob pattern per line" value={paths} onChange={e=>setPaths(e.target.value)} placeholder="private/**" maxLength={6000}/>
      <TextArea label="Reason for preparing this packet" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <Submit pending={a.pending}>Prepare local packet—do not send</Submit></form>}
  </section>;
}

function PlanBuilder({root,packet,open}:{root:string;packet:Packet;open:(id:string)=>void}) {
  const [mode,setMode]=useState<'official'|'advisory'>('official');const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);
  const [requestId]=useState(()=>crypto.randomUUID());const a=useAction();
  const history=useResource<Page<RunPlan>>(`${root}/plans?package_id=${packet.package_id}&deliverable_id=${packet.deliverable_id}&mode=${mode}&mine=${mode==='advisory'}`);
  const prior=history.data?.items.find(p=>p.mode===mode);
  return <section className="panel"><h3>Plan one assessment or explicit rerun</h3><p>No request is sent by creating a plan. Advisory comparisons do not replace the official project profile and remain visible to their requester, payer and project administrators.</p>
    <Feedback error={a.error}/>{history.loading||history.error||!history.data?<Loading error={history.error} refresh={history.refresh}/>:<form onSubmit={e=>{e.preventDefault();if(!reviewed) return;void a.run(()=>api<RunPlan>(`${root}/plans`,'POST',{
      request_id:requestId,packet_id:packet.id,reviewed_packet_hash:packet.content_hash,mode,prior_plan_id:prior?.id??null,reason}),v=>open(v.id));}}>
      <SelectField label="Assessment mode" value={mode} onChange={e=>{setMode(e.target.value as 'official'|'advisory');setReviewed(false);}}><option value="official">Current official-profile run</option><option value="advisory">Advisory comparison (not official)</option></SelectField>
      {prior&&<p className="planning-warning wrap">This is an explicit successor to plan {prior.id}. Its result and rationale remain recorded. Inspect the earlier result in run history before proceeding.</p>}
      <TextArea label={prior?'Why this rerun or successor is needed':'Reason for this assessment'} required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={reviewed} onChange={setReviewed} disabled={a.pending}>I inspected the exact outbound payload, omissions, profile choice and any previous run. I am not approving contribution credit.</ConfirmCheck>
      {!packet.stale&&<Submit pending={a.pending}>Preserve this assessment plan—do not send</Submit>}
    </form>}
  </section>;
}

export function RunPlanDetail({projectRoot,id,close}:{projectRoot:string;id:string;close:()=>void}) {
  const root=`${projectRoot}/ai/assessments`;const path=`${root}/plans/${id}`;const s=useResource<RunPlan>(path);
  const packet=useResource<Packet>(s.data?`${root}/packets/${s.data.packet_id}`:null);const a=useAction();
  const [ref,setRef]=useState('');const [reason,setReason]=useState('');const [hours,setHours]=useState('1');
  const [reviewed,setReviewed]=useState(false);const [authorized,setAuthorized]=useState(false);
  const [quotation,setQuotation]=useState<{value:AssessmentQuote;requestId:string}|null>(null);const [payer,setPayer]=useState(false);const [showResult,setShowResult]=useState(false);
  const refresh=()=>{setQuotation(null);setPayer(false);s.refresh();packet.refresh();};
  if(s.loading||s.error||!s.data)return <section className="panel"><button className="button" onClick={close}>Back to assessment history</button><Loading error={s.error} refresh={s.refresh}/></section>;
  const plan=s.data;
  if(showResult&&plan.result_id)return <AssessmentResultView projectRoot={projectRoot} id={plan.result_id} close={()=>setShowResult(false)}/>;
  return <div><section className="panel"><div className="section-heading"><h3>{plan.mode==='official'?'Official-profile':'Advisory'} run plan</h3><button className="button" onClick={close}>Back to assessment history</button></div>
    <p>{planStatus(plan)}</p><p className="planning-warning">{plan.notice}</p><p>{plan.definition.provider} · {plan.definition.requested_model} · output cap {plan.definition.max_output_tokens}</p>
    <p className="small wrap">Plan fingerprint <code>{plan.content_hash}</code></p><p className="preserve-text">Reason: {plan.reason}</p>
    <p className="wrap">Payer: {plan.definition.payer_id}. Audience: {plan.definition.audience}.</p>
    {plan.prior_plan_id&&<p className="wrap">Preserved previous plan: {plan.prior_plan_id}</p>}
    <button className="button" onClick={refresh}>Refresh permission, job and result status</button><Feedback error={a.error} success={a.success}/>
    {plan.job&&<p>Job: {plan.job.status}; accounting: {plan.job.accounting_state}; held reservation {formatMicroUSD(plan.job.reserved_microusd)}; accounted {formatMicroUSD(plan.job.accounted_microusd)}. {plan.job.last_error??''}</p>}
    {plan.result_id&&<button className="button primary" onClick={()=>setShowResult(true)}>Inspect the preserved assessment</button>}
  </section>
  {packet.loading||packet.error||!packet.data?<Loading error={packet.error} refresh={packet.refresh}/>:<PacketView projectRoot={projectRoot} packet={packet.data}/>}
  <section className="panel"><h3>Administrator disclosure approval</h3>
    <p>Provider permission, confidentiality and contributor agreements must cover this exact packet. Pattern redaction cannot guarantee that every sensitive detail was removed. Approval is a recorded human declaration, not a legal determination.</p>
    {plan.grant?<p>Approved until {new Date(plan.grant.valid_until).toLocaleString()}. Reference: {plan.grant.permission_reference}. Revoked: {plan.revoked?'yes':'no'}.</p>:
    plan.can_approve_data&&!plan.revoked&&!plan.packet_stale&&packet.data?<form onSubmit={e=>{e.preventDefault();void a.run(()=>api(`${path}/approve-data`,'POST',{
      reviewed_plan_hash:plan.content_hash,permission_reference:ref,reason,valid_until:new Date(Date.now()+Number(hours)*3600000).toISOString(),packet_reviewed:reviewed,authorized_to_share:authorized}),refresh);}}>
      <TextArea label="Permission and provider data-handling reference for this exact disclosure" required minLength={12} maxLength={500} value={ref} onChange={e=>setRef(e.target.value)}/>
      <TextArea label="Disclosure approval reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
      <SelectField label="Approval lifetime" value={hours} onChange={e=>setHours(e.target.value)}>{[1,6,12,24].map(h=><option key={h} value={h}>{h} hour{h===1?'':'s'}</option>)}</SelectField>
      <ConfirmCheck checked={reviewed} onChange={setReviewed} disabled={a.pending}>I inspected the exact outbound payload above, including omissions and redactions.</ConfirmCheck>
      <ConfirmCheck checked={authorized} onChange={setAuthorized} disabled={a.pending}>I have authority and permission to disclose this packet to the selected provider under the recorded arrangement.</ConfirmCheck>
      <Submit pending={a.pending}>Approve disclosure for this single run—do not send yet</Submit></form>:<p>An authorized administrator must approve a current plan. A revoked or stale plan cannot be reactivated.</p>}
  </section>
  {plan.can_pay&&!plan.job&&!plan.revoked&&!plan.packet_stale&&plan.grant&&<section className="panel"><h3>Separate payer approval</h3>
    <button className="button" disabled={a.pending} onClick={()=>void a.run(()=>api<AssessmentQuote>(`${path}/quote`),value=>{setQuotation({value,requestId:crypto.randomUUID()});setPayer(false);})}>Prepare current cost quotation—do not send</button>
    {quotation&&<><p className="planning-warning">{quotation.value.data_notice}</p><p>{quotation.value.notice}</p>
      <p>Reserve <strong>{formatMicroUSD(quotation.value.specification.reservation_microusd)}</strong> for {quotation.value.specification.month}. Conservative input allowance {quotation.value.specification.input_token_allowance}; output cap {quotation.value.specification.max_output_tokens}.</p>
      <ConfirmCheck checked={payer} onChange={setPayer} disabled={a.pending}>As payer, I authorize this exact reservation and one request containing the reviewed packet. Uncertain requests are not automatically retried.</ConfirmCheck>
      <button className="button primary" disabled={a.pending||!payer} onClick={()=>void a.run(()=>api(`${path}/run`,'POST',assessmentRequest(quotation.value,quotation.requestId,payer)),refresh,'One request queued. The optional AI worker must be running. Refresh to inspect its result.')}>Approve reservation and request assessment</button>
      <button className="button" onClick={()=>{setQuotation(null);setPayer(false);}}>Discard quotation</button></>}
  </section>}
  {plan.can_revoke&&!plan.revoked&&<section className="panel"><h3>Withdraw future disclosure</h3><p>Already-sent requests may be billed. External copies, received information and provider records cannot be recalled.</p>
    <form onSubmit={e=>{e.preventDefault();const value=new FormData(e.currentTarget).get('reason');void a.run(()=>api(`${path}/revoke`,'POST',{reason:value}),refresh);}}>
      <TextArea name="reason" label="Reason for withdrawing disclosure" required minLength={8} maxLength={500}/><Submit pending={a.pending}>Revoke this run plan</Submit></form></section>}
  </div>;
}

export function AssessmentPanel({projectRoot,packageId}:{projectRoot:string;packageId:string}) {
  const root=`${projectRoot}/ai/assessments`;const options=useResource<AssessmentOptions>(`${root}/options?package_id=${packageId}`);
  const [offset,setOffset]=useState(0);const history=useResource<Page<RunPlan>>(`${root}/plans?package_id=${packageId}&offset=${offset}`);
  const [prepared,setPrepared]=useState<Packet|null>(null);const [selected,setSelected]=useState<string|null>(null);
  const refresh=()=>{setPrepared(null);setSelected(null);setOffset(0);options.refresh();history.refresh();};
  if(selected)return <RunPlanDetail key={selected} projectRoot={projectRoot} id={selected} close={refresh}/>;
  return <section className="assessment-panel"><div className="section-heading"><h2>AI-assisted evidence review</h2><button className="button" onClick={refresh}>Refresh assessment workspace</button></div>
    <p className="planning-warning">AI is optional. No award depends on running a model, and agreeing with a suggestion does not accept work. Complete the existing independent review separately.</p>
    {options.loading||options.error||!options.data?<Loading error={options.error} refresh={options.refresh}/>:<>
      {!options.data.live_evidence_enabled&&<p>Live evidence disclosure is disabled by the operator. The synthetic provider remains available without network requests or charges.</p>}
      {prepared?<><PacketView projectRoot={projectRoot} packet={prepared}/><PlanBuilder key={prepared.id} root={root} packet={prepared} open={setSelected}/><button className="button" onClick={()=>setPrepared(null)}>Return to evidence selection</button></>:
        options.data.state==='submitted'?<PreparePacket key={options.data.package_version} root={root} options={options.data} onPrepared={setPrepared}/>:<p>Submit current scope and evidence before preparing an assessment. Historical results below remain preserved.</p>}
    </>}
    <section className="panel"><h3>All visible run plans—not only favorable results</h3>{history.loading||history.error||!history.data?<Loading error={history.error} refresh={history.refresh}/>:<>
      {!history.data.items.length&&<p>No assessments have been planned.</p>}{history.data.items.map(p=><article className="work-history" key={p.id}><div><strong>{p.mode==='official'?'Official profile':'Advisory'} · {planStatus(p)}</strong><p className="preserve-text">{p.reason}</p><small>{new Date(p.created_at).toLocaleString()}</small></div><button className="button" onClick={()=>setSelected(p.id)}>Inspect plan and result</button></article>)}
      <div className="button-row"><button className="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Newer plans</button><button className="button" disabled={history.data.next_offset===null} onClick={()=>setOffset(history.data!.next_offset!)}>Older plans</button></div></>}
    </section></section>;
}
