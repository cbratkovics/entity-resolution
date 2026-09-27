/**
 * Generate a MOCK lab export (manifest, snapshot, cases, replay bundles, synthetic sandbox) that
 * satisfies the lab contracts, for running the app and its e2e suite when artifacts/lab/ has not
 * been produced yet. Every number is invented from a seeded generator; nothing comes from the
 * real benchmark. The snapshot metrics are computed from the mock replay rows with the same
 * policy engine, so a replay at the native policy reconciles exactly, as it must for real data.
 *
 *   npx tsx scripts/mock-lab-data.ts <output-dir>
 *   LAB_DATA_DIR=<output-dir> npm run test:e2e
 */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import { casesV, manifestV, replayMetaV, sandboxV, snapshotV, type LabCase, type LabManifest, type LabSnapshot, type ReplayMeta, type SnapshotMethod, type EvidenceRow, type SyntheticSandbox } from '../src/lib/contracts';
import { serialiseReplayCsv } from '../src/lib/csv';
import { acceptSweep, decideValues, evaluate, floorSweep, legacyAcceptSweep, makePolicy, round6, typedRowsFromObjects, type Policy, type ReplayRow } from '../src/lib/policy';

const outDir = resolve(process.argv[2] ?? join(tmpdir(), 'erlab-mock-lab'));
mkdirSync(join(outDir, 'replay'), { recursive: true });

// ------------------------------------------------------------------ seeded generator
let seed = 20260926;
function rnd(): number {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}
function sha256(data: string | Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}
function hex(n: number): string {
  let s = '';
  for (let i = 0; i < n; i += 1) s += Math.floor(rnd() * 16).toString(16);
  return s;
}
function uuid(): string {
  return `${hex(8)}-${hex(4)}-${hex(4)}-${hex(4)}-${hex(12)}`;
}
function bId(): string {
  return String(1 + Math.floor(rnd() * 9_000_000));
}

const RUN_ID = '20260101T000000+0000';
const EVAL_COMMIT = sha256('mock-evaluation-code-commit').slice(0, 40);
const MANIFEST_SHA = sha256('mock-manifest-at-evaluation');
const SNAPSHOT_ID = `${RUN_ID}@${MANIFEST_SHA.slice(0, 12)}`;
const N = 3000;

const evidence = {
  run_id: RUN_ID,
  evaluation_code_commit: EVAL_COMMIT,
  feature_version: '0.0.0-mock',
  manifest_sha256_at_evaluation: MANIFEST_SHA,
  evaluation_generated_at_utc: '2026-01-01T00:00:00+00:00',
  artifact_version: '1.0',
  sensitivity_version: '1.0',
  lab_contract_version: '1.0' as const,
};

// ------------------------------------------------------------------ mock population per method
const NATIVE: Record<string, Policy> = {
  exact_v1: makePolicy(1, 0.5, 0.1),
  rules_v1: makePolicy(0.65, 0.0757, 0.1),
  learned_v1: makePolicy(0.95, 0.5, 0.1),
};
const SCORE_KIND = { exact_v1: 'binary_score', rules_v1: 'uncalibrated_score', learned_v1: 'calibrated_probability' } as const;

interface Pop {
  rows: ReplayRow[];
}

function makeRows(method: string): Pop {
  const rows: ReplayRow[] = [];
  for (let i = 0; i < N; i += 1) {
    const labelled = rnd() < 0.5;
    const k = rnd() < 0.24 ? 0 : rnd() < 0.3 ? 1 : 2 + Math.floor(rnd() * 6);
    let v1: number | null = null;
    let v2: number | null = null;
    if (k > 0) {
      if (method === 'exact_v1') {
        v1 = rnd() < 0.55 ? 1 : 0;
        v2 = k >= 2 ? (v1 === 1 && rnd() < 0.08 ? 1 : 0) : null;
      } else {
        const good = rnd() < 0.7;
        v1 = good ? 0.6 + 0.4 * rnd() : rnd() * 0.7;
        v2 = k >= 2 ? Math.min(v1, v1 * (0.3 + 0.7 * rnd()) + (rnd() < 0.15 ? 0 : 0)) : null;
        if (k >= 2 && rnd() < 0.1) v2 = v1 - 0.03 * rnd();
        v1 = round6(v1);
        v2 = v2 === null ? null : round6(Math.min(v1, v2));
      }
    }
    const reach = labelled ? rnd() < 0.96 : null;
    const top1 = labelled && v1 !== null ? (reach ? (v1 >= 0.6 ? rnd() < 0.97 : rnd() < 0.5) : false) : null;
    rows.push({ v1, v2, n_candidates: k, labelled, top1_correct: top1, truth_reachable: reach });
  }
  return { rows };
}

const pops: Record<string, Pop> = {
  exact_v1: makeRows('exact_v1'),
  rules_v1: makeRows('rules_v1'),
  learned_v1: makeRows('learned_v1'),
};

const FLOORS = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95];
const THRESHOLDS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1];
const RATIOS = [1, 5, 20];

function metric(value: number | null, numerator: number | null, denominator: number | null, key: string) {
  return { value, numerator, denominator, source_key: key };
}

