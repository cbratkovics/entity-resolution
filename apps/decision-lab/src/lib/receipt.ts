/**
 * Policy-scenario receipts (lab_receipt contract): build one from the current scenario, validate
 * imported ones strictly and refuse anything from a different snapshot or from the sandbox.
 */
import { receiptV, type ChosenAction, type LabManifest, type LabReceipt, type LabSnapshot, type SnapshotRef, type VerifiedBy } from './contracts';
import { fmtInt, fmtNum, fmtRatio } from './format';
import { newEventId } from './ledger';
import type { EvaluateResult } from './policy';
import { isSynthetic, scenarioId, type RealScenario } from './scenario';
import { findFloorPoint, whatStayedFixed } from './evidence';
import { ValidationError } from './validate';

export const DECISION_QUESTION =
  'Which records should this matching policy accept automatically, send to review, or leave unresolved, and what evidence and trade-offs justify that decision?';

export function snapshotRef(manifest: LabManifest): SnapshotRef {
  return {
    snapshot_id: manifest.snapshot_id,
    analytical_digest: manifest.analytical_digest,
    evaluation_code_commit: manifest.evidence.evaluation_code_commit,
    feature_version: manifest.evidence.feature_version,
    lab_contract_version: '1.0',
  };
}

export interface Observation {
  claim: string;
  value: number | string | null;
  source_key: string;
  verified_by: VerifiedBy;
}

export interface ReceiptDraft {
  decision_question: string;
  queue_budget: number | null;
  review_minutes_per_row: number | null;
  notes: string;
  user_observations: Observation[];
  extra_assumptions: string[];
  alternatives: { option: string; why_not: string }[];
  chosen_action: ChosenAction;
  rationale: string;
  extra_limitations: string[];
}

export const DEFAULT_ASSUMPTIONS = [
  'labelled precision is extrapolated only where stated (legacy cost curve); elsewhere it applies to labelled accepts only',
  'review-recall is an upper bound: every queued reachable record resolved correctly, not observed reviewer performance',
  'unlabelled records are not known non-matches; unverified accepts are counted by coverage, never by precision',
  'the frozen benchmark is retrospective: nothing here refits a model, selects a champion or measures production outcomes',
];

/** Observations auto-filled from the evidence at the scenario (artifact) or a replay result. */
export function scenarioObservations(snapshot: LabSnapshot, scenario: RealScenario, replay: EvaluateResult | null): Observation[] {
  const m = snapshot.methods[scenario.method];
  if (!m) return [];
  const out: Observation[] = [];
  const metric = (key: string, claim: string) => {
    const x = m.metrics[key];
    if (!x) return;
    out.push({ claim, value: x.value === null || x.denominator === 0 ? null : x.value, source_key: x.source_key, verified_by: 'artifact' });
  };
  const count = (key: string, claim: string) => {
    const x = m.counts[key];
    if (!x) return;
    out.push({ claim, value: x.value, source_key: x.source_key, verified_by: 'artifact' });
  };
  metric('precision', `${scenario.method} labelled precision at the recorded policy`);
  metric('recall_labelled', `${scenario.method} reachable-labelled recall at the recorded policy`);
  metric('recall_overall', `${scenario.method} overall-labelled recall at the recorded policy`);
  metric('f1', `${scenario.method} F1 at the recorded policy`);
  metric('coverage', `${scenario.method} coverage at the recorded policy`);
  count('review_queue', `${scenario.method} review queue at the recorded policy`);
  count('unverified_accepts', `${scenario.method} unverified accepts at the recorded policy`);
  if (scenario.kind === 'supported_floor') {
    const p = findFloorPoint(m, scenario.floor);
    if (p) {
      const key = `${m.review_floor.source_key}[floor=${fmtNum(p.floor)}]`;
      out.push({ claim: `queue_total at review floor ${fmtNum(p.floor)}`, value: p.queue_total, source_key: key, verified_by: 'artifact' });
      out.push({ claim: `queue_floor at review floor ${fmtNum(p.floor)}`, value: p.queue_floor, source_key: key, verified_by: 'artifact' });
      out.push({ claim: `queue_ambiguity at review floor ${fmtNum(p.floor)}`, value: p.queue_ambiguity, source_key: key, verified_by: 'artifact' });
      out.push({ claim: `recall_with_review (upper bound) at review floor ${fmtNum(p.floor)}`, value: p.recall_with_review, source_key: key, verified_by: 'artifact' });
    }
  }
  if (scenario.kind === 'replay' && replay) {
    const pol = `replay(accept_min=${fmtNum(replay.policy.accept_min)}, review_min=${fmtNum(replay.policy.review_min)}, ambiguity_gap=${fmtNum(replay.policy.ambiguity_gap)})`;
    out.push({ claim: `labelled precision under ${pol}`, value: replay.at_auto_accept.precision, source_key: `${pol}#at_auto_accept.precision`, verified_by: 'replay' });
    out.push({ claim: `reachable-labelled recall under ${pol}`, value: replay.at_auto_accept.recall_labelled, source_key: `${pol}#at_auto_accept.recall_labelled`, verified_by: 'replay' });
    out.push({ claim: `F1 under ${pol}`, value: replay.at_auto_accept.f1, source_key: `${pol}#at_auto_accept.f1`, verified_by: 'replay' });
    out.push({ claim: `coverage under ${pol}`, value: replay.coverage, source_key: `${pol}#coverage`, verified_by: 'replay' });
    out.push({ claim: `review queue under ${pol}`, value: replay.ambiguity_rule.review_queue, source_key: `${pol}#ambiguity_rule.review_queue`, verified_by: 'replay' });
    out.push({ claim: `unverified accepts under ${pol}`, value: replay.unverified_accepts.count, source_key: `${pol}#unverified_accepts.count`, verified_by: 'replay' });
  }
  return out;
}

