/**
 * The TypeScript mirror of `entity_resolution/decision_lab/policy.py`, the one pure policy
 * specification of the lab. Every function here reproduces the Python oracle bit for bit;
 * `fixtures/policy_fixtures.json` (rendered by the Python side) is the shared test.
 *
 * Semantics preserved from the baseline `decide()`:
 * - the chosen candidate is the one with the highest decision value, ties broken by the
 *   lexically smallest B id (plain code-unit string order);
 * - the top-two gap is `v1 - v2`; a single candidate has a null gap;
 * - `auto_accept` iff `v1 >= accept_min`; `review` iff `review_min <= v1 < accept_min`;
 *   `reject` below (inclusive lower bounds);
 * - the ambiguity override applies to non-reject decisions only, with a strict `gap < ambiguity_gap`;
 * - `demoted` is the ambiguity condition and `v1 >= accept_min`; `ambiguous` is tracked separately;
 * - an A record with no candidate is `reject` with reason `no_candidate` and stays in the population.
 *
 * Metrics follow the evaluator exactly, including its rounding (ratios to six decimals with
 * Python's round-half-even on exact ties, F1 from the rounded precision and recall, tier shares
 * unrounded).
 */

export const TIER_AUTO_ACCEPT = 'auto_accept';
export const TIER_REVIEW = 'review';
export const TIER_REJECT = 'reject';
export const TIERS = [TIER_AUTO_ACCEPT, TIER_REVIEW, TIER_REJECT] as const;
export type Tier = (typeof TIERS)[number];

export const REASON_NO_CANDIDATE = 'no_candidate';
export const REASON_ACCEPT = 'value_at_or_above_accept_min';
export const REASON_REVIEW = 'value_at_or_above_review_min';
export const REASON_REJECT = 'value_below_review_min';
export const REASON_AMBIGUOUS = 'ambiguity_gap_below_threshold';
export type Reason =
  | typeof REASON_NO_CANDIDATE
  | typeof REASON_ACCEPT
  | typeof REASON_REVIEW
  | typeof REASON_REJECT
  | typeof REASON_AMBIGUOUS;

export class PolicyError extends Error {
  override name = 'PolicyError';
}

export interface Policy {
  readonly accept_min: number;
  readonly review_min: number;
  readonly ambiguity_gap: number;
}

/** Validate and freeze a policy exactly as the Python `Policy.__post_init__` does. */
export function makePolicy(accept_min: unknown, review_min: unknown, ambiguity_gap: unknown): Policy {
  const named: [string, unknown][] = [
    ['accept_min', accept_min],
    ['review_min', review_min],
    ['ambiguity_gap', ambiguity_gap],
  ];
  for (const [name, v] of named) {
    if (typeof v !== 'number') {
      throw new PolicyError(`${name} must be a number, got ${String(v)}`);
    }
    if (!Number.isFinite(v)) {
      throw new PolicyError(`${name} must be finite, got ${String(v)}`);
    }
  }
  const a = accept_min as number;
  const r = review_min as number;
  const g = ambiguity_gap as number;
  if (!(0 <= r && r <= a && a <= 1)) {
    throw new PolicyError(
      `policy must satisfy 0 <= review_min <= accept_min <= 1, got review_min=${r}, accept_min=${a}`,
    );
  }
  if (!(0 <= g && g <= 1)) {
    throw new PolicyError(`ambiguity_gap must be in [0, 1], got ${g}`);
  }
  return Object.freeze({ accept_min: a, review_min: r, ambiguity_gap: g });
}

export function policyFromObject(o: { accept_min: unknown; review_min: unknown; ambiguity_gap: unknown }): Policy {
  return makePolicy(o.accept_min, o.review_min, o.ambiguity_gap);
}

export function policyAsDict(p: Policy): { accept_min: number; review_min: number; ambiguity_gap: number } {
  return { accept_min: p.accept_min, review_min: p.review_min, ambiguity_gap: p.ambiguity_gap };
}

/** One A record of the population (see the Python `ReplayRow`). */
export interface ReplayRow {
  readonly v1: number | null;
  readonly v2: number | null;
  readonly n_candidates: number;
  readonly labelled: boolean;
  readonly top1_correct: boolean | null;
  readonly truth_reachable: boolean | null;
}

