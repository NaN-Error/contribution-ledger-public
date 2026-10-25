import { sourcePhase } from '../lib/release.js';
import { Badge, Icon } from '../components/shared.js';
import { formatDate } from '../lib/status.js';
import { useSystemStatus } from '../hooks/useSystemStatus.js';

export function Overview() {
  const state = useSystemStatus();
  const data = state.data;
  const checking = state.loading && !data && !state.error;
  const dbOk = data?.database.status === 'ok';
  const schemaOk = data?.migrations.status === 'current';
  return <>
    <div className="page-heading"><div><p className="eyebrow">Development workspace</p><h1>System overview</h1><p className="subtitle">A working foundation for recognizing the work behind your project.</p></div>
      <button className="button secondary" onClick={state.refresh} disabled={state.loading}><Icon name="refresh" className={state.loading ? 'spinning' : ''} />{state.loading ? 'Checking…' : 'Refresh status'}</button></div>
    <section className="intro-panel"><div className="intro-icon"><Icon name="layers" /></div><div><div className="intro-title"><h2>Start with a dependable foundation.</h2><Badge>Source scope {sourcePhase} · test candidate</Badge></div>
      <p>Check the browser, API, and database here. Human review, finalized contribution units, and disputes now build on accounts, policies, work packages, and private evidence. Artifact storage is checked by evidence operations, not these database cards. Units are not money or ownership.</p></div></section>
    {state.error && <section className="error-panel" role="alert"><strong>Status check failed</strong><p>{state.error}</p>
      {state.lastSuccess && <p className="small">Last successful response: {formatDate(state.lastSuccess)}. Earlier results are no longer shown as current.</p>}
      {state.requestId && <p className="small">Request ID: <code>{state.requestId}</code></p>}
      <a href="#setup">Open local setup instructions <span aria-hidden="true">→</span></a></section>}
    <div className="service-grid" aria-live="polite" aria-busy={state.loading}>
      <Service title="Application API" icon="code" value={checking ? 'Checking…' : data ? 'Responding' : 'Not connected'}
        tone={data ? 'good' : checking ? 'muted' : 'warning'} detail={data ? `FastAPI · ${data.version}` : 'Waiting for a valid API response'} label="Backend" />
      <Service title="Database connection" icon="database" value={checking ? 'Checking…' : dbOk ? 'Connected' : data ? 'Unavailable' : 'Not checked'}
        tone={dbOk ? 'good' : checking ? 'muted' : 'warning'} detail={dbOk ? 'PostgreSQL · persistent storage' : 'The status is based on a live database query'} label="Database" />
      <Service title="Database migrations" icon="shield" value={checking ? 'Checking…' : schemaOk ? 'Up to date' : data?.migrations.status === 'pending' ? 'Action needed' : 'Not checked'}
        tone={schemaOk ? 'good' : checking ? 'muted' : 'warning'} detail={schemaOk ? `Revision ${data?.migrations.current_revision}` : 'Run the startup script to apply migrations'} label="Schema" />
    </div>
    <div className="section-heading"><h2>Foundation checks</h2><span className="muted small">Read-only diagnostics</span></div>
    <div className="details-grid"><section className="panel persistence"><div className="panel-heading"><Icon name="database" /><h3>Persistence check</h3><Badge tone={data?.persistence.status === 'present' ? 'good' : 'muted'}>{data?.persistence.status === 'present' ? 'Marker found' : data?.persistence.status === 'empty' ? 'Not seeded' : 'Not checked'}</Badge></div>
      {data?.persistence.status === 'present' ? <><p>A synthetic record is stored in the database. Its ID should remain the same after restarting the application.</p>
        <dl className="record"><dt>Marker ID</dt><dd data-testid="marker-id">{data.persistence.marker_id}</dd><dt>Created</dt><dd>{formatDate(data.persistence.created_at)}</dd></dl></>
        : <><p>No persistence result is available yet. Seeding is an explicit operator action, not something startup does automatically.</p>
          <div className="command"><span>PowerShell · project root</span><code>.\scripts\seed.ps1</code></div><a href="#setup">View the persistence walkthrough <span aria-hidden="true">→</span></a></>}
    </section><section className="panel"><div className="panel-heading"><Icon name="shield" /><h3>Local development only</h3></div>
      <p>This build includes login and scoped permissions, but deployment hardening and full-stack verification remain open. Keep it local and use synthetic data only.</p>
      <dl className="metadata"><div><dt>Environment</dt><dd>{data?.environment ?? 'Not checked'}</dd></div><div><dt>Development tools</dt><dd>{data ? data.development_tools_enabled ? 'Enabled' : 'Disabled' : 'Not checked'}</dd></div>
        <div><dt>GitHub / AI integrations</dt><dd>Optional · runtime verification open</dd></div><div><dt>Financial operations</dt><dd>Simulation only · no money movement</dd></div></dl>
    </section></div>
    <div className="next-panel"><div className="phase-number">16</div><div><p className="eyebrow">Next: local verification</p><h3>Walk through the complete synthetic workflow</h3><p>Accounts, evidence, review, contribution units, simulations and frozen synthetic distributions are in the source. Installation, browser and native-service checks remain open.</p></div><a className="button secondary" href="#guide">Getting started <Icon name="arrow" /></a></div>
    <footer className="page-footer"><span><span className="live-dot" />Checks refresh every 15 seconds while this page is open.</span><span>{data ? `Checked ${formatDate(data.checked_at)}` : 'No current status available'}</span></footer>
  </>;
}

function Service({ title, icon, value, tone, detail, label }: { title: string; icon: 'code' | 'database' | 'shield'; value: string; tone: 'good' | 'warning' | 'muted'; detail: string; label: string }) {
  return <section className="service panel" aria-label={title}><div className="service-heading"><span>{label}</span><Icon name={icon} /></div><h2>{value}</h2><Badge tone={tone}>{title}</Badge><p>{detail}</p></section>;
}
