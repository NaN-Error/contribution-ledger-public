import { phaseStatus } from '../lib/onboarding.js';
import { sourcePhase } from '../lib/release.js';
import { useState } from 'react';
import { Badge, TextField } from '../components/shared.js';
import { filterPhases } from '../lib/roadmap.js';

export function Roadmap() {
  const [query, setQuery] = useState('');
  const filtered = filterPhases(query);
  return <><div className="page-heading"><div><p className="eyebrow">Development plan</p><h1>Project roadmap</h1><p className="subtitle">Build the manual workflow first. Add integrations without replacing human decisions.</p></div><Badge>16 planned phases</Badge></div>
    <section className="intro-panel"><div><h2>Evidence → human review → contribution credit</h2><p>AI assists evidence review; people approve contribution credit. The implementation includes synthetic financial closes and exports. Human pilot and deployment verification remain separate from source completion.</p></div></section>
    <TextField label="Filter the roadmap" placeholder="Search phases, such as GitHub or evidence" value={query} onChange={event => setQuery(event.target.value)} hint="This filters the development plan only; no server data is changed." />
    <div className="roadmap" aria-live="polite">{filtered.length === 0 ? <section className="panel empty"><h2>No matching phases</h2><p>Try a different word or clear the filter.</p><button className="button secondary" onClick={() => setQuery('')}>Clear filter</button></section> : filtered.map(phase => <section key={phase.number} className={`roadmap-row ${phase.number === sourcePhase ? 'current' : ''}`}><div className="phase-number">{String(phase.number).padStart(2, '0')}</div><div><h2>{phase.title}</h2><p>{phase.description}</p></div><Badge tone={phase.number >= 15 ? 'warning' : 'muted'}>{phase.number <= sourcePhase ? phaseStatus(phase.number) : 'Planned'}</Badge></section>)}</div>
    <p className="small muted">Implementation status and actual test evidence are tracked separately in docs/project_status.md.</p>
  </>;
}