/** Validate a replay row exactly as the Python dataclass does; throws on violation. */
export function checkReplayRow(row: ReplayRow): ReplayRow {
  if (!Number.isInteger(row.n_candidates) || row.n_candidates < 0) {
    throw new Error('n_candidates must be >= 0');
  }
  if ((row.v1 === null) !== (row.n_candidates === 0)) {
    throw new Error('v1 is null exactly when there is no candidate');
  }
  if (row.v2 !== null && row.n_candidates < 2) {
    throw new Error('v2 requires at least two candidates');
  }
  if (row.v2 === null && row.n_candidates >= 2) {
    throw new Error('v2 must be present when there are two or more candidates');
  }
  for (const v of [row.v1, row.v2]) {
    if (v !== null && !Number.isFinite(v)) {
      throw new Error('decision values must be finite');
    }
  }
  if (row.v1 !== null && row.v2 !== null && row.v2 > row.v1) {
    throw new Error('v2 must not exceed v1 (candidates are ranked by decision value)');
  }
  if (!row.labelled && (row.top1_correct !== null || row.truth_reachable !== null)) {
    throw new Error('unlabelled rows carry no correctness or reachability');
  }
  if (row.labelled && row.truth_reachable === null) {
    throw new Error('labelled rows must state truth reachability');
  }
  if (row.labelled && row.v1 !== null && row.top1_correct === null) {
    throw new Error('labelled rows with a candidate must state top1_correct');
  }
  if (row.v1 === null && row.top1_correct !== null) {
    throw new Error('no candidate means no top1_correct');
  }
  return row;
}

export interface Decision {
  readonly tier: Tier;
  readonly reason: Reason;
  readonly gap: number | null;
  readonly ambiguous: boolean;
  readonly demoted: boolean;
}

export type Candidate = readonly [b_id: string, value: number];

/** Order `(b_id, value)` pairs the way `decide` does: value descending, B id ascending (code-unit order). */
export function rankCandidates(candidates: readonly Candidate[]): Candidate[] {
  for (const [b, v] of candidates) {
    if (typeof b !== 'string' || b.length === 0) {
      throw new Error('b_id must be a non-empty string');
    }
    if (typeof v !== 'number' || !Number.isFinite(v)) {
      throw new Error(`non-finite decision value for ${b}`);
    }
  }
  const out = candidates.slice();
  out.sort((x, y) => {
    if (x[1] !== y[1]) {
      return y[1] - x[1];
    }
    return x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0;
  });
  return out;
}

/** Build a replay row from a full candidate list; returns the chosen B id and the row. */
export function rowFromCandidates(
  candidates: readonly Candidate[],
  opts: { labelled: boolean; truth_b_ids?: ReadonlySet<string>; truth_reachable?: boolean | null },
): { chosen: string | null; row: ReplayRow } {
  const ranked = rankCandidates(candidates);
  const truth = opts.truth_b_ids ?? new Set<string>();
  const first = ranked[0];
  const second = ranked[1];
  const chosen = first ? first[0] : null;
  if (!opts.labelled) {
    return {
      chosen,
      row: checkReplayRow({
        v1: first ? first[1] : null,
        v2: second ? second[1] : null,
        n_candidates: ranked.length,
        labelled: false,
        top1_correct: null,
        truth_reachable: null,
      }),
    };
  }
  const reachable =
    opts.truth_reachable !== undefined && opts.truth_reachable !== null
      ? opts.truth_reachable
      : ranked.some(([b]) => truth.has(b));
  return {
    chosen,
    row: checkReplayRow({
      v1: first ? first[1] : null,
      v2: second ? second[1] : null,
      n_candidates: ranked.length,
      labelled: true,
      top1_correct: first ? truth.has(first[0]) : null,
      truth_reachable: Boolean(reachable),
    }),
  };
}

export function decideRow(row: ReplayRow, policy: Policy): Decision {
  if (row.v1 === null) {
    return { tier: TIER_REJECT, reason: REASON_NO_CANDIDATE, gap: null, ambiguous: false, demoted: false };
  }
  return decideValues(row.v1, row.v2, policy);
}

