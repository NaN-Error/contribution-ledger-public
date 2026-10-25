import { Badge } from '../components/shared.js';
export function Setup() {
  return <><div className="page-heading"><div><p className="eyebrow">Operator guide</p><h1>Local setup</h1><p className="subtitle">Run these commands in PowerShell from the contribution-ledger folder.</p></div><Badge>Windows workflow</Badge></div>
    <section className="intro-panel"><div><h2>Invited accounts, local deployment</h2><p>Accounts and scoped project permissions are implemented. This is still an unverified local pilot: keep ports private and use synthetic data. No GitHub or AI credentials are needed.</p></div></section>
    <div className="guide-grid"><Guide number="01" title="Start the application" command={'.\\scripts\\start.ps1'}>The script checks Docker, preserves existing configuration, starts PostgreSQL, applies additive migrations, and starts the web app. It does not create an account.</Guide>
      <Guide number="02" title="Create the first owner" command={'.\\scripts\\setup-owner.ps1'}>The operator receives a one-hour single-use setup token. Enter it in the first-owner screen and choose your own email, passphrase, workspace, and project. There is no default password.</Guide>
      <Guide number="03" title="Restart without deleting data" command={'.\\scripts\\stop.ps1\n.\\scripts\\start.ps1'}>The named database and private evidence volumes are preserved, including accounts, history and artifacts. Volumes are not backups.</Guide>
      <Guide number="04" title="Inspect services and logs" command={'.\\scripts\\doctor.ps1\n.\\scripts\\logs.ps1'}>After signing in, System overview shows live checks. Keep .env, setup tokens, invitation links, and passwords out of shared logs and support messages.</Guide>
    </div><section className="panel"><h2>Invitations and account recovery</h2><p>Workspace owners and administrators create invitations from the workspace's Invitations section. Send the one-time link privately. No email service is connected, and localhost links cannot reach another person's computer.</p>
      <p>For lost passwords, the operator verifies the person's identity and issues a 30-minute recovery token. The command revokes existing sessions. The user sets their own password in Account recovery; the operator does not sign in as them.</p>
      <pre><code>{'.\\scripts\\account.ps1 -Action recover -Email "person@example.test" -Reason "Verified account owner requested recovery"'}</code></pre></section>
    <section className="panel"><h2>Optional synthetic test team</h2><p>After first-owner setup, this explicit development command creates two isolated workspaces, two test owners, five test contributors, and a separate fictional reviewer. Random passwords appear once. Running it again does not reset them.</p><pre><code>{'.\\scripts\\seed-team.ps1'}</code></pre>
      <p>The earlier reset-development command deletes only the persistence marker, never these accounts or audit records. There is no account reset during normal startup.</p></section>
    <section className="panel guide-note"><h2>Testing remains recorded separately</h2><p>The included tests cover API behavior and access boundaries. Full Docker, Windows, native PostgreSQL, and actual React browser verification are still separate checks. See docs/testing.md and docs/account_access.md.</p></section>
  </>;
}
function Guide({ number, title, command, children }: { number: string; title: string; command: string; children: string }) {
  return <section className="panel guide-card"><span className="step-number">{number}</span><h2>{title}</h2><p>{children}</p><pre><code>{command}</code></pre></section>;
}
