import { useState } from 'react';
import { Loading } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import type { Page } from '../../lib/ai.js';
import type { ReviewRecord } from '../../lib/reviews.js';
import { planStatus,type RunPlan } from '../../lib/assessments.js';
import { AssessmentResultView } from './AssessmentResult.js';

export function AssessmentReview({projectRoot,review}:{projectRoot:string;review:ReviewRecord}) {
  const [offset,setOffset]=useState(0);const [selected,setSelected]=useState<string|null>(null);
  const state=useResource<Page<RunPlan>>(`${projectRoot}/ai/assessments/plans?package_id=${review.package_id}&deliverable_id=${review.deliverable_id}&offset=${offset}`);
  return <section className="assessment-panel"><h3>Optional AI observations alongside original evidence</h3>
    <p>Every visible run remains listed. An advisory or stale result cannot replace the official configuration. Even a current valid result cannot submit your acceptance decision or issue credit.</p>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
      {!state.data.items.length&&<p>No AI run for this deliverable. The manual review remains fully available.</p>}
      {state.data.items.map(p=><div className="work-history" key={p.id}><div><strong>{p.mode==='official'?'Official profile':'Advisory'} · {planStatus(p)}</strong><p>{p.reason}</p></div>
        {p.result_id?<button className="button" onClick={()=>setSelected(p.result_id)}>Inspect suggestions and record observations</button>:<span>No validated result yet</span>}</div>)}
      <div className="button-row"><button className="button" onClick={state.refresh}>Refresh assessments</button><button className="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Newer plans</button><button className="button" disabled={state.data.next_offset===null} onClick={()=>setOffset(state.data!.next_offset!)}>Older plans</button></div></>}
    {selected&&<AssessmentResultView key={selected} projectRoot={projectRoot} id={selected} review={review} close={()=>setSelected(null)}/>}
  </section>;
}
