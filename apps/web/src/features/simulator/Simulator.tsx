import { useEffect,useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback,Loading,SelectField } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Project } from '../../lib/accounts.js';
import type { Paged } from '../../lib/reviews.js';
import { assertNonPayable,formatCents,monthInTimezone,parseMoney,scenarioHash,validateMonth,
  type SimulationRecord,type SimulationOptions,type SavedScenario,type ScenarioSummary } from '../../lib/simulator.js';
import { SimulationView } from './SimulationView.js';

export function SavedScenarioView({root,id,workspaceId,projectId,close}:{root:string;id:string;workspaceId:string;projectId:string;close:()=>void}) {
  const state=useResource<SavedScenario>(`${root}/simulator/scenarios/${id}`);
  return <><div className="section-heading"><button className="button" onClick={close}>Back to simulator</button><button className="button" onClick={state.refresh}>Reload saved example</button></div>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<><section className="panel"><p className="eyebrow">Saved example · not a financial record</p><h2>{state.data.title}</h2><p>{state.data.notice}</p><p>The stored calculation was reproduced from its captured inputs: {state.data.reproduced?'yes':'not verified'}.</p>
      <a className="button" href={scenarioHash(workspaceId,projectId,id)}>Open project-protected link</a><p className="small">The link requires a signed-in account with current project access. It is not a public share or a remote deployment.</p></section><SimulationView record={assertNonPayable(state.data.record)}/></>}
  </>;
}

function ScenarioList({root,open,refreshKey}:{root:string;open:(id:string)=>void;refreshKey:number}) {
  const [offset,setOffset]=useState(0);const state=useResource<Paged<ScenarioSummary>>(`${root}/simulator/scenarios?offset=${offset}`);
  useEffect(()=>{state.refresh();},[refreshKey,state.refresh]);
  return <section className="panel"><div className="section-heading"><h2>Saved hypothetical examples</h2><button className="button" onClick={state.refresh}>Refresh examples</button></div>
    {state.loading||state.error?<Loading error={state.error} refresh={state.refresh}/>:<>{!state.data?.items.length?<p>No saved examples on this page. Calculating a preview does not automatically save it.</p>:<div className="table-scroll"><table><caption>Saved examples, not amounts owed</caption><thead><tr><th scope="col">Example</th><th scope="col">Month</th><th scope="col">Hypothetical USD</th><th scope="col">Status</th></tr></thead><tbody>{state.data.items.map(row=><tr key={row.id}><th scope="row"><button className="button" onClick={()=>open(row.id)}>{row.title}</button><small>{new Date(row.created_at).toLocaleString()}</small></th><td>{row.month}</td><td>{formatCents(row.amount_cents)}</td><td>{row.status==='blocked'?'Blocked pool':'Calculated example'}</td></tr>)}</tbody></table></div>}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Previous examples</button><button className="button" disabled={state.data?.next_offset==null} onClick={()=>setOffset(state.data!.next_offset!)}>Next examples</button></div></>}
  </section>;
}

