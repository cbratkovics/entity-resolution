/**
 * The decision ledger: an append-only array of review events (lab_review_events contract),
 * persisted to localStorage under `erlab:v1:<snapshot_id>:<analytical_digest>`. Effective state
 * per (scenario_id, a_id) is derived by replaying the events and ignoring reversed ones. Nothing
 * here is a label, an upstream write or a measured outcome.
 */
import { reviewEventsV, type Action, type EventMethod, type ReasonCode, type ReviewEvent, type ReviewEventsExport, type SnapshotRef } from './contracts';
import { ValidationError } from './validate';

export const LEDGER_SCHEMA_PREFIX = 'erlab:v1';

export function storageKey(snapshotId: string, analyticalDigest: string): string {
  return `${LEDGER_SCHEMA_PREFIX}:${snapshotId}:${analyticalDigest}`;
}

export function newEventId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through to the fallback
  }
  const t = Date.now().toString(36);
  const r = Math.floor(Math.random() * 2 ** 48).toString(36);
  const r2 = Math.floor(Math.random() * 2 ** 48).toString(36);
  return `${t}-${r}-${r2}`.padEnd(8, '0').slice(0, 64);
}

export interface EffectiveState {
  accepted_b: string | null;
  accepted_event_id: string | null;
  rejected_b: string[];
  deferred: boolean;
  /** The latest un-reversed, non-undo event of this (scenario, a_id), if any. */
  last_event_id: string | null;
  event_count: number;
}

export const EMPTY_STATE: EffectiveState = Object.freeze({
  accepted_b: null,
  accepted_event_id: null,
  rejected_b: [],
  deferred: false,
  last_event_id: null,
  event_count: 0,
});

export function reversedIds(events: readonly ReviewEvent[]): Set<string> {
  const out = new Set<string>();
  for (const e of events) {
    if (e.action === 'undo' && e.reverses_event_id) out.add(e.reverses_event_id);
  }
  return out;
}

/** Live (un-reversed, non-undo) events of one (scenario, a_id) in seq order. */
export function liveEvents(events: readonly ReviewEvent[], scenarioId: string, aId: string): ReviewEvent[] {
  const reversed = reversedIds(events);
  return events
    .filter((e) => e.scenario_id === scenarioId && e.a_id === aId && e.action !== 'undo' && !reversed.has(e.event_id))
    .sort((a, b) => a.seq - b.seq);
}

export function effectiveState(events: readonly ReviewEvent[], scenarioId: string, aId: string): EffectiveState {
  const live = liveEvents(events, scenarioId, aId);
  let accepted: string | null = null;
  let acceptedId: string | null = null;
  const rejected = new Set<string>();
  let deferred = false;
  for (const e of live) {
    switch (e.action) {
      case 'accept_candidate':
        accepted = e.b_id;
        acceptedId = e.event_id;
        if (e.b_id) rejected.delete(e.b_id);
        deferred = false;
        break;
      case 'reject_candidate':
        if (e.b_id) {
          rejected.add(e.b_id);
          if (accepted === e.b_id) {
            accepted = null;
            acceptedId = null;
          }
        }
        break;
      case 'defer':
        deferred = true;
        break;
      case 'undo':
        break;
    }
  }
  const last = live[live.length - 1];
  return {
    accepted_b: accepted,
    accepted_event_id: acceptedId,
    rejected_b: [...rejected].sort(),
    deferred,
    last_event_id: last ? last.event_id : null,
    event_count: live.length,
  };
}

export type EffectiveStatus = 'accepted' | 'deferred' | 'rejected_only' | 'none';

export function effectiveStatus(s: EffectiveState): EffectiveStatus {
  if (s.accepted_b) return 'accepted';
  if (s.deferred) return 'deferred';
  if (s.rejected_b.length) return 'rejected_only';
  return 'none';
}

export interface NewEventInput {
  snapshot_id: string;
  scenario_id: string;
  a_id: string;
  method_version: EventMethod;
  action: Exclude<Action, 'undo'>;
  b_id: string | null;
  reason_code: ReasonCode;
  rationale: string | null;
  evidence_ref: { case_id: string; source: 'cases.json' | 'synthetic_sandbox' };
}

function nowIso(): string {
  return new Date().toISOString();
}

function nextSeq(events: readonly ReviewEvent[]): number {
  return events.reduce((m, e) => Math.max(m, e.seq), 0) + 1;
}

