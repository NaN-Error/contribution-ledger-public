import { useState } from 'react';
import { Feedback,Loading,SelectField } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import { categories,formatUnits,humanLabel } from '../../lib/planning.js';
import { formatFraction } from '../../lib/reconstruction.js';
import { overviewPath,type OverviewReport,type OverviewGroup,type OverviewPerson } from '../../lib/overview.js';

export function ContributionOverview({root}:{root:string}){
  const [filters,setFilters]=useState({policy_id:'',pool_key:'',category:'',origin:'',person_id:''});
  const options=useResource<OverviewReport>(root+'/reports/overview');const state=useResource<OverviewReport>(overviewPath(root,filters));
  const policies=[...new Map<string,OverviewGroup>((options.data?.groups??[]).map(g=>[g.policy_id,g] as const)).values()];const people=[...new Map<string,OverviewPerson>((options.data?.groups??[]).flatMap(g=>g.people).map(p=>[p.user_id,p] as const)).values()].sort((a,b)=>a.display_name.localeCompare(b.display_name));
  const set=(key:keyof typeof filters,value:string)=>setFilters(old=>({...old,[key]:value}));
  return <><div className="section-heading"><h2>Contribution explanations</h2><button className="button" onClick={()=>{options.refresh();state.refresh();}}>Refresh recognized contributions</button></div>
    <p>Observed activity, independently accepted units, and pending work are different measurements. These views do not rank personal worth or create payment obligations.</p><Feedback error={options.error}/>
    <section className="panel"><h3>Scope and display filters</h3><div className="form-grid">
      <SelectField label="Credit policy" value={filters.policy_id} onChange={e=>set('policy_id',e.target.value)}><option value="">Each policy shown separately</option>{policies.map(p=><option key={p.policy_id} value={p.policy_id}>Policy version {p.policy_version} · {p.policy_id}</option>)}</SelectField>
      <SelectField label="Contribution pool" value={filters.pool_key} onChange={e=>set('pool_key',e.target.value)}><option value="">Each pool shown separately</option><option value="release">Release</option><option value="ongoing">Ongoing</option></SelectField>
      <SelectField label="Accepted category" value={filters.category} onChange={e=>set('category',e.target.value)}><option value="">All categories</option>{categories.map(x=><option key={x} value={x}>{humanLabel(x)}</option>)}</SelectField>
      <SelectField label="Work origin" value={filters.origin} onChange={e=>set('origin',e.target.value)}><option value="">All origins</option><option value="prospective">Prospective</option><option value="retrospective">Retrospective</option></SelectField>
      <SelectField label="Show one contributor (denominator unchanged)" value={filters.person_id} onChange={e=>set('person_id',e.target.value)}><option value="">All contributors</option>{people.map(p=><option key={p.user_id} value={p.user_id}>{p.display_name}</option>)}</SelectField></div>
      <p>Category and origin narrow the measured pool. Selecting one contributor only hides other rows; it never makes that person's share 100%.</p></section>
    {state.loading||state.error||!state.data?<Loading error={state.error} refresh={state.refresh}/>:<>
      <p>Captured {state.data.captured_at}. Fingerprint <code>{state.data.snapshot_hash}</code>.</p><p className="planning-warning">{state.data.denominator_label}</p>
      {!state.data.groups.length&&<section className="panel"><h3>No finalized credit in this scope</h3><p>Pending, unobserved or unreviewed work is not zero-value work.</p></section>}
      {state.data.groups.map(group=><section className="panel" key={group.policy_id+':'+group.pool_key}><h3>Policy {group.policy_version} · {group.pool_key} pool</h3><p>Scope: {filters.category||'all categories'} · {filters.origin||'all origins'}. Denominator: <strong>{formatUnits(group.denominator_atoms)} finalized units</strong>.</p>
        <p>{group.accepted_deliverable_count} accepted deliverables · {formatUnits(group.disputed_atoms)} units affected by open disputes.</p>
        <div className="table-scroll"><table><caption>Recognized contribution shares, alphabetically displayed</caption><thead><tr><th>Contributor</th><th>Finalized units</th><th>Share of displayed denominator</th></tr></thead><tbody>{group.people.map(person=><tr key={person.user_id}><th scope="row">{person.display_name}</th><td>{formatUnits(person.atoms)}</td><td>{formatFraction(person.share)} <span className="small">({formatUnits(person.atoms)} / {formatUnits(group.denominator_atoms)} units)</span></td></tr>)}</tbody></table></div>
        {!group.people.length&&<p>No displayed contributor row; the full scoped denominator is retained.</p>}
        <details><summary>Categories, origin and award references</summary><pre className="json-block">{JSON.stringify({categories:group.by_category,origin:group.by_origin,people:group.people},null,2)}</pre></details>
      </section>)}
      <section className="panel"><h3>Pending planned work</h3><p>{formatUnits(state.data.pending_planned_atoms)} unissued units under these policy, pool, category and origin filters. This is not contributor-owned credit and is not narrowed by the person display filter.</p><p>{state.data.evidence_notice}</p><p>Use Contributions for individual award history, Human reviews for evidence decisions, and Revenue simulator for separately labeled hypothetical money.</p></section>
      {state.data.activity&&<section className="panel"><h3>Observed GitHub activity — separate scope</h3>{!state.data.activity.available?<p>{state.data.activity.reason}</p>:<><p>{state.data.activity.scope}</p><p>{state.data.activity.notice}</p><p>Retained source versions: {state.data.activity.retained_version_count}</p><dl>{Object.entries(state.data.activity.unique_observed_entities??{}).map(([key,value])=><div key={key}><dt>{humanLabel(key)}</dt><dd>{value} unique observed entities</dd></div>)}</dl></>}</section>}
      <p>{state.data.notice}</p></>}
  </>;
}
