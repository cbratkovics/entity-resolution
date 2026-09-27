/**
 * TypeScript types and strict validators for the seven lab contracts in `artifacts/schemas/`:
 * lab_manifest, lab_snapshot, lab_cases, lab_replay_meta, lab_receipt, lab_review_events and
 * lab_synthetic_sandbox. The validators mirror the JSON Schemas (required keys, closed objects,
 * enums, id patterns); anything else is "malformed data".
 */
import { any, arr, bool, enumOf, int, lit, nil, nullable, num, obj, oneOf, record, str, ValidationError, type Validator } from './validate';

export const METHODS = ['exact_v1', 'rules_v1', 'learned_v1'] as const;
export type MethodVersion = (typeof METHODS)[number];
export const SCORE_KINDS = ['binary_score', 'uncalibrated_score', 'calibrated_probability'] as const;
export type ScoreKind = (typeof SCORE_KINDS)[number];

export const SHA256 = /^[0-9a-f]{64}$/;
export const COMMIT40 = /^[0-9a-f]{40}$/;
export const A_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const B_ID = /^[1-9][0-9]{0,11}$/;
export const SYN_A = /^SYN-A-[0-9]{3}$/;
export const SYN_B = /^SYN-B-[0-9]{3}$/;
export const SNAPSHOT_ID = /^[0-9]{8}T[0-9]{6}\+0000@[0-9a-f]{12}$/;
export const EVENT_ID = /^[A-Za-z0-9_-]{8,64}$/;
export const SCENARIO_ID = /^[a-z]+:[A-Za-z0-9_.:@-]{1,120}$/;
export const REASON_CODE = /^[a-z_]+$/;
export const BLOCK_KEY = /^k_[a-z0-9_]+$/;

// ---------------------------------------------------------------- shared $defs

const policyV = obj({ accept_min: num(), review_min: num(), ambiguity_gap: num() });
export type PolicyJson = ReturnType<typeof policyV>;

const boundedPolicyV = obj({
  accept_min: num({ min: 0, max: 1 }),
  review_min: num({ min: 0, max: 1 }),
  ambiguity_gap: num({ min: 0, max: 1 }),
});

const evidenceV = obj({
  run_id: str(),
  evaluation_code_commit: str({ pattern: COMMIT40 }),
  feature_version: str(),
  manifest_sha256_at_evaluation: str({ pattern: SHA256 }),
  evaluation_generated_at_utc: str(),
  artifact_version: str(),
  sensitivity_version: str(),
  lab_contract_version: lit('1.0'),
});
export type Evidence = ReturnType<typeof evidenceV>;

const populationV = obj({
  fold: lit('test'),
  grain: lit('a_record'),
  a_records: int({ min: 0 }),
  labelled_a: int({ min: 0 }),
  labelled_a_reachable: int({ min: 0 }),
  source_keys: arr(str()),
});
export type Population = ReturnType<typeof populationV>;

const capabilityV = obj({ available: bool, note: str() });
export type Capability = ReturnType<typeof capabilityV>;

const replayCapabilityV = obj(
  {
    available: bool,
    note: str(),
    decision_value_kind: enumOf(['binary_score', 'uncalibrated_score', 'calibrated_probability', 'unavailable'] as const),
    file: str(),
    meta_file: str(),
    reconciled_to_eval_artifact: bool,
    population_conserved: bool,
  },
  { optional: ['file', 'meta_file', 'reconciled_to_eval_artifact', 'population_conserved'] },
);
export type ReplayCapability = ReturnType<typeof replayCapabilityV>;

const criterionV = obj(
  {
    reason_code: str({ pattern: REASON_CODE }),
    description: str(),
    cap: int({ min: 0 }),
    source: enumOf(['committed_exhibits', 'findings_narrative', 'local_evidence'] as const),
    deterministic_order: str(),
    selected: int({ min: 0 }),
    available: int({ min: 0 }),
  },
  { optional: ['selected', 'available'] },
);
export type Criterion = ReturnType<typeof criterionV>;

// ---------------------------------------------------------------- lab_manifest

