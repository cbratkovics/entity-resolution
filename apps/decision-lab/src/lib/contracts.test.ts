import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { casesV, manifestV, receiptV, sandboxV, snapshotV } from './contracts';
import { makeCase, makeManifest, makeSnapshot, TEST_SNAPSHOT_ID } from './testdata';
import { ValidationError, parseAndValidate } from './validate';

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

describe('manifest validator', () => {
  it('accepts a valid manifest and rejects unknown keys, bad ids and missing keys', () => {
    const m = makeManifest();
    expect(manifestV(clone(m), '$').snapshot_id).toBe(TEST_SNAPSHOT_ID);
    const extra = clone(m) as unknown as Record<string, unknown>;
    extra.surprise = 1;
    expect(() => manifestV(extra, '$')).toThrow(ValidationError);
    const badId = clone(m);
    badId.snapshot_id = 'not-a-snapshot-id';
    expect(() => manifestV(badId, '$')).toThrow(/snapshot_id/);
    const missing = clone(m) as unknown as Record<string, unknown>;
    delete missing.build;
    expect(() => manifestV(missing, '$')).toThrow(/build/);
    const badRole = clone(m);
    (badRole.sources[0] as { role: string }).role = 'other';
    expect(() => manifestV(badRole, '$')).toThrow(/role/);
    const badMethod = clone(m) as unknown as { capabilities: { complete_replay: Record<string, unknown> } };
    badMethod.capabilities.complete_replay.other_v9 = { available: false, note: '', decision_value_kind: 'unavailable' };
    expect(() => manifestV(badMethod, '$')).toThrow(/other_v9/);
  });
});

describe('snapshot validator', () => {
  it('accepts a valid snapshot and rejects a missing required metric', () => {
    const s = makeSnapshot();
    expect(Object.keys(snapshotV(clone(s), '$').methods)).toEqual(['exact_v1', 'rules_v1', 'learned_v1']);
    const bad = clone(s) as unknown as { methods: { rules_v1: { metrics: Record<string, unknown> } } };
    delete bad.methods.rules_v1.metrics.f1;
    expect(() => snapshotV(bad, '$')).toThrow(/f1/);
    const badStatus = clone(s);
    (badStatus.methods.rules_v1 as { legacy_threshold_sweep: { status: string } }).legacy_threshold_sweep.status = 'fresh';
    expect(() => snapshotV(badStatus, '$')).toThrow(/status/);
  });

  it('treats non-JSON text as malformed', () => {
    expect(() => parseAndValidate('{oops', snapshotV)).toThrow(/not valid JSON/);
    expect(() => parseAndValidate('[]', snapshotV)).toThrow(ValidationError);
  });
});

describe('cases validator', () => {
  it('accepts the two evidence-row shapes and both label states', () => {
    const doc = {
      lab_cases_version: '1.0',
      snapshot_id: TEST_SNAPSHOT_ID,
      policies: { rules_v1: { accept_min: 0.9, review_min: 0.5, ambiguity_gap: 0.1, score_kind: 'uncalibrated_score', source_key: 'x' } },
      selection: { strategy_version: 't', total_cases: 2, counts_by_reason: { methods_disagree: 2 }, criteria: [], limitations: [], local_evidence: { available: false, note: 'n' } },
      cases: [
        makeCase(),
        makeCase({
          labels: {
            state: 'verified_local',
            labelled: true,
            truth_b_ids: ['111'],
            n_candidates_full: 3,
            truth_reachable_full: true,
            per_method: { rules_v1: { chosen_correct: false, unrounded_gap: 0.0400000001, unrounded_ambiguous: true } },
            verifier: 'v',
          },
        }),
      ],
    };
    const parsed = casesV(clone(doc), '$');
    expect(parsed.cases).toHaveLength(2);
    const badB = clone(doc) as unknown as { cases: { evidence: { b_id?: string }[] }[] };
    (badB.cases[0] as { evidence: { b_id?: string }[] }).evidence[0]!.b_id = '0123';
    expect(() => casesV(badB, '$')).toThrow(ValidationError);
    const mixed = clone(doc) as unknown as { cases: { evidence: Record<string, unknown>[] }[] };
    (mixed.cases[0] as { evidence: Record<string, unknown>[] }).evidence[2]!.b_id = '5';
    expect(() => casesV(mixed, '$')).toThrow(/no alternative/);
  });
});

describe('sandbox validator', () => {
  const p = fileURLToPath(new URL('../../fixtures/synthetic_sandbox.json', import.meta.url));
  it.skipIf(!existsSync(p))('accepts the generated fixture and rejects a tampered id', () => {
    const raw = JSON.parse(readFileSync(p, 'utf8')) as Record<string, unknown>;
    const d = sandboxV(raw, '$');
    expect(d.synthetic).toBe(true);
    expect(d.badge.length).toBeGreaterThan(0);
    expect(d.cases.length).toBeGreaterThan(0);
    const bad = clone(raw) as { records: { a: { id: string }[] } };
    bad.records.a[0]!.id = '0123abcd-0123-4567-89ab-0123456789ab';
    expect(() => sandboxV(bad, '$')).toThrow(ValidationError);
  });
});

describe('receipt validator', () => {
  it('rejects overlong strings and unknown actions', () => {
    const r = {
      receipt_version: '1.0',
      receipt_id: 'abcdefgh',
      kind: 'policy_scenario',
      created_at_utc: 'now',
      decision_question: 'q',
      snapshot: { snapshot_id: TEST_SNAPSHOT_ID, analytical_digest: 'c'.repeat(64), evaluation_code_commit: 'b'.repeat(40), feature_version: '0', lab_contract_version: '1.0' },
      population: { fold: 'test', grain: 'a_record', a_records: 1, labelled_a: 1 },
      method: { method_version: 'rules_v1', score_kind: 'uncalibrated_score', policy: { accept_min: 0.9, review_min: 0.5, ambiguity_gap: 0.1 }, policy_source: 'x' },
      selected_controls: { control_kind: 'native', review_floor: null, replay_policy: null, scenario_id: 'native:rules_v1' },
      user_constraints: { queue_budget: null, notes: '' },
      observations: [],
      assumptions: [],
      alternatives_considered: [],
      chosen_action: 'defer',
      rationale: '',
      limitations: [],
      outcome: { status: 'not_observed', measured_value: null },
    };
    expect(receiptV(clone(r), '$').chosen_action).toBe('defer');
    const long = clone(r);
    long.rationale = 'x'.repeat(4001);
    expect(() => receiptV(long, '$')).toThrow(/rationale/);
    const act = clone(r);
    act.chosen_action = 'ship_it';
    expect(() => receiptV(act, '$')).toThrow(/chosen_action/);
    const syn = clone(r);
    syn.selected_controls.scenario_id = 'synthetic:x';
    expect(receiptV(syn, '$').selected_controls.scenario_id).toBe('synthetic:x'); // shape-valid; refused later by importReceipt
  });
});
