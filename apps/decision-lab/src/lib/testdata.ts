/** Minimal, obviously invented contract objects for unit tests (not from any artifact). */
import type { LabCase, LabManifest, LabSnapshot, SnapshotMethod } from './contracts';

const SHA = 'a'.repeat(64);
const COMMIT = 'b'.repeat(40);
export const TEST_SNAPSHOT_ID = '20260101T000000+0000@0123456789ab';

function metric(value: number | null, numerator: number | null, denominator: number | null, key: string) {
  return { value, numerator, denominator, source_key: key };
}

export function makeMethod(name: string, over: Partial<SnapshotMethod> = {}): SnapshotMethod {
  return {
    method_version: name,
    definition: `test ${name}`,
    score_kind: name === 'rules_v1' ? 'uncalibrated_score' : name === 'exact_v1' ? 'binary_score' : 'calibrated_probability',
    fitted_on: null,
    policy: { accept_min: 0.9, review_min: 0.5, ambiguity_gap: 0.1 },
    policy_source: `test/${name}#policy`,
    metrics: {
      precision: metric(0.5, 1, 2, `${name}.precision`),
      recall_labelled: metric(0.25, 1, 4, `${name}.recall_labelled`),
      recall_overall: metric(0.2, 1, 5, `${name}.recall_overall`),
      f1: metric(0.333333, null, null, `${name}.f1`),
      coverage: metric(0.3, 3, 10, `${name}.coverage`),
      pair_completeness_test: metric(0.8, 4, 5, `${name}.pc`),
      unverified_accepts_share: metric(0.333333, 1, 3, `${name}.ua`),
      precision_or_review: metric(null, 0, 0, `${name}.por`),
      recall_labelled_or_review: metric(0.5, 2, 4, `${name}.rlr`),
    },
    counts: {
      test_a: { value: 10, source_key: `${name}.test_a` },
      labelled_a: { value: 5, source_key: `${name}.labelled_a` },
      labelled_a_reachable: { value: 4, source_key: `${name}.reach` },
      accepted_labelled: { value: 2, source_key: `${name}.al` },
      correct_labelled: { value: 1, source_key: `${name}.cl` },
      accepted_all: { value: 3, source_key: `${name}.aa` },
      unverified_accepts: { value: 1, source_key: `${name}.ua` },
      review_queue: { value: 4, source_key: `${name}.rq` },
      decisions_moved_to_review: { value: 1, source_key: `${name}.dm` },
      tier_auto_accept: { value: 3, source_key: `${name}.ta` },
      tier_review: { value: 4, source_key: `${name}.tr` },
      tier_reject: { value: 3, source_key: `${name}.tj` },
    },
    calibration: {
      pair_level_ece: metric(null, null, null, `${name}.ece`),
      decision_level_ece: metric(null, null, null, `${name}.dece`),
      pair_level_brier: metric(null, null, null, `${name}.brier`),
      decision_level_brier: metric(null, null, null, `${name}.dbrier`),
      note: 'test',
    },
    review_floor: {
      accept_min: 0.9,
      status: 'supported_exact_at_native_accept',
      note: 'test',
      points: [
        { floor: 0.5, queue_floor: 3, queue_ambiguity: 1, queue_total: 4, queue_share_of_test_a: 0.4, recall_with_review: 0.5 },
        { floor: 0.7, queue_floor: 1, queue_ambiguity: 1, queue_total: 2, queue_share_of_test_a: 0.2, recall_with_review: 0.4 },
      ],
      floors_omitted_at_or_above_accept_min: [0.9, 0.95],
      source_key: `${name}.floor`,
    },
    legacy_threshold_sweep: {
      status: 'legacy_snapshot_calculation',
      note: 'test',
      review_min: 0.5,
      chosen_accept_threshold: 0.9,
      false_accept_cost_ratios: [1, 5],
      points: [
        { threshold: 0.9, accepts: 3, queue_floor: 3, queue_ambiguity: 1, review_queue: 4, precision_labelled: 0.5, expected_false_accepts: 1.5, total_cost: { '1': 5.5, '5': 11.5 } },
      ],
      source_key: `${name}.legacy`,
    },
    mapping_exhibit: { path: `test/${name}.csv`, sha256: SHA, rows: 7, note: 'test' },
    ...over,
  };
}

