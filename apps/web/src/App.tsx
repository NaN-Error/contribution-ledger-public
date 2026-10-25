import { sourceRelease } from './lib/release.js';
import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Icon } from './components/shared.js';
import { Feedback } from './components/forms.js';
import { Overview } from './features/Overview.js';
import { Setup } from './features/Setup.js';
import { AuthPortal } from './features/auth/AuthPortal.js';
import { Account } from './features/auth/Account.js';
import { MfaPanel, RecoveryCodes } from './features/auth/Mfa.js';
import { AnalysisHome } from './features/analysis/AnalysisHome.js';
import { api, explainError, loadSession, rememberSession } from './lib/api.js';
import { entryFromHash, authenticatedAppHash, type AuthSession, type Entry } from './lib/accounts.js';
import { useAction } from './hooks/useApi.js';

import { parseScenarioHash } from './lib/simulator.js';
import { ScenarioRoute } from './features/simulator/ScenarioRoute.js';

import { GitHubCallback } from './features/github/GitHubCallback.js';
import type { GitHubCallback as Callback } from './lib/github.js';

const Projects=lazy(()=>import('./features/projects/Projects.js').then(m=>({default:m.Projects})));
const GettingStarted=lazy(()=>import('./features/onboarding/GettingStarted.js').then(m=>({default:m.GettingStarted})));
const Roadmap=lazy(()=>import('./features/Roadmap.js').then(m=>({default:m.Roadmap})));

type Page = 'analysis' | 'guide' | 'projects' | 'account' | 'overview' | 'setup' | 'roadmap' | 'simulation' | 'github-callback';
function route(): Page { if(!window.location.hash||window.location.hash.startsWith('#analysis'))return 'analysis'; if(window.location.hash==='#github-callback')return 'github-callback'; if (parseScenarioHash(window.location.hash)) return 'simulation'; const value = window.location.hash.slice(1); return ['guide', 'account', 'overview', 'setup', 'roadmap'].includes(value) ? value as Page : 'projects'; }
const labels: Record<Page, string> = { analysis:'Repository dashboard', guide: 'Getting started', 'github-callback': 'GitHub authorization', simulation: 'Saved scenario', projects: 'Workspaces', account: 'Account and sessions', overview: 'System overview', setup: 'Local setup', roadmap: 'Project roadmap' };

