import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { Loading, SelectField } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import type { Project } from '../../lib/accounts.js';
import { categories, formatUnits, humanLabel } from '../../lib/planning.js';
import { workStates, type WorkCollection, type WorkOptions } from '../../lib/workPackages.js';
import { ScopeEditor } from './ScopeEditor.js';
import { WorkPackageDetail } from './WorkPackageDetail.js';

export function WorkPackages({ project }: { project: Project }) {
  const root = `/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/work-packages`;
  const [selected, setSelected] = useState<string | null>(null); const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState(''); const [status, setStatus] = useState(''); const [category, setCategory] = useState(''); const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ q: query, category, offset: String(offset) }); if (status) params.set('state', status);
  const state = useResource<WorkCollection>(`${root}?${params}`); const options = useResource<WorkOptions>(root + '/options');
  const refresh = () => { state.refresh(); options.refresh(); };
  if (options.loading || options.error || !options.data) return <Loading error={options.error} refresh={refresh} />;
  if (selected) return <WorkPackageDetail key={selected} root={root} packageId={selected} options={options.data} onBack={() => { setSelected(null); refresh(); }} />;
  if (creating) return <ScopeEditor root={root} options={options.data} onSaved={item => { setCreating(false); setSelected(item.id); refresh(); }} onCancel={() => setCreating(false)} />;
  return <><div className="section-heading"><div><h2>Work packages</h2><p>Define useful outcomes, plan their attribution, and preserve revisions. No contribution units are earned here.</p></div><div className="button-row"><button className="button" onClick={refresh}>Refresh work packages</button>
    {options.data.can_create && <button className="button primary" disabled={!options.data.allocations.length} onClick={() => setCreating(true)}>Create work package</button>}</div></div>
    {options.data.can_create && !options.data.allocations.length && <section className="panel"><h3>An approved, unlinked allocation is required</h3><p>Open Milestones, select an active milestone, propose an allocation for this work, and approve that budget proposal. Then refresh this page. Each allocation can belong to only one work package.</p></section>}
    {options.data.allocations_truncated && <p className="planning-warning">The allocation selector reached its local-pilot limit. It does not show every available allocation.</p>}
    <div className="work-filters"><TextField label="Search work packages" maxLength={120} value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} placeholder="Title or coordinator" />
      <SelectField label="Work-package state" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">All states</option>{workStates.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</SelectField>
      <SelectField label="Work category" value={category} onChange={e => { setCategory(e.target.value); setOffset(0); }}><option value="">All categories</option>{categories.map(value => <option key={value} value={value}>{humanLabel(value)}</option>)}</SelectField></div>
    {state.loading || state.error || !state.data ? <Loading error={state.error} refresh={state.refresh} /> : <>
      <p className="small muted">{state.data.total} matching packages. A package becomes completed only after every deliverable has been independently accepted and its credit finalized.</p>
      <div className="project-grid">{state.data.items.length ? state.data.items.map(item => <button className="project-card" key={item.id} onClick={() => setSelected(item.id)}><strong>{item.title}</strong><p>{item.milestone_name} · {humanLabel(item.origin)}<br />{formatUnits(item.budget_atoms)} current planned units · {item.category}</p><Badge>{humanLabel(item.state)}</Badge><small>Coordinator: {item.coordinator_name}<br />Scope revision {item.scope_revision}</small></button>) : <section className="panel empty"><h3>No matching work packages</h3><p>Change the filters or create a package using an approved work allocation.</p></section>}</div>
      <div className="button-row"><button className="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous page</button><button className="button" disabled={state.data.next_offset === null} onClick={() => state.data?.next_offset != null && setOffset(state.data.next_offset)}>Next page</button></div>
    </>}</>;
}
