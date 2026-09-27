import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  acceptSweep,
  checkReplayRow,
  decideRow,
  evaluate,
  floorSweep,
  legacyAcceptSweep,
  makePolicy,
  policyFromObject,
  PolicyError,
  rankCandidates,
  round6,
  rowAt,
  typedRowsFromObjects,
  type ReplayRow,
} from './policy';

const fixturesPath = fileURLToPath(new URL('../../fixtures/policy_fixtures.json', import.meta.url));
const fixtures = JSON.parse(readFileSync(fixturesPath, 'utf8')) as Fixtures;

interface PolicyJson {
  accept_min: number | string;
  review_min: number | string;
  ambiguity_gap: number | string;
}
interface FixtureCase {
  id: string;
  description: string;
  policy: PolicyJson;
  rows: ReplayRow[];
  expected_decisions: unknown[];
  expected_metrics: unknown;
  baseline_policy?: PolicyJson;
  expected_baseline_decisions?: unknown[];
  expected_legacy_sweep?: { threshold: number }[];
  expected_corrected_sweep?: { threshold: number }[];
  floors?: number[];
  floor_accept_min?: number;
  expected_floor_sweep?: unknown[];
}
interface Fixtures {
  fixtures_version: string;
  cases: FixtureCase[];
  invalid_policies: { id: string; policy: PolicyJson; error: boolean }[];
  rank_cases: { id: string; candidates: [string, number][]; expected_order: string[] }[];
}

/** JSON strings "NaN"/"Infinity" stand for the non-finite doubles (see fixtures note). */
function decodeNumber(v: number | string): number | string {
  if (v === 'NaN') return NaN;
  if (v === 'Infinity') return Infinity;
  if (v === '-Infinity') return -Infinity;
  return v;
}

/** Deep equality with Object.is number semantics (distinguishes NaN, -0 and null vs 0). */
function deepIs(a: unknown, b: unknown, path = '$'): string | null {
  if (typeof a === 'number' || typeof b === 'number') {
    return Object.is(a, b) ? null : `${path}: ${String(a)} !== ${String(b)}`;
  }
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') {
    return Object.is(a, b) ? null : `${path}: ${String(a)} !== ${String(b)}`;
  }
  if (Array.isArray(a) !== Array.isArray(b)) return `${path}: array mismatch`;
  const ka = Object.keys(a as object).sort();
  const kb = Object.keys(b as object).sort();
  if (ka.join(',') !== kb.join(',')) return `${path}: keys ${ka.join(',')} !== ${kb.join(',')}`;
  for (const k of ka) {
    const r = deepIs((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k], `${path}.${k}`);
    if (r) return r;
  }
  return null;
}

function expectSame(actual: unknown, expected: unknown): void {
  const diff = deepIs(actual, expected);
  if (diff) {
    throw new Error(diff + '\nactual: ' + JSON.stringify(actual) + '\nexpected: ' + JSON.stringify(expected));
  }
  expect(diff).toBeNull();
}

describe('policy fixtures (shared oracle)', () => {
  it('loads the fixture file', () => {
    expect(fixtures.fixtures_version).toBe('1.0');
    expect(fixtures.cases.length).toBeGreaterThan(0);
  });

  for (const c of fixtures.cases) {
    describe(c.id, () => {
      const policy = makePolicy(c.policy.accept_min, c.policy.review_min, c.policy.ambiguity_gap);
      const rows = c.rows.map(checkReplayRow);

      it('decides every row like the oracle', () => {
        expectSame(
          rows.map((r) => decideRow(r, policy)),
          c.expected_decisions,
        );
      });

      it('evaluates like the oracle (object rows)', () => {
        expectSame(evaluate(rows, policy), c.expected_metrics);
      });

      it('evaluates like the oracle (typed-array rows)', () => {
        expectSame(evaluate(typedRowsFromObjects(rows), policy), c.expected_metrics);
      });

      if (c.baseline_policy) {
        const base = policyFromObject(c.baseline_policy as { accept_min: number; review_min: number; ambiguity_gap: number });
        it('baseline decisions', () => {
          expectSame(
            rows.map((r) => decideRow(r, base)),
            c.expected_baseline_decisions,
          );
        });
        it('legacy accept sweep', () => {
          const thresholds = (c.expected_legacy_sweep ?? []).map((p) => p.threshold);
          expectSame(legacyAcceptSweep(rows, { baseline: base, thresholds }), c.expected_legacy_sweep);
          expectSame(
            legacyAcceptSweep(typedRowsFromObjects(rows), { baseline: base, thresholds }),
            c.expected_legacy_sweep,
          );
        });
        it('corrected accept sweep', () => {
          const thresholds = (c.expected_corrected_sweep ?? []).map((p) => p.threshold);
          expectSame(
            acceptSweep(rows, { review_min: base.review_min, ambiguity_gap: base.ambiguity_gap, thresholds }),
            c.expected_corrected_sweep,
          );
        });
      }

      if (c.floors) {
        it('floor sweep', () => {
          expectSame(
            floorSweep(rows, {
              accept_min: c.floor_accept_min as number,
              ambiguity_gap: policy.ambiguity_gap,
              floors: c.floors as number[],
            }),
            c.expected_floor_sweep,
          );
          expectSame(
            floorSweep(typedRowsFromObjects(rows), {
              accept_min: c.floor_accept_min as number,
              ambiguity_gap: policy.ambiguity_gap,
              floors: c.floors as number[],
            }),
            c.expected_floor_sweep,
          );
        });
      }
    });
  }

  describe('invalid policies throw', () => {
    for (const p of fixtures.invalid_policies) {
      it(p.id, () => {
        expect(p.error).toBe(true);
        expect(() =>
          makePolicy(decodeNumber(p.policy.accept_min), decodeNumber(p.policy.review_min), decodeNumber(p.policy.ambiguity_gap)),
        ).toThrow(PolicyError);
      });
    }
    it('rejects booleans', () => {
      expect(() => makePolicy(true, 0.5, 0.1)).toThrow(PolicyError);
    });
  });

  describe('rank cases', () => {
    for (const r of fixtures.rank_cases) {
      it(r.id, () => {
        const order = rankCandidates(r.candidates).map(([b]) => b);
        expect(order).toEqual(r.expected_order);
      });
    }
    it('rejects non-finite values', () => {
      expect(() => rankCandidates([['1', NaN]])).toThrow();
      expect(() => rankCandidates([['', 1]])).toThrow();
    });
  });
});

