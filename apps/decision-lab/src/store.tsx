/**
 * App state: the core evidence (manifest + snapshot), the selected real scenario, the decision
 * ledger and lazy caches for cases, replay bundles and the sandbox fixture.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { LabCases, LabManifest, LabSnapshot, MethodVersion, ReviewEvent, SnapshotRef, SyntheticSandbox } from './lib/contracts';
import { loadCases, loadManifest, loadReplayBundle, loadSandbox, loadSnapshot, LoadError, type ReplayBundle } from './lib/data';
import {
  appendEvent,
  appendUndo,
  clearStoredLedger,
  importLedger,
  readStoredLedger,
  writeStoredLedger,
  type ImportResult,
  type NewEventInput,
} from './lib/ledger';
import { methodOrder } from './lib/evidence';
import { snapshotRef } from './lib/receipt';
import { scenarioId, type RealScenario } from './lib/scenario';
import type { EvaluateResult } from './lib/policy';

export interface ReplayResult {
  scenario_id: string;
  method: MethodVersion;
  result: EvaluateResult;
}

export type CoreState =
  | { status: 'loading' }
  | { status: 'error'; error: LoadError }
  | { status: 'ready'; manifest: LabManifest; snapshot: LabSnapshot; ref: SnapshotRef };

export type Lazy<T> = { status: 'idle' } | { status: 'loading' } | { status: 'error'; error: LoadError } | { status: 'ready'; data: T };

interface AppStore {
  core: CoreState;
  scenario: RealScenario;
  setScenario: (s: RealScenario) => void;
  scenarioIdText: string;
  events: ReviewEvent[];
  storedNotice: string | null;
  record: (input: Omit<NewEventInput, 'snapshot_id'>) => void;
  undo: (target: { scenario_id: string; a_id: string; method_version: NewEventInput['method_version']; evidence_ref: NewEventInput['evidence_ref'] }) => void;
  importLedgerText: (text: string) => ImportResult | null;
  resetLedger: () => void;
  status: string;
  setStatus: (s: string) => void;
  cases: Lazy<LabCases>;
  ensureCases: () => void;
  replays: Record<string, Lazy<ReplayBundle>>;
  ensureReplay: (method: MethodVersion) => void;
  sandbox: Lazy<SyntheticSandbox>;
  ensureSandbox: () => void;
  lastReplay: ReplayResult | null;
  setLastReplay: (r: ReplayResult | null) => void;
}

const Ctx = createContext<AppStore | null>(null);

function asLoadError(e: unknown, file: string): LoadError {
  if (e instanceof LoadError) return e;
  return new LoadError('fetch_failed', file, e instanceof Error ? e.message : String(e));
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [core, setCore] = useState<CoreState>({ status: 'loading' });
  const [scenario, setScenarioState] = useState<RealScenario>({ kind: 'native', method: 'exact_v1' });
  const [events, setEvents] = useState<ReviewEvent[]>([]);
  const [storedNotice, setStoredNotice] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const [cases, setCases] = useState<Lazy<LabCases>>({ status: 'idle' });
  const [replays, setReplays] = useState<Record<string, Lazy<ReplayBundle>>>({});
  const [sandbox, setSandbox] = useState<Lazy<SyntheticSandbox>>({ status: 'idle' });
  const [lastReplay, setLastReplay] = useState<ReplayResult | null>(null);
  const refRef = useRef<SnapshotRef | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [manifest, snapshot] = await Promise.all([loadManifest(), loadSnapshot()]);
        if (cancelled) return;
        if (snapshot.snapshot_id !== manifest.snapshot_id) {
          throw new LoadError('malformed', 'snapshot.json', `malformed data: snapshot_id ${snapshot.snapshot_id} does not match the manifest ${manifest.snapshot_id}`);
        }
        const ref = snapshotRef(manifest);
        refRef.current = ref;
        const first = methodOrder(snapshot)[0];
        if (first) setScenarioState({ kind: 'native', method: first });
        const stored = readStoredLedger(ref);
        if (stored.status === 'ok') setEvents(stored.events);
        else if (stored.status === 'corrupt') setStoredNotice(`stored decisions could not be read (corrupt or incompatible); they were left untouched. Detail: ${stored.message}`);
        setCore({ status: 'ready', manifest, snapshot, ref });
      } catch (e) {
        if (!cancelled) setCore({ status: 'error', error: asLoadError(e, 'manifest.json') });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const persist = useCallback((next: ReviewEvent[]) => {
    setEvents(next);
    const ref = refRef.current;
    if (ref && !writeStoredLedger(ref, next)) setStatus('decisions could not be stored in this browser; they remain in memory for this session');
  }, []);

  const setScenario = useCallback((s: RealScenario) => {
    setScenarioState((prev) => (scenarioId(prev) === scenarioId(s) ? prev : s));
  }, []);

  const record = useCallback(
    (input: Omit<NewEventInput, 'snapshot_id'>) => {
      const ref = refRef.current;
      if (!ref) return;
      setEvents((prev) => {
        const next = appendEvent(prev, { ...input, snapshot_id: ref.snapshot_id });
        if (!writeStoredLedger(ref, next)) setStatus('decisions could not be stored in this browser; they remain in memory for this session');
        return next;
      });
      setStatus(`recorded ${input.action.replace('_', ' ')} for ${input.a_id}`);
    },
    [],
  );

  const undo = useCallback((target: { scenario_id: string; a_id: string; method_version: NewEventInput['method_version']; evidence_ref: NewEventInput['evidence_ref'] }) => {
    const ref = refRef.current;
    if (!ref) return;
    setEvents((prev) => {
      const next = appendUndo(prev, { ...target, snapshot_id: ref.snapshot_id });
      if (next.length === prev.length) {
        setStatus(`nothing to undo for ${target.a_id}`);
        return prev;
      }
      writeStoredLedger(ref, next);
      setStatus(`undid the last decision for ${target.a_id}`);
      return next;
    });
  }, []);

  const importLedgerText = useCallback(
    (text: string): ImportResult | null => {
      const ref = refRef.current;
      if (!ref) return null;
      const result = importLedger(text, ref, events);
      if (result.status === 'ok') {
        persist(result.events);
        setStatus(`imported ${result.imported} new event(s)`);
      } else {
        setStatus(`import rejected: ${result.message}`);
      }
      return result;
    },
    [events, persist],
  );

  const resetLedger = useCallback(() => {
    const ref = refRef.current;
    if (ref) clearStoredLedger(ref);
    setEvents([]);
    setStoredNotice(null);
    setStatus('local decisions were reset');
  }, []);

  const ensureCases = useCallback(() => {
    setCases((prev) => {
      if (prev.status !== 'idle') return prev;
      loadCases()
        .then((data) => {
          if (core.status === 'ready' && data.snapshot_id !== core.snapshot.snapshot_id) {
            setCases({ status: 'error', error: new LoadError('malformed', 'cases.json', `malformed data: cases.json is for snapshot ${data.snapshot_id}, not ${core.snapshot.snapshot_id}`) });
            return;
          }
          setCases({ status: 'ready', data });
        })
        .catch((e: unknown) => setCases({ status: 'error', error: asLoadError(e, 'cases.json') }));
      return { status: 'loading' };
    });
  }, [core]);

  const ensureReplay = useCallback(
    (method: MethodVersion) => {
      setReplays((prev) => {
        const cur = prev[method];
        if (cur && cur.status !== 'idle') return prev;
        const cap = core.status === 'ready' ? core.manifest.capabilities.complete_replay[method] : undefined;
        loadReplayBundle(method, cap?.meta_file, cap?.file)
          .then((data) => {
            if (core.status === 'ready' && data.meta.snapshot_id !== core.snapshot.snapshot_id) {
              setReplays((p) => ({ ...p, [method]: { status: 'error', error: new LoadError('malformed', `replay/replay_${method}.json`, `malformed data: replay bundle is for snapshot ${data.meta.snapshot_id}`) } }));
              return;
            }
            setReplays((p) => ({ ...p, [method]: { status: 'ready', data } }));
          })
          .catch((e: unknown) => setReplays((p) => ({ ...p, [method]: { status: 'error', error: asLoadError(e, `replay/replay_${method}.json`) } })));
        return { ...prev, [method]: { status: 'loading' } };
      });
    },
    [core],
  );

  const ensureSandbox = useCallback(() => {
    setSandbox((prev) => {
      if (prev.status !== 'idle') return prev;
      loadSandbox()
        .then((data) => setSandbox({ status: 'ready', data }))
        .catch((e: unknown) => setSandbox({ status: 'error', error: asLoadError(e, 'synthetic_sandbox.json') }));
      return { status: 'loading' };
    });
  }, []);

  const value = useMemo<AppStore>(
    () => ({
      core,
      scenario,
      setScenario,
      scenarioIdText: scenarioId(scenario),
      events,
      storedNotice,
      record,
      undo,
      importLedgerText,
      resetLedger,
      status,
      setStatus,
      cases,
      ensureCases,
      replays,
      ensureReplay,
      sandbox,
      ensureSandbox,
      lastReplay,
      setLastReplay,
    }),
    [core, scenario, setScenario, events, storedNotice, record, undo, importLedgerText, resetLedger, status, cases, ensureCases, replays, ensureReplay, sandbox, ensureSandbox, lastReplay],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): AppStore {
  const v = useContext(Ctx);
  if (!v) throw new Error('useStore outside AppProvider');
  return v;
}

/** The ready core, or null while loading / on error. */
export function useCore(): Extract<CoreState, { status: 'ready' }> | null {
  const { core } = useStore();
  return core.status === 'ready' ? core : null;
}