function methodBlock(name: string): SnapshotMethod {
  const pol = NATIVE[name] as Policy;
  const rows = pops[name]?.rows as ReplayRow[];
  const m = evaluate(rows, pol);
  const key = (k: string) => `artifacts/eval_${name}.json#metrics.${k}`;
  const floorPts = floorSweep(rows, { accept_min: pol.accept_min, ambiguity_gap: pol.ambiguity_gap, floors: FLOORS });
  const legacy = legacyAcceptSweep(rows, { baseline: pol, thresholds: THRESHOLDS });
  const legacyPts = legacy.map((p) => {
    const corrected = acceptSweep(rows, { review_min: pol.review_min, ambiguity_gap: pol.ambiguity_gap, thresholds: [p.threshold] })[0];
    const precision = corrected ? corrected.precision_labelled : null;
    const efa = precision === null ? null : round6(p.accepts * (1 - precision));
    const total: Record<string, number | null> = {};
    for (const r of RATIOS) total[String(r)] = efa === null ? null : round6(p.review_queue + efa * r);
    return { ...p, precision_labelled: precision, expected_false_accepts: efa, total_cost: total };
  });
  return {
    method_version: name,
    definition: `MOCK ${name}: invented rows from a seeded generator (not the benchmark)`,
    score_kind: SCORE_KIND[name as keyof typeof SCORE_KIND],
    fitted_on: name === 'exact_v1' ? null : { fold: 'fit', note: 'mock' },
    policy: { accept_min: pol.accept_min, review_min: pol.review_min, ambiguity_gap: pol.ambiguity_gap },
    policy_source: `artifacts/methods/${name}.json#parameters.thresholds`,
    metrics: {
      precision: metric(m.at_auto_accept.precision, m.at_auto_accept.correct, m.at_auto_accept.accepted, key('at_auto_accept.precision')),
      recall_labelled: metric(m.at_auto_accept.recall_labelled, m.at_auto_accept.correct, m.labelled_a_reachable, key('at_auto_accept.recall_labelled')),
      recall_overall: metric(m.recall_overall, m.at_auto_accept.correct, m.labelled_a, key('recall_overall')),
      f1: metric(m.at_auto_accept.f1, null, null, key('at_auto_accept.f1')),
      coverage: metric(m.coverage, m.accepted_all, m.test_a, key('coverage')),
      pair_completeness_test: metric(m.pair_completeness_test, m.labelled_a_reachable, m.labelled_a, key('pair_completeness_test')),
      unverified_accepts_share: metric(m.unverified_accepts.share_of_accepts, m.unverified_accepts.count, m.accepted_all, key('unverified_accepts.share_of_accepts')),
      precision_or_review: metric(m.at_auto_accept_or_review.precision, m.at_auto_accept_or_review.correct, m.at_auto_accept_or_review.accepted, key('at_auto_accept_or_review.precision')),
      recall_labelled_or_review: metric(m.at_auto_accept_or_review.recall_labelled, m.at_auto_accept_or_review.correct, m.labelled_a_reachable, key('at_auto_accept_or_review.recall_labelled')),
    },
    counts: {
      test_a: { value: m.test_a, source_key: key('test_a') },
      labelled_a: { value: m.labelled_a, source_key: key('labelled_a') },
      labelled_a_reachable: { value: m.labelled_a_reachable, source_key: key('labelled_a_reachable') },
      accepted_labelled: { value: m.at_auto_accept.accepted, source_key: key('at_auto_accept.accepted') },
      correct_labelled: { value: m.at_auto_accept.correct, source_key: key('at_auto_accept.correct') },
      accepted_all: { value: m.accepted_all, source_key: key('accepted_all') },
      unverified_accepts: { value: m.unverified_accepts.count, source_key: key('unverified_accepts.count') },
      review_queue: { value: m.ambiguity_rule.review_queue, source_key: key('ambiguity_rule.review_queue') },
      decisions_moved_to_review: { value: m.ambiguity_rule.decisions_moved_to_review, source_key: key('ambiguity_rule.decisions_moved_to_review') },
      tier_auto_accept: { value: m.tier_counts.auto_accept, source_key: key('tier_counts.auto_accept') },
      tier_review: { value: m.tier_counts.review, source_key: key('tier_counts.review') },
      tier_reject: { value: m.tier_counts.reject, source_key: key('tier_counts.reject') },
    },
    calibration: {
      pair_level_ece: { value: null, numerator: null, denominator: null, source_key: key('calibration.pair_level.ece'), unavailable_reason: 'mock data: not computed' },
      decision_level_ece: { value: null, numerator: null, denominator: null, source_key: key('calibration.decision_level.ece'), unavailable_reason: 'mock data: not computed' },
      pair_level_brier: { value: null, numerator: null, denominator: null, source_key: key('calibration.pair_level.brier'), unavailable_reason: 'mock data: not computed' },
      decision_level_brier: { value: null, numerator: null, denominator: null, source_key: key('calibration.decision_level.brier'), unavailable_reason: 'mock data: not computed' },
      note: 'MOCK: calibration is not computed for invented rows.',
    },
    review_floor: {
      accept_min: pol.accept_min,
      status: 'supported_exact_at_native_accept',
      note: 'Each point is a full replay with review_min = floor at the recorded accept_min and ambiguity_gap (mock rows).',
      points: floorPts,
      floors_omitted_at_or_above_accept_min: FLOORS.filter((f) => f >= pol.accept_min),
      source_key: `artifacts/review_sensitivity.json#methods.${name}.review_floor_sweep.points`,
    },
    legacy_threshold_sweep: {
      status: 'legacy_snapshot_calculation',
      note: 'Legacy calculation: the demotion flag is computed once at the recorded policy and reused at every threshold; not a faithful replay of an arbitrary policy.',
      review_min: pol.review_min,
      chosen_accept_threshold: pol.accept_min,
      false_accept_cost_ratios: RATIOS,
      points: legacyPts,
      source_key: `artifacts/review_sensitivity.json#methods.${name}.points`,
    },
    mapping_exhibit: { path: `artifacts/mapping/${name}.test.csv`, sha256: sha256(`mock-mapping-${name}`), rows: m.accepted_all + m.ambiguity_rule.review_queue, note: 'MOCK exhibit reference' },
  };
}

