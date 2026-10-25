import { useState } from 'react';
import { Feedback, Loading, Submit, TextArea } from '../../components/forms.js';
import { useAction,useResource } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { AIProfile,Page } from '../../lib/ai.js';
function Approval({root,profile,active,refresh}:{root:string;profile:AIProfile;active:string|null;refresh:()=>void}) {
  const [reason,setReason]=useState('');const [reviewed,setReviewed]=useState(false);const a=useAction();
  return <form onSubmit={e=>{e.preventDefault();if(!reviewed)return;void a.run(()=>api(`${root}/profiles/${profile.id}/approve`,'POST',{reviewed_hash:profile.fingerprint,expected_active_profile_id:active,reason}),refresh);}}>
    <Feedback error={a.error}/><TextArea label="Reason for approving this exact profile" value={reason} onChange={e=>setReason(e.target.value)} minLength={8} maxLength={500} required/>
    <label className="check-row"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed the provider, payer authorization, exact model, settings and data policy above. This is not a fairness evaluation.</label>
    <Submit pending={a.pending}>Approve this configuration prospectively</Submit></form>;
}
export function Profiles({root,canApprove}:{root:string;canApprove:boolean}) {
  const [offset,setOffset]=useState(0);
  const s=useResource<Page<AIProfile>&{active_profile_id:string|null}>(`${root}/profiles?offset=${offset}`);
  return <section className="panel"><div className="section-heading"><h3>Evaluator-profile history</h3><button className="button" onClick={s.refresh}>Refresh profiles</button></div>
    <p>Catalog refreshes never approve or replace profiles. The last approved configuration may become unavailable after revocation or model changes. There is no automatic fallback. Only a new evidence-review profile can support phase-11 assessments; earlier protocol-only profiles retain their original limited scope.</p>
    {s.loading||s.error||!s.data?<Loading error={s.error} refresh={s.refresh}/>:<>
      {!s.data.items.length&&<p>No profiles. Configure a connection, authorize project use, complete a synthetic probe, and save a draft.</p>}
      {s.data.items.map(p=><details key={p.id}><summary>Version {p.version}: {p.definition.title} — {p.id===s.data!.active_profile_id?'last approved configuration':p.approved?'previously approved':'draft'}</summary>
        <pre className="code-block">{JSON.stringify(p.definition,null,2)}</pre><p>Fingerprint: <code>{p.fingerprint}</code></p>
        {canApprove&&!p.approved&&<Approval root={root} profile={p} active={s.data!.active_profile_id} refresh={s.refresh}/>}</details>)}
      <button className="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous profiles</button>
      <button className="button" disabled={s.data.next_offset===null} onClick={()=>setOffset(s.data!.next_offset!)}>Next profiles</button>
    </>}
  </section>;
}