/** Alternatives prefilled from the other methods and the other exported floors of the chosen method. */
export function defaultAlternatives(snapshot: LabSnapshot, scenario: RealScenario): { option: string; why_not: string }[] {
  const out: { option: string; why_not: string }[] = [];
  for (const name of Object.keys(snapshot.methods)) {
    if (name === scenario.method) continue;
    const m = snapshot.methods[name];
    if (!m) continue;
    const f1 = m.metrics.f1;
    const q = m.counts.review_queue;
    out.push({
      option: `native:${name}`,
      why_not: `not chosen; recorded F1 ${f1 ? fmtRatio(f1.value) : 'unavailable'}, review queue ${q ? fmtInt(q.value) : 'unavailable'} at its own thresholds`,
    });
  }
  const m = snapshot.methods[scenario.method];
  if (m && scenario.kind !== 'replay') {
    const current = scenario.kind === 'supported_floor' ? scenario.floor : m.policy.review_min;
    for (const p of [...m.review_floor.points].sort((a, b) => a.floor - b.floor)) {
      if (p.floor === current) continue;
      out.push({ option: `floor:${scenario.method}:${fmtNum(p.floor)}`, why_not: `not chosen; queue_total ${fmtInt(p.queue_total)}, recall_with_review ${fmtRatio(p.recall_with_review)}` });
      if (out.length >= 20) break;
    }
  }
  return out.slice(0, 50);
}

export function defaultLimitations(manifest: LabManifest): string[] {
  const out: string[] = [];
  for (const l of manifest.selection.limitations) out.push(l.slice(0, 500));
  const caps = manifest.capabilities;
  for (const [name, c] of Object.entries({
    evidence_comparison: caps.evidence_comparison,
    supported_floor_control: caps.supported_floor_control,
    case_explorer: caps.case_explorer,
    decision_ledger: caps.decision_ledger,
    synthetic_sandbox: caps.synthetic_sandbox,
    local_case_evidence: caps.local_case_evidence,
  })) {
    if (!c.available) out.push(`${name} unavailable: ${c.note}`.slice(0, 500));
  }
  for (const [name, c] of Object.entries(caps.complete_replay)) {
    if (!c.available) out.push(`complete replay unavailable for ${name}: ${c.note}`.slice(0, 500));
  }
  out.push('test fold only; one decision per A record; the frozen benchmark metrics are unchanged by any local decision');
  return out.slice(0, 50);
}

