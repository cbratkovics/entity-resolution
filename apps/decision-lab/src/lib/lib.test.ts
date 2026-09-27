import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { sandboxV, type ExportedEvidenceRow } from './contracts';
import { casesWithEvents, consequences } from './consequences';
import { assumedEffort, evidenceSays, feasibleFloors, findFloorPoint, whatStayedFixed, whyTier } from './evidence';
import { fmtMetric } from './format';
import { appendEvent } from './ledger';
import { discogsLink, musicbrainzLink } from './links';
import { makePolicy } from './policy';
import { buildReceipt, importReceipt, receiptFileName, snapshotRef } from './receipt';
import { buildHash, parseHash } from './router';
import { checkExpectations, decideSandbox, joinDemo } from './sandbox';
import { parseCompareQuery, scenarioId, serialiseCompareQuery } from './scenario';
import { makeCase, makeManifest, makeSnapshot, TEST_A_ID } from './testdata';

describe('evidence panel rules', () => {
  const snapshot = makeSnapshot();
  it('names the highest F1, highest precision and smallest queue from the data', () => {
    const texts = evidenceSays(snapshot).map((s) => s.text);
    expect(texts[0]).toContain('rules_v1');
    expect(texts[0]).toContain('Highest F1');
    expect(texts[1]).toContain('learned_v1');
    expect(texts[1]).toContain('Highest labelled precision');
    expect(texts[2]).toContain('exact_v1');
    expect(texts[2]).toContain('Smallest review queue');
    expect(texts.some((t) => t.includes('highest-precision method (learned_v1) has lower reachable-labelled recall') && t.includes('lower coverage'))).toBe(true);
    expect(texts.some((t) => t.includes('different recorded thresholds') && t.includes('not an equal-recall comparison'))).toBe(true);
    expect(texts.some((t) => t.includes('rules_v1 score is an uncalibrated score'))).toBe(true);
  });
  it('renders zero-denominator metrics as unavailable, never 0 or 1', () => {
    const m = snapshot.methods.rules_v1?.metrics.precision_or_review;
    expect(fmtMetric(m)).toBe('unavailable (denominator 0)');
    expect(fmtMetric({ value: 1, numerator: 0, denominator: 0, source_key: 'x' })).toBe('unavailable (denominator 0)');
    expect(fmtMetric({ value: null, numerator: null, denominator: 5, source_key: 'x', unavailable_reason: 'not computed' })).toBe('unavailable (not computed)');
  });
});

describe('supported floor control', () => {
  const snapshot = makeSnapshot();
  const m = snapshot.methods.rules_v1!;
  it('finds only exported floors and never interpolates', () => {
    expect(findFloorPoint(m, 0.7)?.queue_total).toBe(2);
    expect(findFloorPoint(m, 0.6)).toBeNull();
    expect(whatStayedFixed(m)).toContain('accept_min = 0.9, ambiguity_gap = 0.1');
  });
  it('lists feasible floors largest first per method, or nothing', () => {
    const f = feasibleFloors(snapshot, 4);
    expect(f.map((x) => `${x.method}:${x.point.floor}`)).toEqual(['exact_v1:0.7', 'exact_v1:0.5', 'rules_v1:0.7', 'rules_v1:0.5', 'learned_v1:0.7', 'learned_v1:0.5']);
    expect(feasibleFloors(snapshot, 1)).toEqual([]);
    expect(feasibleFloors(snapshot, -1)).toEqual([]);
    expect(feasibleFloors(snapshot, 2.5)).toEqual([]);
  });
  it('assumed effort is minutes times queue, or null', () => {
    expect(assumedEffort(4, 3)).toEqual({ minutes: 12, hours: 0.2 });
    expect(assumedEffort(4, null)).toBeNull();
    expect(assumedEffort(4, -1)).toBeNull();
  });
});

describe('why this tier', () => {
  const row = makeCase().evidence[1] as ExportedEvidenceRow;
  const policy = { accept_min: 0.9, review_min: 0.5, ambiguity_gap: 0.1 };
  it('explains from rounded exported values and prefers the unrounded local gap', () => {
    const w = whyTier(row, policy, undefined);
    expect(w.basis).toBe('rounded_exported');
    expect(w.decision.tier).toBe('review');
    expect(w.matches_exported_tier).toBe(true);
    const local = whyTier(row, policy, 0.15);
    expect(local.basis).toBe('unrounded_local');
    expect(local.decision.ambiguous).toBe(false);
  });
  it('flags a rounded boundary', () => {
    const w = whyTier({ ...row, top2_gap: 0.1, gap_at_rounded_boundary: true }, policy, null);
    expect(w.lines.some((l) => l.includes('rounded gap equals the threshold'))).toBe(true);
  });
});