export const manifestV = obj({
  lab_manifest_version: lit('1.0'),
  snapshot_id: str({ pattern: SNAPSHOT_ID }),
  analytical_digest: str({ pattern: SHA256 }),
  evidence: evidenceV,
  sources: arr(
    obj(
      {
        path: str(),
        sha256: str({ pattern: SHA256 }),
        role: enumOf([
          'manifest', 'eval_artifact', 'method_record', 'review_sensitivity', 'split', 'blocking_report', 'truth_audit',
          'mapping_exhibit', 'findings_narrative', 'local_features', 'local_candidates', 'local_truth', 'local_sample_a',
        ] as const),
        local_only: bool,
      },
      { optional: ['local_only'] },
    ),
    { min: 1 },
  ),
  files: record(
    obj(
      {
        sha256: str({ pattern: SHA256 }),
        bytes: int({ min: 0 }),
        rows: int({ min: 0 }),
        generated_from: enumOf(['committed_artifacts', 'committed_artifacts_and_local_data', 'synthetic_generator'] as const),
        recomputable_without_local_data: bool,
        analytical: bool,
        schema: str(),
      },
      { optional: ['rows', 'schema'] },
    ),
    { minProperties: 1 },
  ),
  capabilities: obj({
    evidence_comparison: capabilityV,
    supported_floor_control: capabilityV,
    case_explorer: capabilityV,
    decision_ledger: capabilityV,
    synthetic_sandbox: capabilityV,
    local_case_evidence: capabilityV,
    complete_replay: record(replayCapabilityV, { keys: METHODS }),
  }),
  population: populationV,
  selection: obj({
    strategy_version: str(),
    total_cases: int({ min: 0 }),
    counts_by_reason: record(int({ min: 0 })),
    criteria: arr(criterionV),
    limitations: arr(str()),
  }),
  supported_operations: arr(str()),
  build: obj({ built_at_utc: str(), builder_code_commit: str(), builder_version: str() }),
});
export type LabManifest = ReturnType<typeof manifestV>;

// ---------------------------------------------------------------- lab_snapshot

const filerefV = obj(
  { path: str(), sha256: str({ pattern: SHA256 }), code_commit: str(), generated_at_utc: str() },
  { optional: ['code_commit', 'generated_at_utc'] },
);
export type FileRef = ReturnType<typeof filerefV>;

const metricV = obj(
  {
    value: nullable(num()),
    numerator: nullable(int()),
    denominator: nullable(int()),
    source_key: str(),
    unavailable_reason: nullable(str()),
  },
  { optional: ['unavailable_reason'] },
);
export type Metric = ReturnType<typeof metricV>;

const countV = obj({ value: nullable(int()), source_key: str() });
export type Count = ReturnType<typeof countV>;

const floorPointV = obj({
  floor: num(),
  queue_floor: int(),
  queue_ambiguity: int(),
  queue_total: int(),
  queue_share_of_test_a: nullable(num()),
  recall_with_review: nullable(num()),
});
export type SnapshotFloorPoint = ReturnType<typeof floorPointV>;

const legacyPointV = obj({
  threshold: num(),
  accepts: int(),
  queue_floor: int(),
  queue_ambiguity: int(),
  review_queue: int(),
  precision_labelled: nullable(num()),
  expected_false_accepts: nullable(num()),
  total_cost: record(nullable(num())),
});
export type LegacyPoint = ReturnType<typeof legacyPointV>;

const REQUIRED_METRICS = [
  'precision', 'recall_labelled', 'recall_overall', 'f1', 'coverage', 'pair_completeness_test',
  'unverified_accepts_share', 'precision_or_review', 'recall_labelled_or_review',
] as const;
const REQUIRED_COUNTS = [
  'test_a', 'labelled_a', 'labelled_a_reachable', 'accepted_labelled', 'correct_labelled', 'accepted_all',
  'unverified_accepts', 'review_queue', 'decisions_moved_to_review', 'tier_auto_accept', 'tier_review', 'tier_reject',
] as const;