const snapshot: LabSnapshot = {
  lab_snapshot_version: '1.0',
  snapshot_id: SNAPSHOT_ID,
  evidence,
  population: {
    fold: 'test',
    grain: 'a_record',
    a_records: N,
    labelled_a: (pops.rules_v1 as Pop).rows.filter((r) => r.labelled).length,
    labelled_a_reachable: (pops.rules_v1 as Pop).rows.filter((r) => r.labelled && r.truth_reachable).length,
    source_keys: ['artifacts/eval_rules_v1.json#metrics.test_a', 'artifacts/eval_rules_v1.json#metrics.labelled_a', 'artifacts/eval_rules_v1.json#metrics.labelled_a_reachable'],
  },
  metric_definitions: {
    precision: { display_name: 'labelled precision', definition: 'Among labelled A records the method accepted, the share whose accepted B is in the truth set.', numerator: 'correct labelled accepts', denominator: 'labelled auto-accepted A records', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'accuracy' },
    recall_labelled: { display_name: 'reachable-labelled recall', definition: 'Correct accepts over labelled A records whose truth survived blocking.', numerator: 'correct labelled accepts', denominator: 'labelled A records whose truth survived blocking', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'accuracy' },
    recall_overall: { display_name: 'overall-labelled recall', definition: 'Correct accepts over all labelled A records (blocking loss included).', numerator: 'correct labelled accepts', denominator: 'all labelled A records', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'accuracy' },
    f1: { display_name: 'F1', definition: 'Harmonic mean of the rounded precision and reachable-labelled recall.', numerator: '2 * precision * recall', denominator: 'precision + recall', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'accuracy' },
    coverage: { display_name: 'coverage', definition: 'Auto-accepted A records over all test-fold A records, labelled or not. A volume measure.', numerator: 'auto-accepted A records', denominator: 'all test-fold A records', scope: 'all test-fold A records', unit: 'ratio', kind: 'volume' },
    pair_completeness_test: { display_name: 'pair completeness (test)', definition: 'labelled_a_reachable over labelled_a.', numerator: 'labelled A records whose truth survived blocking', denominator: 'labelled A records', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'volume' },
    unverified_accepts_share: { display_name: 'unverified accepts share', definition: 'Auto-accepts on unlabelled A records over all auto-accepts.', numerator: 'unlabelled auto-accepts', denominator: 'all auto-accepts', scope: 'all test-fold A records', unit: 'share', kind: 'volume' },
    precision_or_review: { display_name: 'precision with review (upper bound)', definition: 'Precision if every review were resolved correctly.', numerator: 'correct accepts + queued reachable', denominator: 'labelled accepts + labelled queued', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'upper_bound' },
    recall_labelled_or_review: { display_name: 'recall with review (upper bound)', definition: 'Recall if every queued reachable record were resolved correctly.', numerator: 'correct accepts + queued reachable', denominator: 'labelled A records whose truth survived blocking', scope: 'labelled test-fold A records', unit: 'ratio', kind: 'upper_bound' },
  },
  methods: { exact_v1: methodBlock('exact_v1'), rules_v1: methodBlock('rules_v1'), learned_v1: methodBlock('learned_v1') },
  provenance: {
    eval_artifacts: Object.fromEntries(['exact_v1', 'rules_v1', 'learned_v1'].map((m) => [m, { path: `artifacts/eval_${m}.json`, sha256: sha256(`mock-eval-${m}`), code_commit: EVAL_COMMIT, generated_at_utc: evidence.evaluation_generated_at_utc }])),
    method_records: Object.fromEntries(['exact_v1', 'rules_v1', 'learned_v1'].map((m) => [m, { path: `artifacts/methods/${m}.json`, sha256: sha256(`mock-method-${m}`) }])),
    review_sensitivity: { path: 'artifacts/review_sensitivity.json', sha256: sha256('mock-sensitivity') },
    split: { path: 'artifacts/split.json', sha256: sha256('mock-split') },
    note: 'MOCK DATA: every value is invented by scripts/mock-lab-data.ts; nothing here is from the benchmark.',
  },
};

// ------------------------------------------------------------------ cases
const REASONS = ['methods_disagree', 'ambiguity_boundary', 'single_candidate', 'unverified_accept', 'narrative_exhibit', 'none_exported'];

