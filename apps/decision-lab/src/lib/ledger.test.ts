import { describe, expect, it } from 'vitest';
import type { ReviewEvent, SnapshotRef } from './contracts';
import { EVENT_ID } from './contracts';
import {
  appendEvent,
  appendUndo,
  checkLedger,
  effectiveState,
  effectiveStatus,
  exportLedger,
  importLedger,
  newEventId,
  readStoredLedger,
  storageKey,
  writeStoredLedger,
} from './ledger';
import { TEST_A_ID, TEST_SNAPSHOT_ID } from './testdata';

const ref: SnapshotRef = {
  snapshot_id: TEST_SNAPSHOT_ID,
  analytical_digest: 'c'.repeat(64),
  evaluation_code_commit: 'b'.repeat(40),
  feature_version: '0.0.0',
  lab_contract_version: '1.0',
};
const SCEN = 'native:rules_v1';
const base = { snapshot_id: TEST_SNAPSHOT_ID, scenario_id: SCEN, a_id: TEST_A_ID, method_version: 'rules_v1' as const, evidence_ref: { case_id: TEST_A_ID, source: 'cases.json' as const } };

function accept(events: ReviewEvent[], b: string): ReviewEvent[] {
  return appendEvent(events, { ...base, action: 'accept_candidate', b_id: b, reason_code: 'evidence_sufficient', rationale: null });
}
function reject(events: ReviewEvent[], b: string): ReviewEvent[] {
  return appendEvent(events, { ...base, action: 'reject_candidate', b_id: b, reason_code: 'candidate_wrong_work', rationale: 'wrong' });
}
function defer(events: ReviewEvent[]): ReviewEvent[] {
  return appendEvent(events, { ...base, action: 'defer', b_id: null, reason_code: 'needs_source_lookup', rationale: '' });
}

class MemoryStorage implements Storage {
  private m = new Map<string, string>();
  get length() {
    return this.m.size;
  }
  clear() {
    this.m.clear();
  }
  getItem(k: string) {
    return this.m.has(k) ? (this.m.get(k) as string) : null;
  }
  key(i: number) {
    return [...this.m.keys()][i] ?? null;
  }
  removeItem(k: string) {
    this.m.delete(k);
  }
  setItem(k: string, v: string) {
    this.m.set(k, v);
  }
}

describe('ledger events', () => {
  it('generates contract-shaped event ids', () => {
    for (let i = 0; i < 20; i += 1) expect(newEventId()).toMatch(EVENT_ID);
  });

  it('accept sets the effective B, a second accept supersedes it', () => {
    let ev = accept([], '111');
    expect(ev).toHaveLength(1);
    expect(ev[0]?.seq).toBe(1);
    expect(ev[0]?.supersedes_event_id).toBeNull();
    let s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(s.accepted_b).toBe('111');
    ev = accept(ev, '222');
    expect(ev[1]?.supersedes_event_id).toBe(ev[0]?.event_id);
    s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(s.accepted_b).toBe('222');
    expect(effectiveStatus(s)).toBe('accepted');
  });

  it('reject adds to the rejected set and only clears an accept of the same B', () => {
    let ev = accept([], '111');
    ev = reject(ev, '333');
    let s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(s.accepted_b).toBe('111');
    expect(s.rejected_b).toEqual(['333']);
    expect(ev[1]?.supersedes_event_id).toBeNull();
    ev = reject(ev, '111');
    expect(ev[2]?.supersedes_event_id).toBe(ev[0]?.event_id);
    s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(s.accepted_b).toBeNull();
    expect(s.rejected_b).toEqual(['111', '333']);
    expect(effectiveStatus(s)).toBe('rejected_only');
  });

  it('defer and undo restore the prior effective state by replay', () => {
    let ev = accept([], '111');
    ev = defer(ev);
    expect(effectiveStatus(effectiveState(ev, SCEN, TEST_A_ID))).toBe('accepted'); // accept stays, deferred flagged
    ev = reject(ev, '111');
    expect(effectiveStatus(effectiveState(ev, SCEN, TEST_A_ID))).toBe('deferred');
    ev = appendUndo(ev, base);
    const undoEv = ev[ev.length - 1] as ReviewEvent;
    expect(undoEv.action).toBe('undo');
    expect(undoEv.reason_code).toBe('reversal');
    expect(undoEv.reverses_event_id).toBe(ev[2]?.event_id);
    let s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(s.accepted_b).toBe('111');
    ev = appendUndo(ev, base); // reverses the defer
    ev = appendUndo(ev, base); // reverses the accept
    s = effectiveState(ev, SCEN, TEST_A_ID);
    expect(effectiveStatus(s)).toBe('none');
    const before = ev.length;
    ev = appendUndo(ev, base); // nothing left to undo
    expect(ev.length).toBe(before);
    expect(checkLedger(ev)).toBeNull();
    expect(ev.map((e) => e.seq)).toEqual(ev.map((_, i) => i + 1));
  });

  it('scopes effective state to the (scenario, a_id) pair', () => {
    const ev = accept([], '111');
    expect(effectiveState(ev, 'native:exact_v1', TEST_A_ID).accepted_b).toBeNull();
    expect(effectiveState(ev, SCEN, 'ffffffff-0000-0000-0000-000000000000').accepted_b).toBeNull();
  });

  it('truncates rationale to 2000 characters and stores empty as null', () => {
    const ev = appendEvent([], { ...base, action: 'defer', b_id: '999', reason_code: 'other', rationale: 'x'.repeat(3000) });
    expect(ev[0]?.rationale?.length).toBe(2000);
    expect(ev[0]?.b_id).toBeNull();
  });
});