/** The decision for a record with candidate values `v1` (best) and `v2` (second best or null). */
export function decideValues(v1: number, v2: number | null, policy: Policy): Decision {
  let base: Tier;
  let reason: Reason;
  if (v1 >= policy.accept_min) {
    base = TIER_AUTO_ACCEPT;
    reason = REASON_ACCEPT;
  } else if (v1 >= policy.review_min) {
    base = TIER_REVIEW;
    reason = REASON_REVIEW;
  } else {
    base = TIER_REJECT;
    reason = REASON_REJECT;
  }
  const gap = v2 === null ? null : v1 - v2;
  const ambiguous = base !== TIER_REJECT && gap !== null && gap < policy.ambiguity_gap;
  const tier: Tier = ambiguous ? TIER_REVIEW : base;
  const demoted = ambiguous && v1 >= policy.accept_min;
  return { tier, reason: ambiguous ? REASON_AMBIGUOUS : reason, gap, ambiguous, demoted };
}

/**
 * Python's `round(x, 6)`: the nearest multiple of 1e-6 by the exact decimal value of the double,
 * exact ties resolved half to even. `Number.prototype.toFixed` also works on the exact decimal
 * expansion but resolves exact ties upward, so ties (where `x * 2e6` is an exact odd integer,
 * e.g. 1/128) are detected on the exact expansion and rounded to the even neighbour.
 */
export function round6(x: number): number {
  if (!Number.isFinite(x)) {
    return x;
  }
  const neg = x < 0;
  const ax = Math.abs(x);
  if (ax >= 1e15) {
    return x;
  }
  // Exact decimal expansion: a double in [2^-47, 1e15) has at most 100 fractional digits.
  const exact = ax.toFixed(100);
  const dot = exact.indexOf('.');
  const frac = exact.slice(dot + 1);
  const tail = frac.slice(6);
  let rounded: number;
  if (tail[0] === '5' && /^5(0*)$/.test(tail)) {
    // exact tie: round half to even on the sixth decimal
    const head = exact.slice(0, dot + 1 + 6);
    const sixth = Number(head[head.length - 1]);
    rounded = sixth % 2 === 0 ? Number(head) : bumpLastDigit(head);
  } else {
    rounded = Number(ax.toFixed(6));
  }
  return neg ? -rounded : rounded;
}

function bumpLastDigit(fixed6: string): number {
  // fixed6 is "<int>.<6 digits>"; add one unit in the last place using decimal string arithmetic.
  const digits = fixed6.replace('.', '').split('').map(Number);
  let i = digits.length - 1;
  while (i >= 0) {
    const d = digits[i] ?? 0;
    if (d < 9) {
      digits[i] = d + 1;
      break;
    }
    digits[i] = 0;
    i -= 1;
  }
  const s = (i < 0 ? '1' : '') + digits.join('');
  const intPart = s.slice(0, s.length - 6);
  const fracPart = s.slice(s.length - 6);
  return Number(`${intPart}.${fracPart}`);
}

function rate(n: number, d: number): number | null {
  return d ? round6(n / d) : null;
}

function f1(p: number | null, r: number | null, accepted: number, base: number): number | null {
  if (p && r && p + r) {
    return round6((2 * p * r) / (p + r));
  }
  return accepted || base ? 0.0 : null;
}

export interface TierBlock {
  accepted: number;
  correct: number;
  precision: number | null;
  recall_labelled: number | null;
  f1: number | null;
}

export interface EvaluateResult {
  policy: { accept_min: number; review_min: number; ambiguity_gap: number };
  test_a: number;
  labelled_a: number;
  labelled_a_reachable: number;
  no_candidate_a: number;
  pair_completeness_test: number | null;
  at_auto_accept: TierBlock;
  at_auto_accept_or_review: TierBlock;
  recall_overall: number | null;
  coverage: number | null;
  accepted_all: number;
  unverified_accepts: { count: number; share_of_accepts: number | null };
  tier_counts: Record<Tier, number>;
  tier_shares: Record<Tier, number | null>;
  ambiguity_rule: { decisions_moved_to_review: number; ambiguous_non_reject: number; review_queue: number };
  denominators: {
    precision: string;
    recall_labelled: string;
    recall_overall: string;
    coverage: string;
    share_of_accepts: string;
  };
}