function requiredRecord<T>(value: Validator<T>, required: readonly string[]): Validator<Record<string, T>> {
  const base = record(value);
  return (x, path) => {
    const out = base(x, path);
    for (const k of required) {
      if (!(k in out)) throw new ValidationError(`${path}.${k}`, 'required key missing');
    }
    return out;
  };
}

const methodV = obj({
  method_version: str(),
  definition: str(),
  score_kind: enumOf(SCORE_KINDS),
  fitted_on: nullable(record(any)),
  policy: policyV,
  policy_source: str(),
  metrics: requiredRecord(metricV, REQUIRED_METRICS),
  counts: requiredRecord(countV, REQUIRED_COUNTS),
  calibration: obj({
    pair_level_ece: metricV,
    decision_level_ece: metricV,
    pair_level_brier: metricV,
    decision_level_brier: metricV,
    note: str(),
  }),
  review_floor: obj({
    accept_min: num(),
    status: enumOf(['supported_exact_at_native_accept'] as const),
    note: str(),
    points: arr(floorPointV),
    floors_omitted_at_or_above_accept_min: arr(num()),
    source_key: str(),
  }),
  legacy_threshold_sweep: obj({
    status: lit('legacy_snapshot_calculation'),
    note: str(),
    review_min: num(),
    chosen_accept_threshold: num(),
    false_accept_cost_ratios: arr(num()),
    points: arr(legacyPointV),
    source_key: str(),
  }),
  mapping_exhibit: obj({ path: str(), sha256: str(), rows: int(), note: str() }),
});
export type SnapshotMethod = ReturnType<typeof methodV>;

export const snapshotV = obj({
  lab_snapshot_version: lit('1.0'),
  snapshot_id: str(),
  evidence: evidenceV,
  population: populationV,
  metric_definitions: record(
    obj({
      display_name: str(),
      definition: str(),
      numerator: str(),
      denominator: str(),
      scope: str(),
      unit: enumOf(['ratio', 'count', 'share'] as const),
      kind: enumOf(['accuracy', 'volume', 'workload', 'calibration', 'upper_bound'] as const),
    }),
    { minProperties: 1 },
  ),
  methods: record(methodV, { keys: METHODS, minProperties: 1 }),
  provenance: obj({
    eval_artifacts: record(filerefV),
    method_records: record(filerefV),
    review_sensitivity: filerefV,
    split: filerefV,
    note: str(),
  }),
});
export type LabSnapshot = ReturnType<typeof snapshotV>;

// ---------------------------------------------------------------- lab_cases

const exportedRowV = obj(
  {
    method_version: str(),
    exported: lit(true),
    b_id: str({ pattern: B_ID }),
    score: num(),
    probability: num(),
    tier: enumOf(['auto_accept', 'review'] as const),
    top2_gap: nullable(num()),
    gap_state: enumOf(['exported', 'single_candidate'] as const),
    block_keys: arr(str({ pattern: BLOCK_KEY })),
    ambiguity_demoted_derived: nullable(bool),
    gap_at_rounded_boundary: bool,
    run_id: str(),
    decided_at_utc: str(),
    source: str(),
  },
  { optional: ['gap_at_rounded_boundary'] },
);
export type ExportedEvidenceRow = ReturnType<typeof exportedRowV>;

const notExportedRowV = obj({
  method_version: str(),
  exported: lit(false),
  state: lit('not_exported'),
  reason: enumOf(['reject_or_no_candidate', 'rejected', 'no_candidate'] as const),
  source: str(),
});
export type NotExportedEvidenceRow = ReturnType<typeof notExportedRowV>;
export type EvidenceRow = ExportedEvidenceRow | NotExportedEvidenceRow;

const evidenceRowV: Validator<EvidenceRow> = oneOf<[ExportedEvidenceRow, NotExportedEvidenceRow]>(exportedRowV, notExportedRowV);