export function makeSnapshot(): LabSnapshot {
  return {
    lab_snapshot_version: '1.0',
    snapshot_id: TEST_SNAPSHOT_ID,
    evidence: {
      run_id: '20260101T000000+0000',
      evaluation_code_commit: COMMIT,
      feature_version: '0.0.0',
      manifest_sha256_at_evaluation: SHA,
      evaluation_generated_at_utc: '2026-01-01T00:00:00+00:00',
      artifact_version: '1.0',
      sensitivity_version: '1.0',
      lab_contract_version: '1.0',
    },
    population: { fold: 'test', grain: 'a_record', a_records: 10, labelled_a: 5, labelled_a_reachable: 4, source_keys: ['x'] },
    metric_definitions: {
      precision: { display_name: 'precision', definition: 'd', numerator: 'n', denominator: 'd', scope: 's', unit: 'ratio', kind: 'accuracy' },
    },
    methods: {
      exact_v1: makeMethod('exact_v1', { metrics: { ...makeMethod('exact_v1').metrics, f1: metric(0.2, null, null, 'exact.f1'), precision: metric(0.9, 9, 10, 'exact.p'), recall_labelled: metric(0.1, 1, 10, 'exact.r'), coverage: metric(0.1, 1, 10, 'exact.c') }, counts: { ...makeMethod('exact_v1').counts, review_queue: { value: 1, source_key: 'exact.rq' } } }),
      rules_v1: makeMethod('rules_v1', { metrics: { ...makeMethod('rules_v1').metrics, f1: metric(0.6, null, null, 'rules.f1'), precision: metric(0.7, 7, 10, 'rules.p'), recall_labelled: metric(0.5, 5, 10, 'rules.r'), coverage: metric(0.5, 5, 10, 'rules.c') } }),
      learned_v1: makeMethod('learned_v1', { metrics: { ...makeMethod('learned_v1').metrics, f1: metric(0.4, null, null, 'learned.f1'), precision: metric(0.95, 19, 20, 'learned.p'), recall_labelled: metric(0.3, 3, 10, 'learned.r'), coverage: metric(0.3, 3, 10, 'learned.c') }, counts: { ...makeMethod('learned_v1').counts, review_queue: { value: 2, source_key: 'learned.rq' } } }),
    },
    provenance: {
      eval_artifacts: { rules_v1: { path: 'x', sha256: SHA } },
      method_records: {},
      review_sensitivity: { path: 'x', sha256: SHA },
      split: { path: 'x', sha256: SHA },
      note: 'test',
    },
  };
}

export function makeManifest(): LabManifest {
  return {
    lab_manifest_version: '1.0',
    snapshot_id: TEST_SNAPSHOT_ID,
    analytical_digest: 'c'.repeat(64),
    evidence: makeSnapshot().evidence,
    sources: [{ path: 'artifacts/manifest.json', sha256: SHA, role: 'manifest' }],
    files: { 'snapshot.json': { sha256: SHA, bytes: 1, generated_from: 'committed_artifacts', recomputable_without_local_data: true, analytical: true } },
    capabilities: {
      evidence_comparison: { available: true, note: 'n' },
      supported_floor_control: { available: true, note: 'n' },
      case_explorer: { available: true, note: 'n' },
      decision_ledger: { available: true, note: 'n' },
      synthetic_sandbox: { available: true, note: 'n' },
      local_case_evidence: { available: false, note: 'local evidence did not run' },
      complete_replay: {
        rules_v1: { available: true, note: 'n', decision_value_kind: 'uncalibrated_score' },
        learned_v1: { available: false, note: 'learned replay unavailable', decision_value_kind: 'unavailable' },
      },
    },
    population: makeSnapshot().population,
    selection: { strategy_version: 't', total_cases: 1, counts_by_reason: { x: 1 }, criteria: [], limitations: ['curated, not representative'] },
    supported_operations: ['x'],
    build: { built_at_utc: '2026-01-02T00:00:00Z', builder_code_commit: 'd'.repeat(40), builder_version: '0' },
  };
}

export const TEST_A_ID = '0123abcd-0123-4567-89ab-0123456789ab';

export function makeCase(over: Partial<LabCase> = {}): LabCase {
  return {
    case_id: TEST_A_ID,
    a_id: TEST_A_ID,
    reason_codes: ['methods_disagree'],
    narrative: null,
    evidence: [
      {
        method_version: 'exact_v1',
        exported: true,
        b_id: '111',
        score: 1,
        probability: 1,
        tier: 'auto_accept',
        top2_gap: 1,
        gap_state: 'exported',
        block_keys: ['k_title'],
        ambiguity_demoted_derived: false,
        gap_at_rounded_boundary: false,
        run_id: 'r',
        decided_at_utc: 't',
        source: 's',
      },
      {
        method_version: 'rules_v1',
        exported: true,
        b_id: '222',
        score: 0.8,
        probability: 0.8,
        tier: 'review',
        top2_gap: 0.04,
        gap_state: 'exported',
        block_keys: [],
        ambiguity_demoted_derived: true,
        gap_at_rounded_boundary: false,
        run_id: 'r',
        decided_at_utc: 't',
        source: 's',
      },
      { method_version: 'learned_v1', exported: false, state: 'not_exported', reason: 'no_candidate', source: 's' },
    ],
    comparison: { methods_exported: 2, distinct_chosen_b_ids: 2, agreement_class: 'methods_disagree', note: 'n' },
    labels: { state: 'truth_unavailable' },
    ...over,
  };
}