/**
 * A compact, typed-array population: `v1`/`v2` use NaN for null, `flags` carry
 * bit 0 labelled, bit 1 top1_correct (bit 2 set when top1_correct is non-null),
 * bit 3 truth_reachable (bit 4 set when truth_reachable is non-null).
 */
export interface TypedRows {
  readonly length: number;
  readonly v1: Float64Array;
  readonly v2: Float64Array;
  readonly n_candidates: Uint32Array;
  readonly flags: Uint8Array;
}

export const FLAG_LABELLED = 1;
export const FLAG_TOP1_CORRECT = 2;
export const FLAG_TOP1_PRESENT = 4;
export const FLAG_REACHABLE = 8;
export const FLAG_REACHABLE_PRESENT = 16;

export function typedRowsFromObjects(rows: readonly ReplayRow[]): TypedRows {
  const n = rows.length;
  const v1 = new Float64Array(n);
  const v2 = new Float64Array(n);
  const nc = new Uint32Array(n);
  const flags = new Uint8Array(n);
  for (let i = 0; i < n; i += 1) {
    const r = rows[i] as ReplayRow;
    v1[i] = r.v1 === null ? NaN : r.v1;
    v2[i] = r.v2 === null ? NaN : r.v2;
    nc[i] = r.n_candidates;
    let f = 0;
    if (r.labelled) f |= FLAG_LABELLED;
    if (r.top1_correct !== null) f |= FLAG_TOP1_PRESENT | (r.top1_correct ? FLAG_TOP1_CORRECT : 0);
    if (r.truth_reachable !== null) f |= FLAG_REACHABLE_PRESENT | (r.truth_reachable ? FLAG_REACHABLE : 0);
    flags[i] = f;
  }
  return { length: n, v1, v2, n_candidates: nc, flags };
}

export function rowAt(t: TypedRows, i: number): ReplayRow {
  const f = t.flags[i] ?? 0;
  const a = t.v1[i] ?? NaN;
  const b = t.v2[i] ?? NaN;
  return {
    v1: Number.isNaN(a) ? null : a,
    v2: Number.isNaN(b) ? null : b,
    n_candidates: t.n_candidates[i] ?? 0,
    labelled: (f & FLAG_LABELLED) !== 0,
    top1_correct: f & FLAG_TOP1_PRESENT ? (f & FLAG_TOP1_CORRECT) !== 0 : null,
    truth_reachable: f & FLAG_REACHABLE_PRESENT ? (f & FLAG_REACHABLE) !== 0 : null,
  };
}

type Population = readonly ReplayRow[] | TypedRows;

function isTyped(p: Population): p is TypedRows {
  return !Array.isArray(p);
}

interface Tally {
  n_test_a: number;
  tiers: Record<Tier, number>;
  n_lab: number;
  n_reach: number;
  acc_lab: number;
  acc_lab_correct: number;
  rev_lab: number;
  rev_lab_reachable: number;
  n_accept_all: number;
  n_review_all: number;
  n_unverified: number;
  n_demoted: number;
  n_ambiguous: number;
  n_no_candidate: number;
}