const truthUnavailableV = obj({ state: lit('truth_unavailable'), note: str() }, { optional: ['note'] });
const verifiedLocalV = obj(
  {
    state: lit('verified_local'),
    labelled: bool,
    truth_b_ids: arr(str({ pattern: B_ID })),
    n_candidates_full: int({ min: 0 }),
    truth_reachable_full: nullable(bool),
    truth_visible_in_exported_choices: nullable(bool),
    per_method: record(
      obj(
        { chosen_correct: nullable(bool), unrounded_gap: nullable(num()), unrounded_ambiguous: nullable(bool), note: str() },
        { optional: ['note'] },
      ),
    ),
    verifier: str(),
  },
  { optional: ['truth_visible_in_exported_choices'] },
);
export type LabelsUnavailable = ReturnType<typeof truthUnavailableV>;
export type LabelsVerified = ReturnType<typeof verifiedLocalV>;
export type CaseLabels = LabelsUnavailable | LabelsVerified;
const labelsV: Validator<CaseLabels> = oneOf<[LabelsUnavailable, LabelsVerified]>(truthUnavailableV, verifiedLocalV);

const narrativeV = obj({ kind: lit('narrative'), source: str(), note: str() });
export type Narrative = ReturnType<typeof narrativeV>;

const caseV = obj({
  case_id: str({ pattern: A_ID }),
  a_id: str({ pattern: A_ID }),
  reason_codes: arr(str({ pattern: REASON_CODE }), { min: 1 }),
  narrative: oneOf<[null, Narrative]>(nil, narrativeV),
  evidence: arr(evidenceRowV, { min: 3, max: 3 }),
  comparison: obj({
    methods_exported: int({ min: 0, max: 3 }),
    distinct_chosen_b_ids: int({ min: 0 }),
    agreement_class: enumOf(['all_exported_agree', 'methods_disagree', 'single_method_exported', 'none_exported'] as const),
    note: str(),
  }),
  labels: labelsV,
});
export type LabCase = ReturnType<typeof caseV>;

export const casesV = obj({
  lab_cases_version: lit('1.0'),
  snapshot_id: str(),
  policies: record(
    obj({ accept_min: num(), review_min: num(), ambiguity_gap: num(), score_kind: enumOf(SCORE_KINDS), source_key: str() }),
    { keys: METHODS },
  ),
  selection: obj({
    strategy_version: str(),
    total_cases: int(),
    counts_by_reason: record(int()),
    criteria: arr(criterionV),
    limitations: arr(str()),
    local_evidence: obj(
      {
        available: bool,
        note: str(),
        verifier: str(),
        truth_content_sha256: str(),
        candidates_file_sha256: str(),
        features_file_sha256: str(),
      },
      { optional: ['verifier', 'truth_content_sha256', 'candidates_file_sha256', 'features_file_sha256'] },
    ),
  }),
  cases: arr(caseV),
});
export type LabCases = ReturnType<typeof casesV>;

// ---------------------------------------------------------------- lab_replay_meta

export const REPLAY_COLUMNS = ['v1', 'v2', 'n_candidates', 'labelled', 'top1_correct', 'truth_reachable'] as const;

export const replayMetaV = obj({
  lab_replay_version: lit('1.0'),
  snapshot_id: str(),
  method_version: str(),
  decision_value_kind: enumOf(SCORE_KINDS),
  file: str(),
  columns: (x, path) => {
    const cols = arr(str())(x, path);
    if (cols.length !== REPLAY_COLUMNS.length || cols.some((c, i) => c !== REPLAY_COLUMNS[i])) {
      throw new ValidationError(path, `columns must be exactly ${REPLAY_COLUMNS.join(',')}`);
    }
    return cols;
  },
  rows: int({ min: 0 }),
  population: populationV,
  completeness: obj({
    a_records_expected: int(),
    a_records_in_file: int(),
    with_candidates: int(),
    without_candidates: int(),
    labelled: int(),
    labelled_reachable: int(),
    conserved: bool,
  }),
  inputs: arr(obj({ path: str(), sha256: str(), role: str(), manifest_key: str() }, { optional: ['manifest_key'] })),
  native_policy: policyV,
  reconciliation: obj({
    eval_artifact: str(),
    eval_artifact_sha256: str(),
    all_equal: bool,
    checks: arr(obj({ metric: str(), replay: any, artifact: any, equal: bool })),
  }),
  floor_sweep_reconciliation: obj({ all_equal: bool, points_compared: int() }),
  legacy_sweep_divergence: obj({
    note: str(),
    thresholds_differing: int(),
    max_accepts_difference: int(),
    points: arr(
      obj({
        threshold: num(),
        legacy_accepts: int(),
        corrected_accepts: int(),
        legacy_review_queue: int(),
        corrected_review_queue: int(),
        legacy_matches_artifact: bool,
      }),
    ),
  }),
  a_id_order_sha256: str({ pattern: SHA256 }),
  note: str(),
});
export type ReplayMeta = ReturnType<typeof replayMetaV>;

