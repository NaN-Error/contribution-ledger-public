import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Feedback, Loading, SelectField, Submit } from '../../components/forms.js';
import { ConfirmCheck } from '../../components/planning.js';
import { useAction, useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { humanLabel } from '../../lib/planning.js';
import type { IdentityPage, IdentityRow, GitHubPage } from '../../lib/github.js';

function MappingHistory({path}:{path:string}) {
  const [offset,setOffset]=useState(0);const state=useResource<GitHubPage<{id:string;version:number;linked_user_id:string|null;reason:string;created_at:string}>>(`${path}?offset=${offset}`);
  if(state.loading||state.error||!state.data)return <Loading error={state.error} refresh={state.refresh}/>;
  return <><h4>Preserved mapping decisions</h4>{state.data.items.length?state.data.items.map(row=><p className="small wrap" key={row.id}>Version {row.version} · {row.linked_user_id||'Unlinked'} · {row.reason} · {new Date(row.created_at).toLocaleString()}</p>):<p>No manual mapping decisions.</p>}
    <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous decisions</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>state.data?.next_offset!=null&&setOffset(state.data.next_offset)}>Next decisions</button></div></>;
}
function MappingRow({root,row,people,canManage,refresh}:{root:string;row:IdentityRow;people:IdentityPage['people'];canManage:boolean;refresh:()=>void}) {
  const [user,setUser]=useState(row.linked_user_id||'');const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);const [history,setHistory]=useState(false);const action=useAction();
  const current=people.find(p=>p.user_id===row.linked_user_id);
  return <article className="panel"><div className="section-heading"><h3 className="wrap">{row.label}</h3><Badge>{humanLabel(row.kind)}</Badge></div><p className="small wrap">{row.external_key}</p>
    <p>Current mapping: {current?.display_name||(row.linked_user_id?`Historical account ${row.linked_user_id}`:'Unassigned')}</p><Feedback error={action.error}/>
    {canManage&&<form onSubmit={e=>{e.preventDefault();void action.run(()=>api(`${root}/identities/${row.id}/mapping`,'POST',{user_id:user||null,expected_version:row.version,reason,reviewed:confirmed}),refresh);}}>
      <SelectField label="Reviewed contributor mapping" value={user} onChange={e=>setUser(e.target.value)}><option value="">No contributor mapping</option>{row.linked_user_id&&!current&&<option value={row.linked_user_id}>Historical/inactive account (cannot newly assign)</option>}{row.kind!=='github_bot'&&people.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name} · {p.role}</option>)}</SelectField>
      <TextField label="Evidence and reason for this identity decision" minLength={8} maxLength={500} required value={reason} onChange={e=>setReason(e.target.value)}/>
      <ConfirmCheck checked={confirmed} onChange={setConfirmed} disabled={action.pending}>I reviewed this claim. The mapping does not verify a person's identity, change previous evidence snapshots, or award contribution units.</ConfirmCheck><Submit pending={action.pending}>Save mapping decision</Submit>
    </form>}
    <button className="button" onClick={()=>setHistory(!history)}>{history?'Hide mapping history':'Inspect mapping history'}</button>{history&&<MappingHistory path={`${root}/identities/${row.id}/history`}/>}
  </article>;
}
export function GitHubIdentities({root}:{root:string}) {
  const [offset,setOffset]=useState(0);const state=useResource<IdentityPage>(`${root}/identities?offset=${offset}`);
  return <><div className="section-heading"><h2>Identity claims and mappings</h2><button className="button" onClick={state.refresh}>Refresh identities</button></div>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<><p className="planning-warning">{state.data.notice}</p>
      {!state.data.items.length&&<section className="panel empty"><h3>No imported identities on this page</h3><p>Identities appear after the worker captures source records. Names and email claims are never automatically matched to team members.</p></section>}
      {state.data.items.map(row=><MappingRow key={`${row.id}:${row.version}`} root={root} row={row} people={state.data!.people} canManage={state.data!.can_manage} refresh={state.refresh}/>)}
      <div className="button-row"><button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous identities</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>state.data?.next_offset!=null&&setOffset(state.data.next_offset)}>Next identities</button></div></>}
  </>;
}
