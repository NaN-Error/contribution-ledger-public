import { useState } from 'react';
import { Badge } from '../../components/shared.js';
import { Loading, SelectField } from '../../components/forms.js';
import { useResource } from '../../hooks/useApi.js';
import type { Items, Project } from '../../lib/accounts.js';
import { humanLabel, type PolicyCollection, type PolicyTemplate } from '../../lib/planning.js';
import { PolicyDetail } from './PolicyDetail.js';
import { PolicyEditor } from './PolicyEditor.js';

export function Policies({ project }: { project: Project }) {
  const root = `/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/policies`;
  const state = useResource<PolicyCollection>(root); const templates = useResource<Items<PolicyTemplate>>(root + '/templates');
  const [selected, setSelected] = useState<string | null>(null); const [editing, setEditing] = useState(false); const [templateKey, setTemplateKey] = useState('release_only');
  if (state.loading || state.error || !state.data || templates.loading || templates.error || !templates.data) return <Loading error={state.error || templates.error} refresh={() => { state.refresh(); templates.refresh(); }} />;
  const chosen = state.data.items.find(x => x.id === selected) || state.data.items[0];
  const template = templates.data.items.find(x => x.key === templateKey) || templates.data.items[0];
  return <><div className="section-heading"><div><h2>Policies and agreement references</h2><p>Draft → administrative approval → participant acknowledgements → effective use.</p></div><button className="button" onClick={state.refresh}>Refresh policies</button></div>
    {project.can_manage && !editing && <div className="panel policy-start"><h3>{chosen ? 'Keep changes prospective' : 'Start with a draft example'}</h3><p>{chosen ? 'Create a successor revision instead of overwriting an approved document.' : 'Example ratios and terms are not automatically accepted. No policy is seeded at startup.'}</p>
      {!state.data.items.length && <SelectField label="Draft example" value={templateKey} onChange={e => setTemplateKey(e.target.value)}>{templates.data.items.map(item => <option key={item.key} value={item.key}>{item.title}</option>)}</SelectField>}
      <button className="button primary" onClick={() => setEditing(true)}>{state.data.items.length ? 'Create successor version' : 'Review draft example'}</button>
    </div>}
    {editing && project.can_manage && <PolicyEditor key={`${state.data.latest_version}-${templateKey}`} project={project} source={state.data.items[0] || null} template={template} latestVersion={state.data.latest_version} onCancel={() => setEditing(false)} onSaved={item => { setEditing(false); setSelected(item.id); state.refresh(); }} />}
    {!editing && !chosen && <section className="panel empty"><h3>No policy versions</h3><p>{project.can_manage ? 'Review a draft example above to start.' : 'A project administrator must create the first draft. You can review it here once available.'}</p></section>}
    {!editing && chosen && <><div className="policy-version-list" aria-label="Policy version history">{state.data.items.map(item => <button key={item.id} className={`button ${chosen.id === item.id ? 'primary' : ''}`} aria-pressed={chosen.id === item.id} onClick={() => setSelected(item.id)}>Version {item.version}<Badge>{humanLabel(item.state)}</Badge></button>)}</div>
      <PolicyDetail key={chosen.id} policy={chosen} path={root + '/' + chosen.id} canManage={project.can_manage} refresh={state.refresh} />
    </>}
  </>;
}