function tally(rows: Population, policy: Policy): Tally {
  const t: Tally = {
    n_test_a: rows.length,
    tiers: { auto_accept: 0, review: 0, reject: 0 },
    n_lab: 0,
    n_reach: 0,
    acc_lab: 0,
    acc_lab_correct: 0,
    rev_lab: 0,
    rev_lab_reachable: 0,
    n_accept_all: 0,
    n_review_all: 0,
    n_unverified: 0,
    n_demoted: 0,
    n_ambiguous: 0,
    n_no_candidate: 0,
  };
  const n = rows.length;
  const typed = isTyped(rows);
  for (let i = 0; i < n; i += 1) {
    let v1: number | null;
    let v2: number | null;
    let labelled: boolean;
    let top1: boolean;
    let reach: boolean;
    if (typed) {
      const a = rows.v1[i] as number;
      const b = rows.v2[i] as number;
      const f = rows.flags[i] as number;
      v1 = Number.isNaN(a) ? null : a;
      v2 = Number.isNaN(b) ? null : b;
      labelled = (f & FLAG_LABELLED) !== 0;
      top1 = (f & FLAG_TOP1_CORRECT) !== 0;
      reach = (f & FLAG_REACHABLE) !== 0;
    } else {
      const r = rows[i] as ReplayRow;
      v1 = r.v1;
      v2 = r.v2;
      labelled = r.labelled;
      top1 = Boolean(r.top1_correct);
      reach = Boolean(r.truth_reachable);
    }
    let tier: Tier;
    let ambiguous = false;
    let demoted = false;
    if (v1 === null) {
      tier = TIER_REJECT;
      t.n_no_candidate += 1;
    } else {
      const d = decideValues(v1, v2, policy);
      tier = d.tier;
      ambiguous = d.ambiguous;
      demoted = d.demoted;
    }
    t.tiers[tier] += 1;
    if (ambiguous) t.n_ambiguous += 1;
    if (demoted) t.n_demoted += 1;
    if (tier === TIER_AUTO_ACCEPT) {
      t.n_accept_all += 1;
      if (!labelled) t.n_unverified += 1;
    } else if (tier === TIER_REVIEW) {
      t.n_review_all += 1;
    }
    if (labelled) {
      t.n_lab += 1;
      if (reach) t.n_reach += 1;
      if (tier === TIER_AUTO_ACCEPT) {
        t.acc_lab += 1;
        if (top1) t.acc_lab_correct += 1;
      } else if (tier === TIER_REVIEW) {
        t.rev_lab += 1;
        if (reach) t.rev_lab_reachable += 1;
      }
    }
  }
  return t;
}

/** Every metric of `eval_<method>.json#metrics` the replay rows can support, at A-record grain. */
export function evaluate(rows: Population, policy: Policy): EvaluateResult {
  const t = tally(rows, policy);
  const p = rate(t.acc_lab_correct, t.acc_lab);
  const r = rate(t.acc_lab_correct, t.n_reach);
  const pOr = rate(t.acc_lab_correct + t.rev_lab_reachable, t.acc_lab + t.rev_lab);
  const rOr = rate(t.acc_lab_correct + t.rev_lab_reachable, t.n_reach);
  const n = t.n_test_a;
  return {
    policy: policyAsDict(policy),
    test_a: n,
    labelled_a: t.n_lab,
    labelled_a_reachable: t.n_reach,
    no_candidate_a: t.n_no_candidate,
    pair_completeness_test: rate(t.n_reach, t.n_lab),
    at_auto_accept: {
      accepted: t.acc_lab,
      correct: t.acc_lab_correct,
      precision: p,
      recall_labelled: r,
      f1: f1(p, r, t.acc_lab, t.n_reach),
    },
    at_auto_accept_or_review: {
      accepted: t.acc_lab + t.rev_lab,
      correct: t.acc_lab_correct + t.rev_lab_reachable,
      precision: pOr,
      recall_labelled: rOr,
      f1: f1(pOr, rOr, t.acc_lab + t.rev_lab, t.n_reach),
    },
    recall_overall: rate(t.acc_lab_correct, t.n_lab),
    coverage: rate(t.n_accept_all, n),
    accepted_all: t.n_accept_all,
    unverified_accepts: { count: t.n_unverified, share_of_accepts: rate(t.n_unverified, t.n_accept_all) },
    tier_counts: { auto_accept: t.tiers.auto_accept, review: t.tiers.review, reject: t.tiers.reject },
    tier_shares: {
      auto_accept: n ? t.tiers.auto_accept / n : null,
      review: n ? t.tiers.review / n : null,
      reject: n ? t.tiers.reject / n : null,
    },
    ambiguity_rule: {
      decisions_moved_to_review: t.n_demoted,
      ambiguous_non_reject: t.n_ambiguous,
      review_queue: t.n_review_all,
    },
    denominators: {
      precision: 'labelled auto-accepted A records',
      recall_labelled: 'labelled A records whose truth survived blocking',
      recall_overall: 'all labelled A records',
      coverage: 'all A records in the population',
      share_of_accepts: 'all auto-accepted A records',
    },
  };
}