/** Append a decision event; returns the new ledger array (the input is not mutated). */
export function appendEvent(events: readonly ReviewEvent[], input: NewEventInput): ReviewEvent[] {
  const state = effectiveState(events, input.scenario_id, input.a_id);
  let supersedes: string | null = null;
  if (input.action === 'accept_candidate' && state.accepted_event_id) supersedes = state.accepted_event_id;
  if (input.action === 'reject_candidate' && input.b_id && state.accepted_b === input.b_id) supersedes = state.accepted_event_id;
  const rationale = input.rationale === null || input.rationale === '' ? null : input.rationale.slice(0, 2000);
  const ev: ReviewEvent = {
    event_id: newEventId(),
    seq: nextSeq(events),
    occurred_at_utc: nowIso(),
    snapshot_id: input.snapshot_id,
    scenario_id: input.scenario_id,
    a_id: input.a_id,
    method_version: input.method_version,
    action: input.action,
    b_id: input.action === 'defer' ? null : input.b_id,
    reason_code: input.reason_code,
    rationale,
    supersedes_event_id: supersedes,
    reverses_event_id: null,
    evidence_ref: input.evidence_ref,
  };
  return [...events, ev];
}

/** Append an undo of the latest live event of (scenario, a_id); returns the same array if none. */
export function appendUndo(
  events: readonly ReviewEvent[],
  target: { snapshot_id: string; scenario_id: string; a_id: string; method_version: EventMethod; evidence_ref: NewEventInput['evidence_ref'] },
  rationale: string | null = null,
): ReviewEvent[] {
  const state = effectiveState(events, target.scenario_id, target.a_id);
  if (!state.last_event_id) return events.slice();
  const ev: ReviewEvent = {
    event_id: newEventId(),
    seq: nextSeq(events),
    occurred_at_utc: nowIso(),
    snapshot_id: target.snapshot_id,
    scenario_id: target.scenario_id,
    a_id: target.a_id,
    method_version: target.method_version,
    action: 'undo',
    b_id: null,
    reason_code: 'reversal',
    rationale: rationale === null || rationale === '' ? null : rationale.slice(0, 2000),
    supersedes_event_id: null,
    reverses_event_id: state.last_event_id,
    evidence_ref: target.evidence_ref,
  };
  return [...events, ev];
}

/** Check the ledger invariants: seq contiguous from 1, unique ids, references resolve. */
export function checkLedger(events: readonly ReviewEvent[]): string | null {
  const ids = new Set<string>();
  const sorted = [...events].sort((a, b) => a.seq - b.seq);
  for (let i = 0; i < sorted.length; i += 1) {
    const e = sorted[i] as ReviewEvent;
    if (e.seq !== i + 1) return `seq is not contiguous at ${e.seq}`;
    if (ids.has(e.event_id)) return `duplicate event_id ${e.event_id}`;
    ids.add(e.event_id);
  }
  for (const e of events) {
    if (e.reverses_event_id && !ids.has(e.reverses_event_id)) return `reverses unknown event ${e.reverses_event_id}`;
    if (e.supersedes_event_id && !ids.has(e.supersedes_event_id)) return `supersedes unknown event ${e.supersedes_event_id}`;
    if (e.action === 'undo' && !e.reverses_event_id) return 'undo without reverses_event_id';
  }
  return null;
}

// ---------------------------------------------------------------- persistence

export type StoredLedgerResult =
  | { status: 'ok'; events: ReviewEvent[] }
  | { status: 'empty' }
  | { status: 'corrupt'; message: string };

/** Read the stored ledger; corrupt or incompatible JSON is reported, never applied or deleted. */
export function readStoredLedger(snapshot: SnapshotRef, storage: Storage | null = safeStorage()): StoredLedgerResult {
  if (!storage) return { status: 'empty' };
  let raw: string | null;
  try {
    raw = storage.getItem(storageKey(snapshot.snapshot_id, snapshot.analytical_digest));
  } catch {
    return { status: 'empty' };
  }
  if (raw === null || raw === '') return { status: 'empty' };
  try {
    const parsed = reviewEventsV(JSON.parse(raw), 'stored');
    if (parsed.snapshot.snapshot_id !== snapshot.snapshot_id || parsed.snapshot.analytical_digest !== snapshot.analytical_digest) {
      return { status: 'corrupt', message: 'stored decisions belong to a different snapshot' };
    }
    const problem = checkLedger(parsed.events);
    if (problem) return { status: 'corrupt', message: problem };
    return { status: 'ok', events: parsed.events };
  } catch (e) {
    return { status: 'corrupt', message: e instanceof ValidationError ? e.message : 'not valid JSON' };
  }
}

