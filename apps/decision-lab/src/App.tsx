import { useEffect, useState } from 'react';
import { ErrorState, Loading, StatusLive } from './components/common';
import { parseHash, type Route, type View } from './lib/router';
import { useStore } from './store';
import { CasesView } from './views/Cases';
import { CompareView } from './views/Compare';
import { ProvenanceView } from './views/Provenance';
import { ReceiptView } from './views/Receipt';
import { ReplayView } from './views/Replay';
import { SandboxView } from './views/Sandbox';

const TABS: { view: View; label: string }[] = [
  { view: 'compare', label: 'Compare' },
  { view: 'cases', label: 'Cases' },
  { view: 'replay', label: 'Replay' },
  { view: 'sandbox', label: 'Sandbox' },
  { view: 'receipt', label: 'Receipt' },
  { view: 'provenance', label: 'Provenance' },
];

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export function App() {
  const route = useRoute();
  const { core, status, storedNotice, resetLedger } = useStore();

  useEffect(() => {
    const base = 'Entity Resolution Decision Lab';
    const tab = TABS.find((t) => t.view === route.view)?.label ?? 'Compare';
    if (route.view !== 'sandbox') document.title = `${tab} · ${base}`;
  }, [route.view]);

  let body;
  if (core.status === 'loading') body = <Loading what="the frozen evidence snapshot (manifest + snapshot)" />;
  else if (core.status === 'error') body = <ErrorState error={core.error} />;
  else {
    switch (route.view) {
      case 'compare':
        body = <CompareView route={route} />;
        break;
      case 'cases':
        body = <CasesView route={route} />;
        break;
      case 'replay':
        body = <ReplayView route={route} />;
        break;
      case 'sandbox':
        body = <SandboxView />;
        break;
      case 'receipt':
        body = <ReceiptView />;
        break;
      case 'provenance':
        body = <ProvenanceView />;
        break;
    }
  }

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="brand">
          <h1>Entity Resolution Decision Lab</h1>
          <nav aria-label="Site" className="external">
            <a href="../" data-testid="link-results">
              Results
            </a>
            <a href="../dbt/" data-testid="link-dbt">
              dbt docs
            </a>
          </nav>
        </div>
        <nav aria-label="Lab views">
          <ul className="tabs">
            {TABS.map((t) => (
              <li key={t.view}>
                <a href={`#/${t.view}`} aria-current={route.view === t.view ? 'page' : undefined} data-testid={`tab-${t.view}`}>
                  {t.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        {storedNotice ? (
          <div className="notice" role="alert" data-testid="stored-notice">
            {storedNotice}{' '}
            <button type="button" onClick={resetLedger}>
              reset stored decisions
            </button>
          </div>
        ) : null}
        {body}
      </main>
      <footer>
        <div className="inner">
          <span>Code: MIT licence (repository LICENSE). Data: CC0 as recorded in docs/DATA_SOURCES.md; it stays under data/ and never enters git.</span>
          <span>No analytics; local decisions stay in this browser.</span>
          <span>Test fold, one decision per A record; a retrospective workbench, not a production service.</span>
        </div>
      </footer>
      <StatusLive message={status} />
    </>
  );
}
