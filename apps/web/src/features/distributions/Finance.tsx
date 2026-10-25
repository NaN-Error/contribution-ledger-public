import { useState } from 'react';
import { TextField, Badge } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Items, Project } from '../../lib/accounts.js';
import { financeCommand, requireReviewed, type FinanceOptions, type PeriodSummary } from '../../lib/finance.js';
import { validateMonth } from '../../lib/simulator.js';
import { Period } from './Period.js';
import { PersonalStatement } from './Statements.js';

function NewPeriod({root,options,refresh}:{root:string;options:FinanceOptions;refresh:()=>void}) {
 const [month,setMonth]=useState('');const [source,setSource]=useState('');const [calculation,setCalculation]=useState('');
 const [agreement,setAgreement]=useState('');const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const action=useAction();
 const sourceId=source||options.policies.find(p=>p.ready_for_pinned_work)?.id||'';const calculationId=calculation||sourceId;
 const rules=options.policies.find(p=>p.id===calculationId)?.rules;
 return <section className="panel"><h2>Open a synthetic accounting period</h2><p>Use a finished calendar month. The first approved close freezes release shares. Later periods must be consecutive and keep the same source-credit policy and timezone.</p>
 <Feedback error={action.error}/><form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/periods`,'POST',{
  ...financeCommand(reason),month:validateMonth(month),source_policy_id:sourceId,calculation_policy_id:calculationId,agreement_reference:agreement,
  deficit_rule:'carry_negative_balance_forward',synthetic_only:true,period_rules_reviewed:requireReviewed(reviewed)}),refresh);}}>
 <TextField label="Accounting month" type="month" required value={month} onChange={e=>setMonth(e.target.value)}/>
 <SelectField label="Accepted contributions under policy" required value={sourceId} onChange={e=>setSource(e.target.value)}><option value="">Choose a ready policy</option>{options.policies.map(p=><option key={p.id} value={p.id} disabled={!p.ready_for_pinned_work}>Version {p.version}: {p.title} {p.ready_for_pinned_work?'':'(not ready)'}</option>)}</SelectField>
 <SelectField label="Approved distribution rules" required value={calculationId} onChange={e=>setCalculation(e.target.value)}><option value="">Choose a ready policy</option>{options.policies.map(p=><option key={p.id} value={p.id} disabled={!p.ready_for_pinned_work}>Version {p.version}: {p.title}</option>)}</SelectField>
 {rules&&<p>USD · {rules.timezone} · {rules.accounting.revenue_basis.replaceAll('_',' ')}. First period opens with zero reserve and deficit; later periods carry both from the preceding close.</p>}
 <TextField label="Reviewed agreement reference" required minLength={2} maxLength={200} value={agreement} onChange={e=>setAgreement(e.target.value)}/>
 <TextField label="Reason" required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/>
 <label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed these synthetic-only rules and negative-balance carryforward. This does not establish legal compliance or authorize real compensation.</label>
 <Submit pending={action.pending}>Create period</Submit></form></section>;
}

export function Finance({project}:{project:Project}) {
 const root=`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/finance`;
 const options=useResource<FinanceOptions>(root+'/options');const periods=useResource<Items<PeriodSummary>>(root+'/periods');
 const [selected,setSelected]=useState<PeriodSummary|null>(null);
 const refresh=()=>{options.refresh();periods.refresh();setSelected(null);};
 if(options.loading||options.error||!options.data)return <Loading error={options.error} refresh={options.refresh}/>;
 const cfg=options.data;
 return <><div className="page-heading"><div><p className="eyebrow">Financial records</p><h2>Distributions and statements</h2><p>{cfg.notice}</p></div><Badge>Synthetic development only</Badge></div>
 <p className="small muted">No bank connection, transfer, tax form, equity, or automatic clawback. Financial sources are restricted to administrators and finance members; other members can inspect their own closed statement.</p>
 {selected?<><button className="button" onClick={refresh}>← Accounting periods</button>{cfg.can_manage_finance?<Period key={selected.id} root={root} id={selected.id} options={cfg}/>:selected.close_id?<PersonalStatement key={selected.close_id} root={root} closeId={selected.close_id}/>:<section className="panel"><h3>No closed statement</h3><p>This period has not been approved and frozen.</p></section>}</>:<>
 <div className="section-heading"><h3>Accounting periods</h3><button className="button" onClick={periods.refresh}>Refresh periods</button></div>
 {periods.loading||periods.error?<Loading error={periods.error} refresh={periods.refresh}/>:<div className="project-grid">{!periods.data?.items.length&&<p>No accounting periods have been created.</p>}{periods.data?.items.map(p=><button className="project-card" key={p.id} onClick={()=>setSelected(p)}><strong>{p.month}</strong><p>{p.timezone}</p><Badge>{p.state}</Badge></button>)}</div>}
 {cfg.can_approve&&<NewPeriod root={root} options={cfg} refresh={refresh}/>}</>}
 </>;
}