export interface FloorPoint {
  floor: number;
  queue_floor: number;
  queue_ambiguity: number;
  queue_total: number;
  queue_share_of_test_a: number | null;
  recall_with_review: number | null;
}

/** The corrected review-floor sweep: every floor strictly below `accept_min` is a full replay. */
export function floorSweep(
  rows: Population,
  opts: { accept_min: number; ambiguity_gap: number; floors: readonly number[] },
): FloorPoint[] {
  const out: FloorPoint[] = [];
  for (const floor of opts.floors) {
    if (floor >= opts.accept_min) continue;
    const m = evaluate(rows, makePolicy(opts.accept_min, floor, opts.ambiguity_gap));
    out.push({
      floor,
      queue_floor: m.ambiguity_rule.review_queue - m.ambiguity_rule.decisions_moved_to_review,
      queue_ambiguity: m.ambiguity_rule.decisions_moved_to_review,
      queue_total: m.ambiguity_rule.review_queue,
      queue_share_of_test_a: rate(m.ambiguity_rule.review_queue, m.test_a),
      recall_with_review: rate(m.at_auto_accept_or_review.correct, m.labelled_a_reachable),
    });
  }
  return out;
}

export interface AcceptPoint {
  threshold: number;
  accepts: number;
  queue_floor: number;
  queue_ambiguity: number;
  review_queue: number;
  precision_labelled: number | null;
  labelled_accepts: number;
  labelled_false_accepts: number;
}

/** The corrected accept-threshold sweep: a full replay at every threshold. */
export function acceptSweep(
  rows: Population,
  opts: { review_min: number; ambiguity_gap: number; thresholds: readonly number[] },
): AcceptPoint[] {
  const out: AcceptPoint[] = [];
  for (const t of opts.thresholds) {
    if (t < opts.review_min) continue;
    const m = evaluate(rows, makePolicy(t, opts.review_min, opts.ambiguity_gap));
    out.push({
      threshold: t,
      accepts: m.accepted_all,
      queue_floor: m.ambiguity_rule.review_queue - m.ambiguity_rule.decisions_moved_to_review,
      queue_ambiguity: m.ambiguity_rule.decisions_moved_to_review,
      review_queue: m.ambiguity_rule.review_queue,
      precision_labelled: m.at_auto_accept.precision,
      labelled_accepts: m.at_auto_accept.accepted,
      labelled_false_accepts: m.at_auto_accept.accepted - m.at_auto_accept.correct,
    });
  }
  return out;
}

export interface LegacyPoint {
  threshold: number;
  accepts: number;
  queue_floor: number;
  queue_ambiguity: number;
  review_queue: number;
}

/** The legacy `review_cost.sweep` calculation restated over replay rows: the demotion flag is
 * computed once at `baseline` and reused at every threshold. Never a replay. */
export function legacyAcceptSweep(
  rows: Population,
  opts: { baseline: Policy; thresholds: readonly number[] },
): LegacyPoint[] {
  const out: LegacyPoint[] = [];
  const n = rows.length;
  const typed = isTyped(rows);
  for (const t of opts.thresholds) {
    let accepts = 0;
    let qFloor = 0;
    let qAmb = 0;
    for (let i = 0; i < n; i += 1) {
      let v1: number | null;
      let v2: number | null;
      if (typed) {
        const a = rows.v1[i] as number;
        const b = rows.v2[i] as number;
        v1 = Number.isNaN(a) ? null : a;
        v2 = Number.isNaN(b) ? null : b;
      } else {
        const r = rows[i] as ReplayRow;
        v1 = r.v1;
        v2 = r.v2;
      }
      if (v1 === null) continue;
      const flag = decideValues(v1, v2, opts.baseline).demoted;
      if (v1 >= t && !flag) accepts += 1;
      if (opts.baseline.review_min <= v1 && v1 < t) qFloor += 1;
      if (flag && v1 >= t) qAmb += 1;
    }
    out.push({ threshold: t, accepts, queue_floor: qFloor, queue_ambiguity: qAmb, review_queue: qFloor + qAmb });
  }
  return out;
}