// ---------------------------------------------------------------- lab_receipt

const snapshotRefV = obj({
  snapshot_id: str({ maxLength: 80 }),
  analytical_digest: str({ pattern: SHA256 }),
  evaluation_code_commit: str({ pattern: COMMIT40 }),
  feature_version: str({ maxLength: 20 }),
  lab_contract_version: lit('1.0'),
});
export type SnapshotRef = ReturnType<typeof snapshotRefV>;

export const CHOSEN_ACTIONS = ['adopt_scenario_for_review', 'defer', 'reject_scenario', 'insufficient_evidence', 'no_feasible_scenario'] as const;
export type ChosenAction = (typeof CHOSEN_ACTIONS)[number];
export const CONTROL_KINDS = ['native', 'supported_floor', 'replay'] as const;
export type ControlKind = (typeof CONTROL_KINDS)[number];
export const VERIFIED_BY = ['artifact', 'replay', 'narrative', 'user'] as const;
export type VerifiedBy = (typeof VERIFIED_BY)[number];

export const receiptV = obj({
  receipt_version: lit('1.0'),
  receipt_id: str({ pattern: EVENT_ID }),
  kind: lit('policy_scenario'),
  created_at_utc: str({ maxLength: 40 }),
  decision_question: str({ maxLength: 2000 }),
  snapshot: snapshotRefV,
  population: obj({ fold: lit('test'), grain: lit('a_record'), a_records: int(), labelled_a: int() }),
  method: obj({
    method_version: enumOf(METHODS),
    score_kind: str(),
    policy: boundedPolicyV,
    policy_source: str({ maxLength: 200 }),
  }),
  selected_controls: obj(
    {
      control_kind: enumOf(CONTROL_KINDS),
      review_floor: nullable(num()),
      replay_policy: oneOf<[null, PolicyJson]>(nil, boundedPolicyV),
      scenario_id: str({ pattern: SCENARIO_ID }),
      what_stayed_fixed: str({ maxLength: 1000 }),
    },
    { optional: ['what_stayed_fixed'] },
  ),
  user_constraints: obj(
    {
      queue_budget: nullable(int({ min: 0 })),
      review_minutes_per_row: nullable(num({ min: 0 })),
      notes: str({ maxLength: 2000 }),
    },
    { optional: ['review_minutes_per_row'] },
  ),
  observations: arr(
    obj({
      claim: str({ maxLength: 500 }),
      value: oneOf<[number, string, null]>(num(), str(), nil),
      source_key: str({ maxLength: 300 }),
      verified_by: enumOf(VERIFIED_BY),
    }),
    { max: 100 },
  ),
  assumptions: arr(str({ maxLength: 500 }), { max: 50 }),
  alternatives_considered: arr(obj({ option: str({ maxLength: 200 }), why_not: str({ maxLength: 1000 }) }), { max: 50 }),
  chosen_action: enumOf(CHOSEN_ACTIONS),
  rationale: str({ maxLength: 4000 }),
  limitations: arr(str({ maxLength: 500 }), { max: 50 }),
  outcome: obj({ status: enumOf(['not_observed', 'not_measured'] as const), measured_value: nil }),
});
export type LabReceipt = ReturnType<typeof receiptV>;

// ---------------------------------------------------------------- lab_review_events

