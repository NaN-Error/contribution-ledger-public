import { useState } from 'react';
import { ConfirmCheck } from '../../components/planning.js';
import { ScopeEditor } from '../work-packages/ScopeEditor.js';
import { api } from '../../lib/api.js';
import { promotionBody,type BatchDetail,type Candidate,type HistoricalResult } from '../../lib/reconstruction.js';
import type { WorkOptions,WorkPackageDetail } from '../../lib/workPackages.js';

export function CandidatePromotion({root,base,batch,candidate,done,cancel}:{root:string;base:string;batch:BatchDetail;candidate:Candidate;done:(id:string)=>void;cancel:()=>void}){
  const [shared,setShared]=useState(false);
  const occupied=new Set((batch.candidates??[]).map(c=>c.allocation_id).filter(Boolean));
  const options:WorkOptions={my_user_id:batch.my_user_id,can_create:batch.can_manage,participants:batch.participants??[],allocations_truncated:false,notice:'Historical work uses a separately approved allocation.',
    allocations:(batch.allocations??[]).filter(a=>a.category===candidate.document.category&&a.atoms>0&&a.issued_atoms===0&&!occupied.has(a.id)).map(a=>({...a,milestone_id:batch.milestone_id,milestone_name:batch.definition.title,policy_id:batch.policy_id}))};
  return <section className="panel"><h3>Create reviewed historical package</h3><p>Allocate a budget in the Milestones tab first, then refresh this batch. The server rejects an allocation already bound to another package. No budget or value is inferred from commits.</p>
    <p>This action pins {candidate.sources.length} source records as project-visible evidence. Inspect them before sharing. Manual outcomes need their evidence attached separately after creation.</p>
    <ConfirmCheck checked={shared} onChange={setShared}>I reviewed the pinned source records and permit their disclosure to this project's participants.</ConfirmCheck>
    {!shared?<button className="button" onClick={cancel}>Close package preparation</button>:<ScopeEditor root={`${root}/work-packages`} options={options} initialTitle={candidate.document.title} initialOutcome={candidate.document.summary}
      onCancel={cancel} onSaved={p=>done(p.id)} submitCreate={async(scope,allocation,reason)=>{
        const result=await api<HistoricalResult>(base+'/promote','POST',promotionBody(batch,candidate,allocation,scope,reason,shared));
        if(!result.result.package_id)throw new Error('The server did not return the created package. Refresh this batch before retrying.');
        return api<WorkPackageDetail>(`${root}/work-packages/${result.result.package_id}`);
      }}/>}</section>;
}