describe('ledger persistence', () => {
  it('round-trips through storage under the namespaced key', () => {
    const st = new MemoryStorage();
    const ev = accept([], '111');
    expect(writeStoredLedger(ref, ev, st)).toBe(true);
    expect(st.getItem(storageKey(ref.snapshot_id, ref.analytical_digest))).not.toBeNull();
    const r = readStoredLedger(ref, st);
    expect(r.status).toBe('ok');
    if (r.status === 'ok') expect(r.events).toEqual(ev);
  });

  it('reports corrupt JSON and leaves it untouched', () => {
    const st = new MemoryStorage();
    st.setItem(storageKey(ref.snapshot_id, ref.analytical_digest), '{not json');
    const r = readStoredLedger(ref, st);
    expect(r.status).toBe('corrupt');
    expect(st.getItem(storageKey(ref.snapshot_id, ref.analytical_digest))).toBe('{not json');
  });

  it('reports an incompatible stored snapshot', () => {
    const st = new MemoryStorage();
    const other = { ...ref, analytical_digest: 'e'.repeat(64) };
    writeStoredLedger(other, accept([], '111'), st);
    st.setItem(storageKey(ref.snapshot_id, ref.analytical_digest), st.getItem(storageKey(other.snapshot_id, other.analytical_digest)) as string);
    expect(readStoredLedger(ref, st).status).toBe('corrupt');
  });

  it('is empty when nothing is stored or storage is unavailable', () => {
    expect(readStoredLedger(ref, new MemoryStorage()).status).toBe('empty');
    expect(readStoredLedger(ref, null).status).toBe('empty');
  });
});

describe('ledger export / import', () => {
  it('exports a contract-shaped document and re-imports it with parity', () => {
    const ev = reject(accept([], '111'), '222');
    const doc = exportLedger(ref, ev);
    expect(doc.review_events_version).toBe('1.0');
    const r = importLedger(JSON.stringify(doc), ref, []);
    expect(r.status).toBe('ok');
    if (r.status === 'ok') {
      expect(r.imported).toBe(2);
      expect(r.events).toHaveLength(2);
    }
    const again = importLedger(JSON.stringify(doc), ref, ev);
    expect(again.status).toBe('ok');
    if (again.status === 'ok') expect(again.imported).toBe(0);
  });

  it('rejects a different snapshot with a quarantine summary and applies nothing', () => {
    const doc = exportLedger({ ...ref, snapshot_id: '20260101T000000+0000@ffffffffffff' }, accept([], '111'));
    const r = importLedger(JSON.stringify(doc), ref, []);
    expect(r.status).toBe('rejected');
    if (r.status === 'rejected') {
      expect(r.reason).toBe('incompatible_snapshot');
      expect(r.quarantine?.event_count).toBe(1);
    }
    const doc2 = exportLedger({ ...ref, analytical_digest: 'f'.repeat(64) }, accept([], '111'));
    expect(importLedger(JSON.stringify(doc2), ref, []).status).toBe('rejected');
  });

  it('rejects corrupt JSON and contract violations', () => {
    expect(importLedger('nope', ref, []).status).toBe('rejected');
    const doc = exportLedger(ref, accept([], '111'));
    const bad = JSON.parse(JSON.stringify(doc)) as { events: Record<string, unknown>[] };
    (bad.events[0] as Record<string, unknown>).action = 'approve';
    const r = importLedger(JSON.stringify(bad), ref, []);
    expect(r.status).toBe('rejected');
    if (r.status === 'rejected') expect(r.reason).toBe('corrupt');
  });

  it('rejects a ledger whose seq is not contiguous', () => {
    const doc = exportLedger(ref, reject(accept([], '111'), '222'));
    (doc.events[1] as ReviewEvent) = { ...(doc.events[1] as ReviewEvent), seq: 5 };
    const r = importLedger(JSON.stringify(doc), ref, []);
    expect(r.status).toBe('rejected');
    if (r.status === 'rejected') expect(r.reason).toBe('invalid_ledger');
  });
});