export function writeStoredLedger(snapshot: SnapshotRef, events: readonly ReviewEvent[], storage: Storage | null = safeStorage()): boolean {
  if (!storage) return false;
  try {
    storage.setItem(storageKey(snapshot.snapshot_id, snapshot.analytical_digest), JSON.stringify(exportLedger(snapshot, events)));
    return true;
  } catch {
    return false;
  }
}

export function clearStoredLedger(snapshot: SnapshotRef, storage: Storage | null = safeStorage()): void {
  if (!storage) return;
  try {
    storage.removeItem(storageKey(snapshot.snapshot_id, snapshot.analytical_digest));
  } catch {
    // ignore
  }
}

export function safeStorage(): Storage | null {
  try {
    if (typeof localStorage !== 'undefined') return localStorage;
  } catch {
    // access can throw in restricted contexts
  }
  return null;
}

// ---------------------------------------------------------------- export / import

export function exportLedger(snapshot: SnapshotRef, events: readonly ReviewEvent[]): ReviewEventsExport {
  return {
    review_events_version: '1.0',
    snapshot: { ...snapshot },
    exported_at_utc: nowIso(),
    events: [...events].sort((a, b) => a.seq - b.seq),
  };
}

export type ImportResult =
  | { status: 'ok'; events: ReviewEvent[]; imported: number }
  | { status: 'rejected'; reason: 'corrupt' | 'incompatible_snapshot' | 'invalid_ledger'; message: string; quarantine: QuarantineSummary | null };

export interface QuarantineSummary {
  snapshot_id: string;
  analytical_digest: string;
  event_count: number;
  exported_at_utc: string;
}

/**
 * Validate an exported ledger and merge it into the current one. The snapshot block must match
 * the loaded evidence (snapshot_id and analytical_digest); otherwise nothing is applied and a
 * quarantine summary is returned for display. Imported events that already exist (same event_id)
 * are skipped; new ones are re-sequenced after the current tail.
 */
export function importLedger(text: string, snapshot: SnapshotRef, current: readonly ReviewEvent[]): ImportResult {
  let parsed: ReviewEventsExport;
  try {
    parsed = reviewEventsV(JSON.parse(text), 'import');
  } catch (e) {
    return {
      status: 'rejected',
      reason: 'corrupt',
      message: e instanceof ValidationError ? `the file does not match the review-events contract (${e.message})` : 'the file is not valid JSON',
      quarantine: null,
    };
  }
  const quarantine: QuarantineSummary = {
    snapshot_id: parsed.snapshot.snapshot_id,
    analytical_digest: parsed.snapshot.analytical_digest,
    event_count: parsed.events.length,
    exported_at_utc: parsed.exported_at_utc,
  };
  if (parsed.snapshot.snapshot_id !== snapshot.snapshot_id || parsed.snapshot.analytical_digest !== snapshot.analytical_digest) {
    return { status: 'rejected', reason: 'incompatible_snapshot', message: 'incompatible snapshot: the file was exported from different evidence', quarantine };
  }
  const problem = checkLedger(parsed.events);
  if (problem) return { status: 'rejected', reason: 'invalid_ledger', message: `the ledger is inconsistent: ${problem}`, quarantine };
  for (const e of parsed.events) {
    if (e.snapshot_id !== snapshot.snapshot_id) {
      return { status: 'rejected', reason: 'incompatible_snapshot', message: `event ${e.event_id} names a different snapshot`, quarantine };
    }
  }
  const known = new Set(current.map((e) => e.event_id));
  const merged = [...current];
  let imported = 0;
  for (const e of [...parsed.events].sort((a, b) => a.seq - b.seq)) {
    if (known.has(e.event_id)) continue;
    merged.push({ ...e, seq: nextSeq(merged) });
    known.add(e.event_id);
    imported += 1;
  }
  const check = checkLedger(merged);
  if (check) return { status: 'rejected', reason: 'invalid_ledger', message: `merge would break the ledger: ${check}`, quarantine };
  return { status: 'ok', events: merged, imported };
}
