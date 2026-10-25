import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { formatCents } from '../../lib/simulator.js';
import { explicitInstant } from '../../lib/planning.js';
import { financeCommand, requireReviewed, positiveMoney, assertSyntheticClose, financeDownloadPath,
 type ClosedDistribution,type ContributorStatement,type PaymentCollection,type PaymentView } from '../../lib/finance.js';
import { ReviewDetails } from './ReviewDetails.js';

export function PersonalStatement({root,closeId,recipientId}:{root:string;closeId:string;recipientId?:string}) {
 const state=useResource<ContributorStatement>(`${root}/closes/${closeId}/statement${recipientId?'?recipient_id='+encodeURIComponent(recipientId):''}`);
 return <section className="panel"><h3>Contributor statement</h3><p>Access requires current project membership. An administrator may supply a statement separately to a departed contributor.</p>{state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
 <h4>{state.data.recipient.display_name} · {state.data.month}</h4><p>Frozen synthetic amount: {formatCents(state.data.recipient.distribution_cents)}.</p><p>Reported externally completed: {formatCents(state.data.recipient.recorded_paid_cents)}. Outstanding: {formatCents(state.data.recipient.outstanding_cents)}. Overpayment: {formatCents(state.data.recipient.overpaid_cents)}.</p><Badge>{state.data.recipient.status.replaceAll('_',' ')}</Badge><p>{state.data.notice}</p><p>Original close fingerprint: <code>{state.data.close_hash}</code></p>
 <details><summary>Per-pool calculation and reported payment history</summary><pre className="code-block">{JSON.stringify({pool_explanations:state.data.pool_explanations,payments:state.data.payments},null,2)}</pre></details><button className="button" onClick={state.refresh}>Refresh current payment declarations</button></>}</section>;
}
function VoidDeclaration({root,payment,refresh}:{root:string;payment:PaymentView;refresh:()=>void}) {
 const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const action=useAction();
 return <form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/payments/${payment.id}/void`,'POST',{...financeCommand(reason),reviewed_payment_hash:payment.record_hash,bookkeeping_correction_only:requireReviewed(reviewed)}),refresh);}}><Feedback error={action.error}/><TextField label="Reason for correcting the mistaken payment record" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
 <label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>This only voids a mistaken declaration. It does not reverse, refund or erase a transfer.</label><Submit pending={action.pending}>Void mistaken declaration</Submit></form>;
}
function Payments({root,closed,admin}:{root:string;closed:ClosedDistribution;admin:boolean}) {
 const path=`${root}/closes/${closed.id}/payments`;const state=useResource<PaymentCollection>(path);const action=useAction();
 const [recipient,setRecipient]=useState('');const [amount,setAmount]=useState('');const [provider,setProvider]=useState('');const [reference,setReference]=useState('');const [paidAt,setPaidAt]=useState('');const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const [overpaid,setOverpaid]=useState(false);
 const [viewPerson,setViewPerson]=useState<string|null>(null);
 return <section className="panel"><h3>External-payment declarations</h3><Feedback error={action.error}/>{state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<><p>{state.data.notice}</p>
 <div className="table-scroll"><table><caption>Frozen amounts versus current declarations</caption><thead><tr><th scope="col">Contributor</th><th scope="col">Frozen</th><th scope="col">Reported</th><th scope="col">Outstanding</th><th scope="col">Overpaid</th></tr></thead><tbody>{state.data.balances.map(b=><tr key={b.user_id}><td><button className="button" onClick={()=>setViewPerson(b.user_id)}>{b.display_name}</button></td><td>{formatCents(b.distribution_cents)}</td><td>{formatCents(b.recorded_paid_cents)}</td><td>{formatCents(b.outstanding_cents)}</td><td>{formatCents(b.overpaid_cents)}</td></tr>)}</tbody></table></div>
 {viewPerson&&<PersonalStatement key={viewPerson} root={root} closeId={closed.id} recipientId={viewPerson}/>}
 <form onSubmit={e=>{e.preventDefault();void action.run(()=>{const timestamp=explicitInstant(paidAt);if(!timestamp)throw new Error('Enter the actual completion timestamp with an explicit offset.');return api(path,'POST',{...financeCommand(reason),recipient_id:recipient,amount_cents:positiveMoney(amount),provider,external_reference:reference,paid_at:timestamp,reviewed_close_hash:closed.record_hash,externally_completed:requireReviewed(reviewed),synthetic_only:true,overpayment_acknowledged:overpaid});},()=>{setReference('');setAmount('');setReviewed(false);state.refresh();});}}>
 <SelectField label="Recipient of reported transfer" required value={recipient} onChange={e=>setRecipient(e.target.value)}><option value="">Choose a recipient</option>{state.data.balances.filter(b=>b.distribution_cents>0).map(b=><option key={b.user_id} value={b.user_id}>{b.display_name}</option>)}</SelectField>
 <TextField label="Reported transfer amount in USD" required inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/><TextField label="External provider or bank reference namespace" required minLength={2} maxLength={200} value={provider} onChange={e=>setProvider(e.target.value)}/>
 <TextField label="Unique completed transfer reference" required minLength={2} maxLength={200} value={reference} onChange={e=>setReference(e.target.value)}/><TextField label="Transfer completion timestamp" required value={paidAt} onChange={e=>setPaidAt(e.target.value)} hint="ISO timestamp with seconds and offset, e.g. 2030-03-01T12:00:00-04:00. Must not be in the future or precede this close."/>
 <TextField label="Recording reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/><label className="check-row"><input type="checkbox" checked={overpaid} onChange={e=>setOverpaid(e.target.checked)}/>Allow reporting an overpayment explicitly. This does not increase the frozen entitlement.</label>
 <label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed this frozen distribution and am recording a fictional already-completed external transfer. No payment will be sent.</label><Submit pending={action.pending}>Record external-payment declaration</Submit></form>
 <h4>Declaration history</h4>{!state.data.items.length&&<p>No transfer declarations recorded. Exporting does not mark recipients paid.</p>}{state.data.items.map(p=><details key={p.id}><summary>{formatCents(p.record.amount_cents)} · {p.record.provider} · {p.record.external_reference} · {p.status.replaceAll('_',' ')}</summary><pre className="code-block">{JSON.stringify(p,null,2)}</pre>{admin&&!p.void&&<VoidDeclaration root={root} payment={p} refresh={state.refresh}/>}</details>)}</>}
 </section>;
}
export function Distribution({root,closeId,admin}:{root:string;closeId:string;admin:boolean}) {
 const state=useResource<ClosedDistribution>(`${root}/closes/${closeId}`);
 if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
 let closed:ClosedDistribution;try{closed=assertSyntheticClose(state.data);}catch{return <Feedback error="The response was not a valid reproduced synthetic distribution."/>;}
 return <><section className="panel"><h3>Frozen synthetic distribution</h3><p>Closed {closed.created_at}. The server reproduced its amounts from the preserved inputs, without an AI call. These exports stay identical when later payment declarations change.</p><code>{closed.record_hash}</code><p>{(['csv','json','zip'] as const).map(format=><a className="button" key={format} href={financeDownloadPath(root,closed.id,format)}>Download {format==='zip'?'audit bundle':format.toUpperCase()}</a>)}</p><p>CSV display names are prefixed with “text: ” to avoid formula-like cells; JSON preserves original text. The audit bundle contains source references and hashes, not original statement bytes. No download creates another payment obligation.</p></section>
 <ReviewDetails record={closed.record} frozen/><Payments root={root} closed={closed} admin={admin}/></>;
}