function evidenceRow(method: string, v1: number | null, v2: number | null, exported: boolean, reason: 'reject_or_no_candidate' | 'rejected' | 'no_candidate', chosen: string): EvidenceRow {
  if (!exported || v1 === null) {
    return { method_version: method, exported: false, state: 'not_exported', reason, source: `artifacts/mapping/${method}.test.csv` };
  }
  const pol = NATIVE[method] as Policy;
  const d = decideValues(v1, v2, pol);
  const tier = d.tier === 'reject' ? 'review' : d.tier;
  const gap = v2 === null ? null : round6(v1 - v2);
  return {
    method_version: method,
    exported: true,
    b_id: chosen,
    score: v1,
    probability: v1,
    tier,
    top2_gap: gap,
    gap_state: v2 === null ? 'single_candidate' : 'exported',
    block_keys: ['k_title_artist', 'k_title_year'].slice(0, 1 + Math.floor(rnd() * 2)),
    ambiguity_demoted_derived: gap === null ? null : tier === 'review' && v1 >= pol.accept_min && gap < pol.ambiguity_gap,
    gap_at_rounded_boundary: gap !== null && gap === pol.ambiguity_gap,
    run_id: RUN_ID,
    decided_at_utc: evidence.evaluation_generated_at_utc,
    source: `artifacts/mapping/${method}.test.csv`,
  };
}

