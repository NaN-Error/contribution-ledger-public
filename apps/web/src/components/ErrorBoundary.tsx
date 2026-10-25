import { Component, type ErrorInfo, type ReactNode } from 'react';

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Do not log raw application state or future contributor evidence.
    console.error('The application interface encountered an error.');
  }
  render() {
    if (this.state.failed) return <main className="fatal" role="alert"><h1>The interface could not be displayed.</h1>
      <p>Reload the page. No server data was changed by this screen error.</p><button onClick={() => window.location.reload()}>Reload page</button></main>;
    return this.props.children;
  }
}
