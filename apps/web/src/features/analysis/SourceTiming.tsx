import type { AnalysisSource } from '../../lib/analysis.js';

const labels = {created_at:'Created',updated_at:'Last updated',closed_at:'Closed',merged_at:'Merged',submitted_at:'Review submitted',git_author_date:'Git author date',git_committer_date:'Git committer date'};

export function SourceTiming({source}:{source:AnalysisSource}) {
  const times=Object.entries(source.recorded_times||{});
  if(!source.context_only&&!times.length)return null;
  return <div className="analysis-source-timing">
    {source.context_only&&<p className="planning-warning">Parent context only. Its older authorship is excluded from this period's contributor attribution; related reviews and discussion have their own dates.</p>}
    {!!times.length&&<><p className="small">Captured timestamps (UTC). Current source text and status may include later edits.</p><ul className="small">{times.map(([key,value])=>{
      const date=new Date(value!);const shown=Number.isNaN(date.valueOf())?value:date.toISOString();
      return <li key={key}>{labels[key as keyof typeof labels]}: {shown}</li>;
    })}</ul></>}
  </div>;
}