const cases: LabCase[] = [];
for (let i = 0; i < 14; i += 1) {
  const a = uuid();
  const bMain = bId();
  const bAlt = bId();
  const kind = i % 7;
  const rows: EvidenceRow[] = [];
  let reasons: string[];
  let labels: LabCase['labels'];
  switch (kind) {
    case 0: // methods disagree
      rows.push(evidenceRow('exact_v1', 1, 0, true, 'rejected', bMain));
      rows.push(evidenceRow('rules_v1', 0.91, 0.62, true, 'rejected', bAlt));
      rows.push(evidenceRow('learned_v1', 0.97, 0.2, true, 'rejected', bMain));
      reasons = ['methods_disagree'];
      break;
    case 1: // ambiguity boundary (rules gap exactly 0.1 after rounding)
      rows.push(evidenceRow('exact_v1', null, null, false, 'reject_or_no_candidate', bMain));
      rows.push(evidenceRow('rules_v1', 0.8, 0.7, true, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', 0.96, 0.9, true, 'rejected', bMain));
      reasons = ['ambiguity_boundary'];
      break;
    case 2: // single candidate
      rows.push(evidenceRow('exact_v1', 1, null, true, 'rejected', bMain));
      rows.push(evidenceRow('rules_v1', 0.7, null, true, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', 0.99, null, true, 'rejected', bMain));
      reasons = ['single_candidate'];
      break;
    case 3: // unverified accept
      rows.push(evidenceRow('exact_v1', null, null, false, 'no_candidate', bMain));
      rows.push(evidenceRow('rules_v1', 0.88, 0.1, true, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', 0.955, 0.01, true, 'rejected', bMain));
      reasons = ['unverified_accept'];
      break;
    case 4: // narrative
      rows.push(evidenceRow('exact_v1', 1, 0, true, 'rejected', bMain));
      rows.push(evidenceRow('rules_v1', 0.95, 0.3, true, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', 0.5, 0.4, true, 'rejected', bAlt));
      reasons = ['narrative_exhibit', 'methods_disagree'];
      break;
    case 5: // none exported
      rows.push(evidenceRow('exact_v1', null, null, false, 'reject_or_no_candidate', bMain));
      rows.push(evidenceRow('rules_v1', null, null, false, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', null, null, false, 'no_candidate', bMain));
      reasons = ['none_exported'];
      break;
    default: // review by value
      rows.push(evidenceRow('exact_v1', null, null, false, 'rejected', bMain));
      rows.push(evidenceRow('rules_v1', 0.4, 0.05, true, 'rejected', bMain));
      rows.push(evidenceRow('learned_v1', 0.7, 0.1, true, 'rejected', bMain));
      reasons = ['ambiguity_boundary', 'single_candidate'].slice(0, 1);
      break;
  }
  const exported = rows.filter((r) => r.exported);
  const distinct = new Set(exported.map((r) => (r.exported ? r.b_id : ''))).size;
  const agreement = exported.length === 0 ? 'none_exported' : exported.length === 1 ? 'single_method_exported' : distinct === 1 ? 'all_exported_agree' : 'methods_disagree';
  if (i % 3 === 0) {
    labels = { state: 'truth_unavailable', note: 'MOCK: the local verification stage did not run for this case.' };
  } else {
    const labelled = i % 3 === 1;
    const per: Record<string, { chosen_correct: boolean | null; unrounded_gap: number | null; unrounded_ambiguous: boolean | null }> = {};
    for (const r of rows) {
      per[r.method_version] = r.exported
        ? { chosen_correct: labelled ? r.b_id === bMain : null, unrounded_gap: r.top2_gap === null ? null : r.top2_gap + 1e-9, unrounded_ambiguous: r.top2_gap === null ? null : r.top2_gap + 1e-9 < (NATIVE[r.method_version] as Policy).ambiguity_gap }
        : { chosen_correct: null, unrounded_gap: null, unrounded_ambiguous: null };
    }
    labels = {
      state: 'verified_local',
      labelled,
      truth_b_ids: labelled ? [bMain] : [],
      n_candidates_full: 1 + Math.floor(rnd() * 6),
      truth_reachable_full: labelled ? true : null,
      truth_visible_in_exported_choices: labelled ? exported.some((r) => r.exported && r.b_id === bMain) : null,
      per_method: per,
      verifier: 'mock-verifier 0.0',
    };
  }
  cases.push({
    case_id: a,
    a_id: a,
    reason_codes: reasons,
    narrative: kind === 4 ? { kind: 'narrative', source: 'docs/FINDINGS.md', note: 'MOCK narrative: this case illustrates a method disagreement discussed in the findings.' } : null,
    evidence: rows,
    comparison: {
      methods_exported: exported.length,
      distinct_chosen_b_ids: distinct,
      agreement_class: agreement,
      note: 'The chosen B ids of different methods are not a ranked candidate list.',
    },
    labels,
  });
}
const countsByReason: Record<string, number> = {};
for (const c of cases) for (const r of c.reason_codes) countsByReason[r] = (countsByReason[r] ?? 0) + 1;
const criteria = REASONS.map((r) => ({ reason_code: r, description: `MOCK criterion ${r}`, cap: 5, source: 'committed_exhibits' as const, deterministic_order: 'a_id ascending', selected: countsByReason[r] ?? 0, available: (countsByReason[r] ?? 0) + 3 }));

const casesDoc = {
  lab_cases_version: '1.0' as const,
  snapshot_id: SNAPSHOT_ID,
  policies: Object.fromEntries(
    Object.entries(NATIVE).map(([m, p]) => [m, { accept_min: p.accept_min, review_min: p.review_min, ambiguity_gap: p.ambiguity_gap, score_kind: SCORE_KIND[m as keyof typeof SCORE_KIND], source_key: `artifacts/methods/${m}.json#parameters.thresholds` }]),
  ),
  selection: {
    strategy_version: 'mock-0.0',
    total_cases: cases.length,
    counts_by_reason: countsByReason,
    criteria,
    limitations: ['MOCK DATA: cases are invented; not a representative sample.', 'Label metadata is invented where present.'],
    local_evidence: { available: true, note: 'MOCK: local evidence values are invented.', verifier: 'mock-verifier 0.0' },
  },
  cases,
};

// ------------------------------------------------------------------ replay bundles
function replayFiles(name: string): { meta: ReplayMeta; csv: Buffer } {
  const pol = NATIVE[name] as Policy;
  const rows = (pops[name] as Pop).rows;
  const typed = typedRowsFromObjects(rows);
  const csv = gzipSync(Buffer.from(serialiseReplayCsv(typed), 'utf8'));
  const m = evaluate(rows, pol);
  const method = snapshot.methods[name] as SnapshotMethod;
  const checks = [
    { metric: 'at_auto_accept.precision', replay: m.at_auto_accept.precision, artifact: method.metrics.precision?.value ?? null },
    { metric: 'at_auto_accept.recall_labelled', replay: m.at_auto_accept.recall_labelled, artifact: method.metrics.recall_labelled?.value ?? null },
    { metric: 'at_auto_accept.f1', replay: m.at_auto_accept.f1, artifact: method.metrics.f1?.value ?? null },
    { metric: 'coverage', replay: m.coverage, artifact: method.metrics.coverage?.value ?? null },
    { metric: 'ambiguity_rule.review_queue', replay: m.ambiguity_rule.review_queue, artifact: method.counts.review_queue?.value ?? null },
    { metric: 'unverified_accepts.count', replay: m.unverified_accepts.count, artifact: method.counts.unverified_accepts?.value ?? null },
  ].map((c) => ({ ...c, equal: Object.is(c.replay, c.artifact) }));
  const legacy = legacyAcceptSweep(rows, { baseline: pol, thresholds: THRESHOLDS });
  const corrected = acceptSweep(rows, { review_min: pol.review_min, ambiguity_gap: pol.ambiguity_gap, thresholds: THRESHOLDS });
  const points = legacy.map((l, i) => {
    const c = corrected[i];
    return {
      threshold: l.threshold,
      legacy_accepts: l.accepts,
      corrected_accepts: c ? c.accepts : l.accepts,
      legacy_review_queue: l.review_queue,
      corrected_review_queue: c ? c.review_queue : l.review_queue,
      legacy_matches_artifact: true,
    };
  });
  const differing = points.filter((p) => p.legacy_accepts !== p.corrected_accepts);
  const meta: ReplayMeta = {
    lab_replay_version: '1.0',
    snapshot_id: SNAPSHOT_ID,
    method_version: name,
    decision_value_kind: SCORE_KIND[name as keyof typeof SCORE_KIND],
    file: `replay/replay_${name}.test.csv.gz`,
    columns: ['v1', 'v2', 'n_candidates', 'labelled', 'top1_correct', 'truth_reachable'],
    rows: rows.length,
    population: snapshot.population,
    completeness: {
      a_records_expected: N,
      a_records_in_file: rows.length,
      with_candidates: rows.filter((r) => r.n_candidates > 0).length,
      without_candidates: rows.filter((r) => r.n_candidates === 0).length,
      labelled: rows.filter((r) => r.labelled).length,
      labelled_reachable: rows.filter((r) => r.labelled && r.truth_reachable).length,
      conserved: rows.length === N,
    },
    inputs: [
      { path: 'data/lab/mock_candidates.parquet', sha256: sha256(`mock-candidates-${name}`), role: 'local_candidates' },
      { path: 'artifacts/split.json', sha256: sha256('mock-split'), role: 'split', manifest_key: 'split' },
    ],
    native_policy: { accept_min: pol.accept_min, review_min: pol.review_min, ambiguity_gap: pol.ambiguity_gap },
    reconciliation: { eval_artifact: `artifacts/eval_${name}.json`, eval_artifact_sha256: sha256(`mock-eval-${name}`), all_equal: checks.every((c) => c.equal), checks },
    floor_sweep_reconciliation: { all_equal: true, points_compared: method.review_floor.points.length },
    legacy_sweep_divergence: {
      note: 'The legacy sweep reused the baseline demotion flag at every threshold; the corrected sweep replays the policy. Differences are expected below the recorded accept threshold.',
      thresholds_differing: differing.length,
      max_accepts_difference: differing.reduce((mx, p) => Math.max(mx, Math.abs(p.legacy_accepts - p.corrected_accepts)), 0),
      points,
    },
    a_id_order_sha256: sha256(`mock-a-id-order-${name}`),
    note: `MOCK replay bundle for ${name}: invented rows; the snapshot metrics were computed from these rows so the native replay reconciles.`,
  };
  return { meta, csv };
}

// ------------------------------------------------------------------ synthetic sandbox (mock fixture)
const VOCAB = ['glimmer', 'tundra', 'quartz', 'saffron', 'meadow', 'ember', 'lantern', 'harbor', 'violet', 'cinder'];
function title(i: number, j: number): string {
  return `${VOCAB[i % VOCAB.length]} ${VOCAB[(i * 3 + j) % VOCAB.length]}`;
}
const sandbox: SyntheticSandbox = {
  synthetic: true,
  sandbox_version: '1.0',
  badge: 'SYNTHETIC SANDBOX: invented records and fixture scores; nothing here is from the benchmark',
  generated_by: 'apps/decision-lab/scripts/mock-lab-data.ts (MOCK fixture until the Python generator writes fixtures/synthetic_sandbox.json)',
  vocabulary: VOCAB,
  records: {
    a: [
      { id: 'SYN-A-001', title: title(1, 0), artist_credit: 'The Glimmer Ensemble', year: 1991 },
      { id: 'SYN-A-002', title: title(2, 0), artist_credit: 'Tundra Quartet', year: 2004 },
      { id: 'SYN-A-003', title: title(3, 0), artist_credit: 'Saffron & Meadow', year: null },
      { id: 'SYN-A-004', title: title(4, 0), artist_credit: 'Ember Lantern', year: 1978 },
      { id: 'SYN-A-005', title: title(5, 0), artist_credit: 'Harbor Violet', year: 2015 },
      { id: 'SYN-A-006', title: title(6, 0), artist_credit: 'Cinder Glimmer', year: 1999 },
    ],
    b: [
      { id: 'SYN-B-001', title: title(1, 0), artist_credit: 'The Glimmer Ensemble', year: 1991 },
      { id: 'SYN-B-002', title: title(1, 1), artist_credit: 'The Glimmer Ensemble', year: 1992 },
      { id: 'SYN-B-003', title: title(2, 0), artist_credit: 'Tundra Quartet', year: 2004 },
      { id: 'SYN-B-004', title: title(2, 0), artist_credit: 'Tundra Quartet (live)', year: 2004 },
      { id: 'SYN-B-005', title: title(3, 0), artist_credit: 'Saffron & Meadow', year: 2001 },
      { id: 'SYN-B-006', title: title(4, 1), artist_credit: 'Ember Lantern', year: 1978 },
      { id: 'SYN-B-007', title: title(4, 2), artist_credit: 'Ember Lantern', year: 1979 },
      { id: 'SYN-B-008', title: title(6, 0), artist_credit: 'Cinder Glimmer', year: 1999 },
    ],
  },
  candidates: [
    // regression: top scores 0.80 and 0.76 (gap 0.04)
    { a_id: 'SYN-A-001', b_id: 'SYN-B-001', values: { synthetic_exact_like: 1, synthetic_rules_like: 0.8 } },
    { a_id: 'SYN-A-001', b_id: 'SYN-B-002', values: { synthetic_exact_like: 0, synthetic_rules_like: 0.76 } },
    // exact tie: lexical order chooses SYN-B-003
    { a_id: 'SYN-A-002', b_id: 'SYN-B-003', values: { synthetic_exact_like: 1, synthetic_rules_like: 0.97 } },
    { a_id: 'SYN-A-002', b_id: 'SYN-B-004', values: { synthetic_exact_like: 1, synthetic_rules_like: 0.97 } },
    // single candidate: null gap
    { a_id: 'SYN-A-003', b_id: 'SYN-B-005', values: { synthetic_exact_like: 1, synthetic_rules_like: 0.96 } },
    // clear winner
    { a_id: 'SYN-A-004', b_id: 'SYN-B-006', values: { synthetic_exact_like: 0, synthetic_rules_like: 0.99 } },
    { a_id: 'SYN-A-004', b_id: 'SYN-B-007', values: { synthetic_exact_like: 0, synthetic_rules_like: 0.2 } },
    // SYN-A-005 has no candidate
    // boundary: exactly at accept_min of the strict preset
    { a_id: 'SYN-A-006', b_id: 'SYN-B-008', values: { synthetic_exact_like: 1, synthetic_rules_like: 0.95 } },
  ],
  labels: { 'SYN-A-001': ['SYN-B-001'], 'SYN-A-002': ['SYN-B-004'], 'SYN-A-003': ['SYN-B-005'], 'SYN-A-004': ['SYN-B-006'], 'SYN-A-006': ['SYN-B-008'] },
  score_kinds: {
    synthetic_exact_like: 'a binary fixture score (1 when the invented title, artist credit and year agree, else 0); not a model output',
    synthetic_rules_like: 'a hand-set fixture score in [0, 1] chosen to exercise ties, gaps and boundaries; not a model output and not a probability',
  },
  policies: [
    { preset: 'strict', policy: { accept_min: 0.95, review_min: 0.5, ambiguity_gap: 0.1 } },
    { preset: 'loose', policy: { accept_min: 0.75, review_min: 0.5, ambiguity_gap: 0.1 } },
  ],
  cases: [
    {
      case_id: 'SYN-CASE-regression_ambiguity_flag_reuse',
      a_id: 'SYN-A-001',
      purpose: 'Regression: values 0.80 and 0.76 (gap 0.04). Under strict the record is review by value; under loose it must still be review because the gap is below 0.10, and it is demoted.',
      expected: {
        strict: { synthetic_rules_like: { tier: 'review', ambiguous: true, demoted: false }, synthetic_exact_like: { tier: 'auto_accept', ambiguous: false } },
        loose: { synthetic_rules_like: { tier: 'review', ambiguous: true, demoted: true }, synthetic_exact_like: { tier: 'auto_accept' } },
      },
    },
    {
      case_id: 'SYN-CASE-lexical_tie',
      a_id: 'SYN-A-002',
      purpose: 'A tie on value: the lexically smallest B id is chosen and the gap is zero, so the decision is ambiguous.',
      expected: { strict: { synthetic_rules_like: { tier: 'review', chosen: 'SYN-B-003', ambiguous: true }, synthetic_exact_like: { tier: 'review', chosen: 'SYN-B-003' } } },
    },
    {
      case_id: 'SYN-CASE-single_candidate',
      a_id: 'SYN-A-003',
      purpose: 'A single candidate has a null gap and is never ambiguous.',
      expected: { strict: { synthetic_rules_like: { tier: 'auto_accept', gap: null } } },
    },
    {
      case_id: 'SYN-CASE-no_candidate',
      a_id: 'SYN-A-005',
      purpose: 'An A record with no candidate is reject with reason no_candidate and stays in the population.',
      expected: { strict: { synthetic_rules_like: { tier: 'reject', reason: 'no_candidate' }, synthetic_exact_like: { tier: 'reject', reason: 'no_candidate' } } },
    },
    {
      case_id: 'SYN-CASE-accept_boundary',
      a_id: 'SYN-A-006',
      purpose: 'A value exactly at accept_min is accepted (inclusive lower bound).',
      expected: { strict: { synthetic_rules_like: { tier: 'auto_accept' } }, loose: { synthetic_rules_like: { tier: 'auto_accept' } } },
    },
  ],
  downstream_fixture: {
    note: 'Fact rows keyed by B joined to a mapping that lists one B twice: the join inflates the row count above the conserved count.',
    fact_rows: [
      { b_id: 'SYN-B-001', units: 10 },
      { b_id: 'SYN-B-003', units: 7 },
      { b_id: 'SYN-B-005', units: 3 },
    ],
    mapping_with_duplicate: [
      { a_id: 'SYN-A-001', b_id: 'SYN-B-001' },
      { a_id: 'SYN-A-002', b_id: 'SYN-B-003' },
      { a_id: 'SYN-A-006', b_id: 'SYN-B-003' },
      { a_id: 'SYN-A-003', b_id: 'SYN-B-005' },
    ],
    conserved_row_count: 3,
  },
};

// ------------------------------------------------------------------ write files and manifest
function writeJson(rel: string, value: unknown): { sha256: string; bytes: number } {
  const text = JSON.stringify(value, null, 1) + '\n';
  writeFileSync(join(outDir, rel), text);
  return { sha256: sha256(text), bytes: Buffer.byteLength(text) };
}

snapshotV(JSON.parse(JSON.stringify(snapshot)), 'snapshot');
casesV(JSON.parse(JSON.stringify(casesDoc)), 'cases');
sandboxV(JSON.parse(JSON.stringify(sandbox)), 'sandbox');

const files: LabManifest['files'] = {};
const snap = writeJson('snapshot.json', snapshot);
files['snapshot.json'] = { ...snap, generated_from: 'committed_artifacts', recomputable_without_local_data: true, analytical: true, schema: 'lab_snapshot.schema.json' };
const cs = writeJson('cases.json', casesDoc);
files['cases.json'] = { ...cs, rows: cases.length, generated_from: 'committed_artifacts_and_local_data', recomputable_without_local_data: false, analytical: true, schema: 'lab_cases.schema.json' };
for (const name of ['exact_v1', 'rules_v1']) {
  const { meta, csv } = replayFiles(name);
  replayMetaV(JSON.parse(JSON.stringify(meta)), 'replay');
  writeFileSync(join(outDir, 'replay', `replay_${name}.test.csv.gz`), csv);
  files[`replay/replay_${name}.test.csv.gz`] = { sha256: sha256(csv), bytes: csv.length, rows: meta.rows, generated_from: 'committed_artifacts_and_local_data', recomputable_without_local_data: false, analytical: true, schema: 'lab_replay_meta.schema.json' };
  const mj = writeJson(`replay/replay_${name}.json`, meta);
  files[`replay/replay_${name}.json`] = { ...mj, generated_from: 'committed_artifacts_and_local_data', recomputable_without_local_data: false, analytical: true, schema: 'lab_replay_meta.schema.json' };
}
const sb = writeJson('synthetic_sandbox.json', sandbox);
files['synthetic_sandbox.json'] = { ...sb, generated_from: 'synthetic_generator', recomputable_without_local_data: true, analytical: false, schema: 'lab_synthetic_sandbox.schema.json' };

const digestPairs = Object.entries(files)
  .filter(([, f]) => f.analytical)
  .map(([name, f]) => [name, f.sha256] as const)
  .sort((a, b) => (a[0] < b[0] ? -1 : 1));
const analyticalDigest = sha256(JSON.stringify(digestPairs));

const manifest: LabManifest = {
  lab_manifest_version: '1.0',
  snapshot_id: SNAPSHOT_ID,
  analytical_digest: analyticalDigest,
  evidence,
  sources: [
    { path: 'artifacts/manifest.json', sha256: MANIFEST_SHA, role: 'manifest' },
    { path: 'artifacts/eval_exact_v1.json', sha256: sha256('mock-eval-exact_v1'), role: 'eval_artifact' },
    { path: 'artifacts/eval_rules_v1.json', sha256: sha256('mock-eval-rules_v1'), role: 'eval_artifact' },
    { path: 'artifacts/eval_learned_v1.json', sha256: sha256('mock-eval-learned_v1'), role: 'eval_artifact' },
    { path: 'artifacts/review_sensitivity.json', sha256: sha256('mock-sensitivity'), role: 'review_sensitivity' },
    { path: 'artifacts/split.json', sha256: sha256('mock-split'), role: 'split' },
    { path: 'docs/FINDINGS.md', sha256: sha256('mock-findings'), role: 'findings_narrative' },
    { path: 'data/lab/mock_candidates.parquet', sha256: sha256('mock-candidates'), role: 'local_candidates', local_only: true },
  ],
  files,
  capabilities: {
    evidence_comparison: { available: true, note: 'MOCK: aggregate comparison from invented rows.' },
    supported_floor_control: { available: true, note: 'MOCK: floors replayed from invented rows at the recorded accept_min.' },
    case_explorer: { available: true, note: 'MOCK: invented cases.' },
    decision_ledger: { available: true, note: 'Local, append-only, browser storage only.' },
    synthetic_sandbox: { available: true, note: 'MOCK sandbox fixture until fixtures/synthetic_sandbox.json is generated.' },
    local_case_evidence: { available: true, note: 'MOCK: invented label metadata.' },
    complete_replay: {
      exact_v1: { available: true, note: 'MOCK bundle.', decision_value_kind: 'binary_score', file: 'replay/replay_exact_v1.test.csv.gz', meta_file: 'replay/replay_exact_v1.json', reconciled_to_eval_artifact: true, population_conserved: true },
      rules_v1: { available: true, note: 'MOCK bundle.', decision_value_kind: 'uncalibrated_score', file: 'replay/replay_rules_v1.test.csv.gz', meta_file: 'replay/replay_rules_v1.json', reconciled_to_eval_artifact: true, population_conserved: true },
      learned_v1: { available: false, note: 'Complete replay for learned_v1 is unavailable: the calibrated pair probabilities of the full candidate set are not exported (local-only fitted objects); only the recorded evaluation is shown.', decision_value_kind: 'unavailable' },
    },
  },
  population: snapshot.population,
  selection: { strategy_version: casesDoc.selection.strategy_version, total_cases: cases.length, counts_by_reason: countsByReason, criteria, limitations: casesDoc.selection.limitations },
  supported_operations: ['evidence_comparison', 'supported_floor_control', 'case_explorer', 'decision_ledger', 'synthetic_sandbox', 'complete_replay:exact_v1', 'complete_replay:rules_v1'],
  build: { built_at_utc: new Date().toISOString(), builder_code_commit: 'mock', builder_version: 'mock-lab-data 0.0' },
};
manifestV(JSON.parse(JSON.stringify(manifest)), 'manifest');
writeJson('manifest.json', manifest);
console.log(`mock-lab-data: wrote a MOCK lab export to ${outDir}`);
console.log(`  snapshot_id ${SNAPSHOT_ID}\n  analytical_digest ${analyticalDigest}`);
console.log('  every value is invented; use only for running the app and its tests without artifacts/lab/.');