describe('links', () => {
  it('allowlists only the two hosts and only contract-shaped ids', () => {
    expect(musicbrainzLink(TEST_A_ID)).toBe(`https://musicbrainz.org/release-group/${TEST_A_ID}`);
    expect(musicbrainzLink('not-a-uuid')).toBeNull();
    expect(musicbrainzLink('javascript:alert(1)')).toBeNull();
    expect(discogsLink('123')).toBe('https://www.discogs.com/master/123');
    expect(discogsLink('0123')).toBeNull();
    expect(discogsLink('1234567890123')).toBeNull();
  });
});

describe('scenario ids and compare query', () => {
  it('produces contract-shaped ids', () => {
    expect(scenarioId({ kind: 'native', method: 'rules_v1' })).toBe('native:rules_v1');
    expect(scenarioId({ kind: 'supported_floor', method: 'rules_v1', floor: 0.5 })).toBe('floor:rules_v1:0.5');
    expect(scenarioId({ kind: 'replay', method: 'rules_v1', policy: makePolicy(0.65, 0.0756756772994995, 0.1) })).toBe('replay:rules_v1:0.65:0.0756756772994995:0.1');
    expect(scenarioId({ kind: 'synthetic', preset: 'native 0.95' })).toBe('synthetic:native_0.95');
  });
  it('parses and serialises the compare query without rationale or events', () => {
    const q = parseCompareQuery(new URLSearchParams('method=rules_v1&floor=0.5&budget=20000&minutes=2.5'));
    expect(q).toEqual({ method: 'rules_v1', floor: 0.5, budget: 20000, minutes: 2.5 });
    expect(serialiseCompareQuery(q)).toBe('?method=rules_v1&floor=0.5&budget=20000&minutes=2.5');
    expect(parseCompareQuery(new URLSearchParams('method=evil&floor=abc&budget=-1'))).toEqual({ method: null, floor: null, budget: null, minutes: null });
  });
  it('routes hashes', () => {
    expect(parseHash('#/cases/abc?x=1')).toMatchObject({ view: 'cases', caseId: 'abc' });
    expect(parseHash('')).toMatchObject({ view: 'compare', caseId: null });
    expect(parseHash('#/nope')).toMatchObject({ view: 'compare' });
    expect(buildHash('cases', { caseId: 'a b' })).toBe('#/cases/a%20b');
  });
});

describe('consequences', () => {
  const c = makeCase();
  const base = { snapshot_id: 's', scenario_id: 'native:rules_v1', a_id: TEST_A_ID, method_version: 'rules_v1' as const, evidence_ref: { case_id: TEST_A_ID, source: 'cases.json' as const } };
  it('counts accepted, changed, deferred and unresolved for the explicit set only', () => {
    let ev = appendEvent([], { ...base, action: 'accept_candidate', b_id: '111', reason_code: 'evidence_sufficient', rationale: null });
    let q = consequences(ev, 'native:rules_v1', 'rules_v1', [c]);
    expect(q).toMatchObject({ cases_in_set: 1, cases_with_events: 1, accepted_mappings: 1, changed_vs_baseline: 1, unresolved: 0, deferred: 0 });
    expect(consequences(ev, 'native:exact_v1', 'exact_v1', [c]).accepted_mappings).toBe(0);
    ev = appendEvent(ev, { ...base, action: 'accept_candidate', b_id: '222', reason_code: 'evidence_sufficient', rationale: null });
    q = consequences(ev, 'native:rules_v1', 'rules_v1', [c]);
    expect(q.changed_vs_baseline).toBe(0);
    ev = appendEvent(ev, { ...base, action: 'reject_candidate', b_id: '222', reason_code: 'candidate_wrong_work', rationale: null });
    ev = appendEvent(ev, { ...base, action: 'defer', b_id: null, reason_code: 'needs_source_lookup', rationale: null });
    q = consequences(ev, 'native:rules_v1', 'rules_v1', [c]);
    expect(q).toMatchObject({ accepted_mappings: 0, rejected_candidates: 1, deferred: 1, unresolved: 1 });
    expect(casesWithEvents(ev, 'native:rules_v1', [c, makeCase({ a_id: 'ffffffff-0000-0000-0000-000000000000', case_id: 'ffffffff-0000-0000-0000-000000000000' })])).toHaveLength(1);
  });
});

