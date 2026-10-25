import { useState } from 'react';
import { Badge, TextField } from '../../components/shared.js';
import { SelectField } from '../../components/forms.js';
import { stepsFor, type StartPath } from '../../lib/onboarding.js';

export function GettingStarted() {
  const [path, setPath] = useState<StartPath>('manual');
  const [query, setQuery] = useState('');
  const steps = stepsFor(path, query);
  return <>
    <div className="page-heading"><div><p className="eyebrow">First complete workflow</p><h1>Getting started</h1>
      <p className="subtitle">Begin with fictional data and the manual workflow. GitHub and AI are optional.</p></div><Badge tone="warning">Internal test candidate</Badge></div>
    <section className="intro-panel"><div><h2>Source implementation is not deployment approval.</h2>
      <p>The application still needs installation, browser, native database and user verification. Financial records remain synthetic-only. No money is transferred.</p>
      <p>This guide does not approve policies, assign credit, or mark your project ready. Those actions remain in their separate authorized screens.</p></div></section>
    <section className="panel"><h2>Start with a repository report</h2><p>Open Repository dashboard, select a project and paste public GitHub repository links. Explore contributor usernames and source evidence, then add extra contributions and reasoned unit proposals. A draft report needs no policy or milestone. The steps below explain the separate formal review and approved-credit workflow.</p><a className="button primary" href="#analysis">Open repository dashboard</a></section>
    <div className="guide-controls"><SelectField label="Choose your starting path" value={path} onChange={event => setPath(event.target.value === 'existing' ? 'existing' : 'manual')}>
      <option value="manual">New project or manual evidence first</option><option value="existing">Existing repository and historical review</option></SelectField>
      <TextField label="Find a setup step" value={query} onChange={event => setQuery(event.target.value)} placeholder="For example: evidence or financial" /></div>
    <div className="guide-steps" aria-live="polite">{steps.length === 0 ? <section className="panel empty"><h2>No matching setup steps</h2><button className="button" onClick={() => setQuery('')}>Clear filter</button></section> : steps.map((step, index) =>
      <section className="panel guide-step" key={step.id}><div className="guide-step-heading"><span className="phase-number" aria-hidden="true">{index + 1}</span><div><p className="eyebrow">{step.location}</p><h2>{step.title}</h2></div></div>
        <p>{step.action}</p><p><strong>Check:</strong> {step.expected}</p><p className="small">{step.boundary}</p>
        <details><summary>Detailed guide in the source package</summary><code>{step.documentation}</code></details></section>)}</div>
    <section className="panel"><h2>Add AI only after the manual review works</h2><p>In AI settings, start with the synthetic provider. It deliberately returns insufficient evidence and cannot evaluate quality. Live analysis requires a permitted connection, an approved evidence profile, exact-packet disclosure approval, and the payer’s separate spending approval.</p>
      <p>The offline evaluation tools live in <code>scripts/evaluate.py</code>. Synthetic benchmark cases are not human pilot results or proof of fairness.</p></section>
    <section className="panel"><h2>Before testing with real people</h2><p>Use the backup and isolated recovery procedures. Keep live keys private. Review the relevant agreements and deployment checks. Two actual shadow-review periods remain a later human task, not a blocker to testing fictional data locally.</p>
      <p>Read <code>docs/user-guide/start_here.md</code> and <code>docs/release/readiness.md</code> in the extracted package.</p></section>
    <p><a className="button primary" href="#projects">Open workspaces</a> <a className="button secondary" href="#overview">Check service status</a></p>
  </>;
}