export function Simulator({project}:{project:Project}) {
  const root=`/api/v1/workspaces/${project.workspace_id}/projects/${project.id}`;
  const state=useResource<SimulationOptions>(`${root}/simulator/options`);
  const [source,setSource]=useState('');const [calculation,setCalculation]=useState('');
  const [month,setMonth]=useState(()=>monthInTimezone(project.timezone));const [amount,setAmount]=useState('10000.00');
  const [record,setRecord]=useState<SimulationRecord|null>(null);const [selected,setSelected]=useState<string|null>(null);
  const [title,setTitle]=useState('');const [confirmed,setConfirmed]=useState(false);const [saveKey,setSaveKey]=useState(()=>crypto.randomUUID());
  const [refreshKey,setRefreshKey]=useState(0);const action=useAction();const save=useAction();
  const clear=()=>{setRecord(null);setConfirmed(false);setSaveKey(crypto.randomUUID());};
  if(selected)return <SavedScenarioView root={root} id={selected} workspaceId={project.workspace_id} projectId={project.id} close={()=>{setSelected(null);setRefreshKey(v=>v+1);}}/>;
  if(state.loading||state.error||!state.data)return <section className="panel"><h2>Revenue simulator</h2><Loading error={state.error} refresh={()=>{clear();state.refresh();}}/></section>;
  const options=state.data;
  return <><section className="panel"><div className="section-heading"><div><p className="eyebrow">What-if calculations</p><h2>Revenue simulator</h2></div><button className="button" disabled={action.pending||save.pending} onClick={()=>{clear();state.refresh();}}>Refresh policy choices</button></div><p>{options.notice}</p>
    {!options.policies.length?<p>Create a draft policy first. A draft can be tested without approving it, but unaccepted work will not produce contributor amounts.</p>:<form onSubmit={event=>{event.preventDefault();setRecord(null);void action.run(async()=>{
      const body={source_policy_id:source,calculation_policy_id:calculation,month:validateMonth(month),amount_cents:parseMoney(amount)};
      if(!source||!calculation)throw new Error('Choose the source-credit policy and the calculation policy explicitly.');
      return assertNonPayable(await api<SimulationRecord>(`${root}/simulator/preview`,'POST',body));
    },value=>{setRecord(value);setConfirmed(false);setSaveKey(crypto.randomUUID());});}}>
      <fieldset disabled={action.pending||save.pending} className="sim-fieldset"><legend>Explicit hypothetical scope</legend><div className="form-grid">
        <SelectField label="Source-credit policy" required value={source} onChange={e=>{setSource(e.target.value);if(!calculation)setCalculation(e.target.value);clear();}}><option value="">Choose the policy that owns the accepted credit</option>{options.policies.map(p=><option key={p.id} value={p.id}>Version {p.version} · {p.title} · {p.state}</option>)}</SelectField>
        <SelectField label="Calculation policy" required value={calculation} onChange={e=>{setCalculation(e.target.value);clear();}}><option value="">Choose rules for this example</option>{options.policies.map(p=><option key={p.id} value={p.id}>Version {p.version} · {p.title} · {p.state}</option>)}</SelectField>
        <TextField label="Hypothetical distributable USD" required inputMode="decimal" maxLength={14} value={amount} onChange={e=>{setAmount(e.target.value);clear();}} hint="Example: 10000.00. This is an assumed amount after deductions; this simulator does not import receipts or deduct expenses."/>
        <TextField label="Accounting month" type="month" required min="2000-01" max="9998-12" value={month} onChange={e=>{setMonth(e.target.value);clear();}} hint="Boundaries follow the selected calculation policy timezone, not your computer's local timezone."/>
      </div><p className="small">All milestones under the source policy are considered. Only accepted units in the stated pool/date scope enter each denominator. A draft comparison never changes existing awards or activates its rules.</p>
      <button className="button primary" type="submit">{action.pending?'Calculating…':'Calculate hypothetical distribution'}</button></fieldset></form>}
      <Feedback error={action.error}/>
    </section>
    {record&&<><SimulationView record={record}/>{options.can_save&&<section className="panel"><h3>Save this hypothetical example</h3><p>Saving preserves a reproducible, project-visible snapshot. It does not approve a distribution. A stale preview must be recalculated before saving.</p><Feedback error={save.error}/>
      <form onSubmit={e=>{e.preventDefault();void save.run(async()=>{
        if(!confirmed)throw new Error('Confirm that this is only a non-payable hypothetical example.');
        return api<SavedScenario>(`${root}/simulator/scenarios`,'POST',{request_id:saveKey,title,input:record.input,reviewed_snapshot_hash:record.snapshot_hash,hypothetical_confirmed:true});
      },value=>{setSelected(value.id);setRecord(null);setTitle('');setConfirmed(false);setSaveKey(crypto.randomUUID());});}}>
        <fieldset disabled={save.pending} className="sim-fieldset"><legend>Example label</legend><TextField label="Saved example title" required minLength={2} maxLength={120} value={title} onChange={e=>{setTitle(e.target.value);setSaveKey(crypto.randomUUID());}}/>
        <label className="checkbox-row"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>This is hypothetical and creates no amount owed or payable.</label>
        <button className="button" type="submit" disabled={!confirmed}>{save.pending?'Saving example…':'Save hypothetical example'}</button></fieldset>
      </form></section>}</>}
    <ScenarioList root={root} open={setSelected} refreshKey={refreshKey}/>
  </>;
}
