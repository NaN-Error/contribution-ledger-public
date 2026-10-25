import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.js';
import { ErrorBoundary } from './components/ErrorBoundary.js';
import { entryFromHash } from './lib/accounts.js';
import { githubCallback } from './lib/github.js';
import { desktopToken, openDesktopSession } from './lib/desktop.js';
import { explainError } from './lib/api.js';
import './styles.css';

// Consume secret fragments once, outside React's development double-render.
// Fragments never reach HTTP logs. Remove them from this history entry promptly.
// OAuth codes arrive in the query; clear it before any session/API calls.
const launchToken = desktopToken(window.location.hash);
if (window.location.hash.startsWith('#desktop/')) window.history.replaceState(null, '', `${window.location.pathname}#analysis`);
const initialGitHub = githubCallback(window.location.href);
if(initialGitHub) window.history.replaceState(null, '', '/#github-callback');
const initialEntry = entryFromHash(window.location.hash);
if (initialEntry?.token) window.history.replaceState(null, '', `${window.location.pathname}#${initialEntry.mode}`);
const root = document.getElementById('root');
if (!root) throw new Error('Application root is missing.');
const reactRoot = createRoot(root);
function renderApp() { reactRoot.render(<StrictMode><ErrorBoundary><App initialEntry={initialEntry} initialGitHub={initialGitHub} /></ErrorBoundary></StrictMode>); }
if (launchToken) {
  reactRoot.render(<main className="auth-shell"><section className="panel auth-card"><h1>Contribution ledger</h1><p role="status">Opening your personal dashboard…</p></section></main>);
  void openDesktopSession(launchToken).then(renderApp).catch(error => {
    reactRoot.render(<main className="auth-shell"><section className="panel auth-card"><h1>Could not open the personal dashboard</h1><p role="alert">{explainError(error)}</p><p>Double-click Start.cmd again. Your saved projects are kept.</p><a className="button" href="/#analysis">Open ordinary account access</a></section></main>);
  });
} else renderApp();