describe('round6', () => {
  it('matches Python round-half-even on the exact tie 1/128', () => {
    expect(round6(1 / 128)).toBe(0.007812);
    expect((1 / 128).toFixed(6)).toBe('0.007813');
  });
  it('rounds the other tie neighbour up when the sixth decimal is odd', () => {
    expect(round6(3 / 128)).toBe(0.023438); // 0.0234375 -> 0.023438 (8 is even)
    expect(round6(5 / 128)).toBe(0.039062); // 0.0390625 -> 0.039062
  });
  it('treats decimal near-ties by their exact binary value', () => {
    // 5e-7 is slightly below 0.0000005 as a double, so it rounds to 0.
    expect(round6(5e-7)).toBe(0);
    expect(round6(2 / 3)).toBe(0.666667);
    expect(round6(0.1 + 0.2)).toBe(0.3);
  });
  it('passes through non-finite and integers', () => {
    expect(round6(NaN)).toBeNaN();
    expect(round6(1)).toBe(1);
    expect(round6(0)).toBe(0);
  });
});

describe('typed rows', () => {
  it('round-trips object rows through typed arrays', () => {
    const rows: ReplayRow[] = [
      { v1: 0.9, v2: 0.1, n_candidates: 2, labelled: true, top1_correct: true, truth_reachable: true },
      { v1: 0.9, v2: null, n_candidates: 1, labelled: false, top1_correct: null, truth_reachable: null },
      { v1: null, v2: null, n_candidates: 0, labelled: true, top1_correct: null, truth_reachable: false },
    ];
    const t = typedRowsFromObjects(rows);
    expect(t.length).toBe(3);
    for (let i = 0; i < rows.length; i += 1) {
      expect(rowAt(t, i)).toEqual(rows[i]);
    }
  });
  it('evaluate over ~100k typed rows completes in one pass quickly', () => {
    const n = 100_000;
    const rows: ReplayRow[] = [];
    let seed = 42;
    const rnd = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };
    for (let i = 0; i < n; i += 1) {
      const k = i % 7 === 0 ? 0 : i % 5 === 0 ? 1 : 2 + Math.floor(rnd() * 5);
      const a = rnd();
      const b = rnd() * a;
      const labelled = i % 2 === 0;
      rows.push({
        v1: k === 0 ? null : a,
        v2: k >= 2 ? b : null,
        n_candidates: k,
        labelled,
        top1_correct: labelled && k > 0 ? rnd() > 0.2 : null,
        truth_reachable: labelled ? rnd() > 0.05 : null,
      });
    }
    const policy = makePolicy(0.9, 0.5, 0.1);
    const typed = typedRowsFromObjects(rows);
    const t0 = performance.now();
    const a = evaluate(typed, policy);
    const elapsed = performance.now() - t0;
    const b = evaluate(rows, policy);
    expect(deepIs(a, b)).toBeNull();
    expect(a.tier_counts.auto_accept + a.tier_counts.review + a.tier_counts.reject).toBe(n);
    expect(elapsed).toBeLessThan(2000);
  });
});