export function buildReceipt(
  manifest: LabManifest,
  snapshot: LabSnapshot,
  scenario: RealScenario,
  draft: ReceiptDraft,
  replay: EvaluateResult | null,
): LabReceipt {
  const id = scenarioId(scenario);
  if (isSynthetic(id)) throw new Error('receipts are refused for sandbox scenarios');
  const m = snapshot.methods[scenario.method];
  if (!m) throw new Error(`method ${scenario.method} is not in the snapshot`);
  const observations = [...scenarioObservations(snapshot, scenario, replay), ...draft.user_observations].slice(0, 100);
  const receipt: LabReceipt = {
    receipt_version: '1.0',
    receipt_id: newEventId(),
    kind: 'policy_scenario',
    created_at_utc: new Date().toISOString(),
    decision_question: draft.decision_question.slice(0, 2000),
    snapshot: snapshotRef(manifest),
    population: { fold: 'test', grain: 'a_record', a_records: snapshot.population.a_records, labelled_a: snapshot.population.labelled_a },
    method: {
      method_version: scenario.method,
      score_kind: m.score_kind,
      policy: { accept_min: m.policy.accept_min, review_min: m.policy.review_min, ambiguity_gap: m.policy.ambiguity_gap },
      policy_source: m.policy_source.slice(0, 200),
    },
    selected_controls: {
      control_kind: scenario.kind,
      review_floor: scenario.kind === 'supported_floor' ? scenario.floor : scenario.kind === 'native' ? m.policy.review_min : null,
      replay_policy: scenario.kind === 'replay' ? { ...scenario.policy } : null,
      scenario_id: id,
      what_stayed_fixed:
        scenario.kind === 'supported_floor'
          ? whatStayedFixed(m)
          : scenario.kind === 'native'
            ? 'the recorded policy; nothing moved'
            : 'nothing: every threshold was replayed',
    },
    user_constraints: {
      queue_budget: draft.queue_budget,
      review_minutes_per_row: draft.review_minutes_per_row,
      notes: draft.notes.slice(0, 2000),
    },
    observations: observations.map((o) => ({ ...o, claim: o.claim.slice(0, 500), source_key: o.source_key.slice(0, 300) })),
    assumptions: [...DEFAULT_ASSUMPTIONS, ...draft.extra_assumptions].map((s) => s.slice(0, 500)).slice(0, 50),
    alternatives_considered: draft.alternatives.map((a) => ({ option: a.option.slice(0, 200), why_not: a.why_not.slice(0, 1000) })).slice(0, 50),
    chosen_action: draft.chosen_action,
    rationale: draft.rationale.slice(0, 4000),
    limitations: [...defaultLimitations(manifest), ...draft.extra_limitations].map((s) => s.slice(0, 500)).slice(0, 50),
    outcome: { status: 'not_observed', measured_value: null },
  };
  // Self-check against the contract before export.
  return receiptV(JSON.parse(JSON.stringify(receipt)), 'receipt');
}

export function receiptFileName(receipt: LabReceipt): string {
  return `receipt-${receipt.snapshot.snapshot_id.replace(/[^A-Za-z0-9_@.+-]/g, "_")}-${receipt.receipt_id}.json`;
}

export type ReceiptImportResult =
  | { status: 'ok'; receipt: LabReceipt }
  | {
      status: 'rejected';
      reason: 'corrupt' | 'incompatible_snapshot' | 'synthetic';
      message: string;
      quarantine: { receipt_id: string; snapshot_id: string; analytical_digest: string; scenario_id: string; created_at_utc: string } | null;
    };

/** Validate an imported receipt strictly; a different snapshot is rejected with a quarantine summary and never applied. */
export function importReceipt(text: string, snapshot: SnapshotRef): ReceiptImportResult {
  let r: LabReceipt;
  try {
    r = receiptV(JSON.parse(text), 'import');
  } catch (e) {
    return {
      status: 'rejected',
      reason: 'corrupt',
      message: e instanceof ValidationError ? `the file does not match the receipt contract (${e.message})` : 'the file is not valid JSON',
      quarantine: null,
    };
  }
  const quarantine = {
    receipt_id: r.receipt_id,
    snapshot_id: r.snapshot.snapshot_id,
    analytical_digest: r.snapshot.analytical_digest,
    scenario_id: r.selected_controls.scenario_id,
    created_at_utc: r.created_at_utc,
  };
  if (r.snapshot.snapshot_id !== snapshot.snapshot_id || r.snapshot.analytical_digest !== snapshot.analytical_digest) {
    return { status: 'rejected', reason: 'incompatible_snapshot', message: 'incompatible snapshot: the receipt was built on different evidence', quarantine };
  }
  if (isSynthetic(r.selected_controls.scenario_id)) {
    return { status: 'rejected', reason: 'synthetic', message: 'sandbox scenarios cannot be applied as receipts', quarantine };
  }
  return { status: 'ok', receipt: r };
}
