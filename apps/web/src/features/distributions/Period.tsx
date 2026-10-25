import { ReviewDetails } from './ReviewDetails.js';
import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { financeCommand, requireReviewed, type PeriodDetail, type FinanceOptions, type FinancePreview, type FinanceProposal } from '../../lib/finance.js';
import { FinancialEntries } from './FinancialEntries.js';
import { Distribution } from './Statements.js';

function ProposalDecision({root,proposal,admin,open,refresh}:{root:string;proposal:FinanceProposal;admin:boolean;open:boolean;refresh:()=>void}) {
 const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const [decision,setDecision]=useState<'approve'|'reject'>('approve');const action=useAction();
 return <section className="panel"><h3>Preserved proposal</h3><p>{proposal.record.reason}</p><Badge>{proposal.state}</Badge><p>Created {proposal.created_at}; fingerprint <code>{proposal.record_hash}</code></p><ReviewDetails record={proposal.record.preview}/>
 {proposal.decision?<p>Decision: {proposal.decision.record.action} — {proposal.decision.record.reason}</p>:admin&&open?<><Feedback error={action.error}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/proposals/${proposal.id}/decisions`,'POST',{...financeCommand(reason),reviewed_proposal_hash:proposal.record_hash,action:decision,reviewed:requireReviewed(reviewed),synthetic_only:true}),refresh);}}>
 <SelectField label="Administrator decision" value={decision} onChange={e=>setDecision(e.target.value as typeof decision)}><option value="approve">Approve exact synthetic proposal</option><option value="reject">Reject and preserve proposal</option></SelectField>
 <TextField label="Approval or rejection reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I inspected the financial sources, contribution scope, release shares, carryforward and rounding. This is a synthetic development record, not real-payment authorization.</label><Submit pending={action.pending}>Record decision</Submit></form></>:<p>No decision is available with current access or for a closed period.</p>}</section>;
}
function Closing({root,period,admin,refresh}:{root:string;period:PeriodDetail;admin:boolean;refresh:()=>void}) {
 const [kind,setKind]=useState<'close'|'release_correction'>('close');const [preview,setPreview]=useState<FinancePreview|null>(null);
 const [selected,setSelected]=useState<string|null>(null);const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const action=useAction();
 const selectedProposal=period.proposals.find(p=>p.id===selected);
 return <><section className="panel"><h3>Review before freezing</h3><p>Ordinary financial administration is distinct from independent contribution acceptance. A close cannot bypass a disputed award, empty required pool, missing acknowledgement or unreviewed entry.</p><Feedback error={action.error}/>
 {period.state==='open'&&<><SelectField label="Preview operation" value={kind} onChange={e=>{setKind(e.target.value as typeof kind);setPreview(null);setReviewed(false);}}><option value="close">Period close and distribution</option>{admin&&period.release_snapshot&&<option value="release_correction">Correct existing release attribution prospectively</option>}</SelectField>
 <button className="button" disabled={action.pending} onClick={()=>void action.run(()=>api<FinancePreview>(`${root}/periods/${period.id}/preview?kind=${kind}`,'POST'),value=>{setPreview(value);setReviewed(false);})}>Calculate fresh preview</button></>}
 {preview&&<><ReviewDetails record={preview.record}/><p>Reviewed fingerprint: <code>{preview.preview_hash}</code></p>{!preview.record.blockers.length&&period.state==='open'&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api<FinanceProposal>(`${root}/periods/${period.id}/proposals`,'POST',{...financeCommand(reason),kind,reviewed_preview_hash:preview.preview_hash,financial_records_reviewed:requireReviewed(reviewed),contribution_scope_reviewed:true,synthetic_only:true}),()=>{setPreview(null);refresh();});}}>
 <TextField label="Proposal reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed the exact financial records and contribution scope above. Save this proposal for a separate administrator decision.</label><Submit pending={action.pending}>Save reviewed proposal</Submit></form>}</>}
 </section><section className="panel"><h3>Proposal history</h3>{!period.proposals.length&&<p>No proposal has been saved.</p>}{period.proposals.map(p=><button className="button" key={p.id} onClick={()=>setSelected(p.id)}>{p.kind.replaceAll('_',' ')} · {p.state} · {p.created_at}</button>)}</section>
 {selectedProposal&&<ProposalDecision key={selectedProposal.id} root={root} proposal={selectedProposal} admin={admin} open={period.state==='open'} refresh={refresh}/>}</>;
}
export function Period({root,id,options}:{root:string;id:string;options:FinanceOptions}) {
 const state=useResource<PeriodDetail>(`${root}/periods/${id}`);const [tab,setTab]=useState<'entries'|'close'|'distribution'>('entries');
 if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
 const p=state.data;
 return <><div className="section-heading"><h2>{p.month} · {p.state}</h2><button className="button" onClick={state.refresh}>Refresh period</button></div><p>{p.record.start_inclusive} ≤ acceptance period &lt; {p.record.end_exclusive}. Agreement reference: {p.record.agreement_reference}.</p>
 <div className="tab-buttons"><button className="button" aria-pressed={tab==='entries'} onClick={()=>setTab('entries')}>Statements and entries</button><button className="button" aria-pressed={tab==='close'} onClick={()=>setTab('close')}>Close review and history</button>{p.close_id&&<button className="button" aria-pressed={tab==='distribution'} onClick={()=>setTab('distribution')}>Frozen distribution and payments</button>}</div>
 {tab==='entries'?<FinancialEntries root={root} period={p} admin={options.can_approve} refresh={state.refresh}/>:tab==='distribution'&&p.close_id?<Distribution root={root} closeId={p.close_id} admin={options.can_approve}/>:<Closing root={root} period={p} admin={options.can_approve} refresh={state.refresh}/>}</>;
}