export const EVENT_METHODS = ['exact_v1', 'rules_v1', 'learned_v1', 'synthetic_exact_like', 'synthetic_rules_like'] as const;
export type EventMethod = (typeof EVENT_METHODS)[number];
export const ACTIONS = ['accept_candidate', 'reject_candidate', 'defer', 'undo'] as const;
export type Action = (typeof ACTIONS)[number];
export const REASON_CODES = [
  'evidence_sufficient', 'tie_unresolvable', 'needs_source_lookup', 'candidate_wrong_work', 'candidate_right_work',
  'insufficient_evidence', 'reversal', 'other',
] as const;
export type ReasonCode = (typeof REASON_CODES)[number];
export const EVENT_A_ID = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|SYN-A-[0-9]{3})$/;
export const EVENT_B_ID = /^([1-9][0-9]{0,11}|SYN-B-[0-9]{3})$/;

export const eventV = obj({
  event_id: str({ pattern: EVENT_ID }),
  seq: int({ min: 1 }),
  occurred_at_utc: str({ maxLength: 40 }),
  snapshot_id: str({ maxLength: 80 }),
  scenario_id: str({ pattern: SCENARIO_ID }),
  a_id: str({ pattern: EVENT_A_ID }),
  method_version: enumOf(EVENT_METHODS),
  action: enumOf(ACTIONS),
  b_id: nullable(str({ pattern: EVENT_B_ID })),
  reason_code: enumOf(REASON_CODES),
  rationale: nullable(str({ maxLength: 2000 })),
  supersedes_event_id: nullable(str({ pattern: EVENT_ID })),
  reverses_event_id: nullable(str({ pattern: EVENT_ID })),
  evidence_ref: obj({ case_id: str({ maxLength: 80 }), source: enumOf(['cases.json', 'synthetic_sandbox'] as const) }),
});
export type ReviewEvent = ReturnType<typeof eventV>;

export const reviewEventsV = obj({
  review_events_version: lit('1.0'),
  snapshot: snapshotRefV,
  exported_at_utc: str({ maxLength: 40 }),
  events: arr(eventV, { max: 5000 }),
});
export type ReviewEventsExport = ReturnType<typeof reviewEventsV>;

// ---------------------------------------------------------------- lab_synthetic_sandbox

const recordAV = obj({ id: str({ pattern: SYN_A }), title: str(), artist_credit: str(), year: nullable(int()) });
const recordBV = obj({ id: str({ pattern: SYN_B }), title: str(), artist_credit: str(), year: nullable(int()) });
export type SyntheticRecord = ReturnType<typeof recordAV>;

export const SYN_SCORE_KINDS = ['synthetic_exact_like', 'synthetic_rules_like'] as const;
export type SynScoreKind = (typeof SYN_SCORE_KINDS)[number];

export const sandboxV = obj({
  synthetic: lit(true),
  sandbox_version: lit('1.0'),
  badge: str(),
  generated_by: str(),
  vocabulary: arr(str()),
  records: obj({ a: arr(recordAV), b: arr(recordBV) }),
  candidates: arr(
    obj({
      a_id: str({ pattern: SYN_A }),
      b_id: str({ pattern: SYN_B }),
      values: obj({ synthetic_exact_like: num(), synthetic_rules_like: num() }),
    }),
  ),
  labels: record(arr(str({ pattern: SYN_B })), { keyPattern: SYN_A }),
  score_kinds: obj({ synthetic_exact_like: str(), synthetic_rules_like: str() }),
  policies: arr(obj({ preset: str(), policy: boundedPolicyV })),
  cases: arr(
    obj({
      case_id: str({ pattern: /^SYN-CASE-[a-z0-9_]+$/ }),
      a_id: str({ pattern: SYN_A }),
      purpose: str(),
      expected: record(record(any)),
    }),
  ),
  downstream_fixture: obj({
    note: str(),
    fact_rows: arr(obj({ b_id: str({ pattern: SYN_B }), units: int() })),
    mapping_with_duplicate: arr(obj({ a_id: str({ pattern: SYN_A }), b_id: str({ pattern: SYN_B }) })),
    conserved_row_count: int(),
  }),
});
export type SyntheticSandbox = ReturnType<typeof sandboxV>;