export function App({ initialEntry = null, initialGitHub = null }: { initialEntry?: Entry | null; initialGitHub?: Callback|null }) {
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null); const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>(route); const [entry, setEntry] = useState<Entry | null>(initialEntry);
  const [portalOpen, setPortalOpen] = useState(!!initialEntry); const logout = useAction();
  const changeSession = useCallback((value: AuthSession) => { rememberSession(value); setSession(value); if (!value.user) setPortalOpen(true); }, []);
  const refresh = useCallback(() => { void loadSession().then(value => { changeSession(value); setError(null); }).catch(error => setError(explainError(error))); }, [changeSession]);
  useEffect(() => {
    refresh(); const timer = window.setInterval(refresh, 60000);
    const expired = () => { setSession(null); refresh(); };
    window.addEventListener('focus', refresh); window.addEventListener('ledger-session-expired', expired);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); window.removeEventListener('ledger-session-expired', expired); };
  }, [refresh]);
  useEffect(() => {
    const change = () => {
      if (window.location.hash === '#main-content') return;
      const next = entryFromHash(window.location.hash);
      if (next) { setEntry(next); setPortalOpen(true); if (next.token) window.history.replaceState(null, '', `${window.location.pathname}#${next.mode}`); }
      setPage(route());
    };
    window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change);
  }, []);
  useEffect(() => { document.title = `${session?.user ? labels[page] : 'Account access'} · Contribution ledger`; }, [page, session?.user?.id]);
  const finishFactor = (value: AuthSession) => { changeSession(value); setPortalOpen(false); setEntry(null); };
  const finishEnrollment = (value: AuthSession, codes: string[]) => { setRecoveryCodes(codes); finishFactor(value); };
  const closePortal = () => { setPortalOpen(false); setEntry(null); if (!parseScenarioHash(window.location.hash) && window.location.hash !== '#github-callback') window.location.hash = authenticatedAppHash(window.location.hash); setPage(route()); };
  if (error) return <main className="auth-shell"><section className="panel auth-card"><h1>Cannot check your session</h1><Feedback error={error} /><button className="button" onClick={refresh}>Retry connection</button><p>Keep the deployment running and check the local API logs. No saved account data is shown while access cannot be checked.</p></section></main>;
  if (!session) return <main className="auth-shell"><section className="panel auth-card"><h1>Contribution ledger</h1><p role="status">Checking local session…</p></section></main>;
  if (recoveryCodes) return <RecoveryCodes codes={recoveryCodes} onDone={() => setRecoveryCodes(null)} />;
  if (session.mfa_required) return <main className="auth-shell"><section className="auth-card"><h1>Finish signing in</h1><MfaPanel session={session} onSession={finishFactor} onEnrollment={finishEnrollment}/><button className="button" onClick={() => void logout.run(() => api<AuthSession>('/api/v1/auth/logout','POST'), changeSession)}>Cancel and sign out</button><Feedback error={logout.error}/></section></main>;
  if (!session.user && page === 'setup') return <main><a href="#projects" className="button back-button">← Back to account access</a><Setup /></main>;
  if (!session.user || portalOpen || entry) return <main><AuthPortal key={entry?.token || 'account-portal'} session={session} entry={entry} onSession={changeSession} onClose={closePortal} /></main>;
  return <div className="app-layout" key={session.user.id}><a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="sidebar"><a href="#analysis" className="brand"><span className="brand-mark"><Icon name="layers" /></span><span>Contribution<span className="brand-light">ledger</span></span></a>
      <div className="workspace-label"><span className="workspace-avatar">CL</span><div><strong>{session.user.display_name}</strong><small>Signed-in local session</small></div></div>
      <p className="nav-label">Your application</p><nav aria-label="Main navigation">{(['analysis', 'guide', 'projects', 'account', 'overview', 'setup', 'roadmap'] as const).map(item => <a key={item} className={page === item ? 'active' : ''} aria-current={page === item ? 'page' : undefined} href={`#${item}`}><Icon name={item === 'projects' ? 'layers' : item === 'account' ? 'shield' : item === 'setup' ? 'terminal' : 'grid'} />{labels[item]}</a>)}</nav>
      <div className="sidebar-note"><Icon name="shield" /><strong>Evidence informs decisions.</strong><p>People approve credit.<br />Code calculates the totals.</p><button className="button" disabled={logout.pending} onClick={() => void logout.run(() => api<AuthSession>('/api/v1/auth/logout', 'POST'), value => { changeSession(value); setPage('projects'); })}>Sign out</button></div>
      <div className="sidebar-footer"><span className="local-dot" />Internal test candidate<span className="small">v{sourceRelease}</span></div>
    </aside><div className="main-area"><header className="topbar"><span>Contribution ledger <span className="separator">/</span><strong>{labels[page]}</strong></span><span className="topbar-label">Synthetic data · no money movement</span></header>
      <main id="main-content" tabIndex={-1}><Feedback error={logout.error} /><Suspense fallback={<p role="status">Loading page…</p>}>{page === 'analysis' ? <AnalysisHome /> : page === 'guide' ? <GettingStarted /> : page === 'github-callback' ? <GitHubCallback callback={initialGitHub} /> : page === 'simulation' ? <ScenarioRoute /> : page === 'projects' ? <Projects /> : page === 'account' ? <Account session={session} onSession={changeSession} onEnrollment={finishEnrollment} /> : page === 'overview' ? <Overview /> : page === 'setup' ? <Setup /> : <Roadmap />}</Suspense></main>
    </div></div>;
}