describe('receipts', () => {
  const manifest = makeManifest();
  const snapshot = makeSnapshot();
  const draft = {
    decision_question: 'q',
    queue_budget: 10,
    review_minutes_per_row: null,
    notes: '',
    user_observations: [{ claim: 'c', value: 'v', source_key: 'user', verified_by: 'user' as const }],
    extra_assumptions: ['a'],
    alternatives: [{ option: 'o', why_not: 'w' }],
    chosen_action: 'defer' as const,
    rationale: 'r',
    extra_limitations: ['l'],
  };
  it('builds a contract-valid receipt with artifact observations and refuses sandbox scenarios', () => {
    const r = buildReceipt(manifest, snapshot, { kind: 'supported_floor', method: 'rules_v1', floor: 0.7 }, draft, null);
    expect(r.selected_controls).toMatchObject({ control_kind: 'supported_floor', review_floor: 0.7, scenario_id: 'floor:rules_v1:0.7' });
    expect(r.observations.some((o) => o.verified_by === 'artifact' && o.claim.includes('queue_total'))).toBe(true);
    expect(r.observations.some((o) => o.verified_by === 'user')).toBe(true);
    expect(r.limitations).toContain('curated, not representative');
    expect(r.limitations.some((l) => l.includes('learned replay unavailable'))).toBe(true);
    expect(r.outcome).toEqual({ status: 'not_observed', measured_value: null });
    expect(receiptFileName(r)).toBe(`receipt-${manifest.snapshot_id}-${r.receipt_id}.json`);
    const rt = importReceipt(JSON.stringify(r), snapshotRef(manifest));
    expect(rt.status).toBe('ok');
  });
  it('rejects receipts from another snapshot or the sandbox with a quarantine summary', () => {
    const r = buildReceipt(manifest, snapshot, { kind: 'native', method: 'rules_v1' }, draft, null);
    const other = { ...r, snapshot: { ...r.snapshot, analytical_digest: 'e'.repeat(64) } };
    const res = importReceipt(JSON.stringify(other), snapshotRef(manifest));
    expect(res.status).toBe('rejected');
    if (res.status === 'rejected') {
      expect(res.reason).toBe('incompatible_snapshot');
      expect(res.quarantine?.receipt_id).toBe(r.receipt_id);
    }
    const syn = { ...r, selected_controls: { ...r.selected_controls, scenario_id: 'synthetic:x' } };
    const rs = importReceipt(JSON.stringify(syn), snapshotRef(manifest));
    expect(rs.status === 'rejected' && rs.reason === 'synthetic').toBe(true);
    expect(importReceipt('{', snapshotRef(manifest)).status).toBe('rejected');
  });
});

describe('sandbox mechanics', () => {
  const p = fileURLToPath(new URL('../../fixtures/synthetic_sandbox.json', import.meta.url));
  it.skipIf(!existsSync(p))('reproduces every expected value of the generated fixture for every preset', () => {
    const d = sandboxV(JSON.parse(readFileSync(p, 'utf8')), '$');
    let compared = 0;
    for (const preset of d.policies) {
      const policy = makePolicy(preset.policy.accept_min, preset.policy.review_min, preset.policy.ambiguity_gap);
      for (const c of d.cases) {
        const checks = checkExpectations(d, c.case_id, preset.preset, policy);
        for (const k of checks) {
          expect(k.ok, `${c.case_id} ${preset.preset} ${k.key}.${k.field}: expected ${JSON.stringify(k.expected)} got ${JSON.stringify(k.actual)}`).toBe(true);
          compared += 1;
        }
      }
    }
    expect(compared).toBeGreaterThan(0);
    const j = joinDemo(d);
    expect(j.inflated).toBe(j.joined_rows !== j.conserved_row_count);
    const first = d.cases[0]!;
    const dec = decideSandbox(d, first.a_id, 'synthetic_rules_like', makePolicy(0.95, 0.5, 0.1));
    expect(['auto_accept', 'review', 'reject']).toContain(dec.decision.tier);
  });
});
