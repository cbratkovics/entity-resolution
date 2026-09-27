/**
 * Synthetic sandbox mechanics: decisions per invented A record under a preset or edited policy,
 * the expected-value check per case, and the downstream duplicate-join demonstration. Nothing
 * here touches the real snapshot; scenario ids are `synthetic:<preset>`.
 */
import { SYN_SCORE_KINDS, type SynScoreKind, type SyntheticSandbox } from './contracts';
import { decideRow, rankCandidates, rowFromCandidates, type Candidate, type Decision, type Policy, type ReplayRow } from './policy';

export interface SandboxDecision {
  a_id: string;
  kind: SynScoreKind;
  ranked: Candidate[];
  chosen: string | null;
  row: ReplayRow;
  decision: Decision;
  truth_b_ids: string[];
}

export function candidatesFor(sandbox: SyntheticSandbox, aId: string, kind: SynScoreKind): Candidate[] {
  return sandbox.candidates.filter((c) => c.a_id === aId).map((c) => [c.b_id, c.values[kind]] as Candidate);
}

export function decideSandbox(sandbox: SyntheticSandbox, aId: string, kind: SynScoreKind, policy: Policy): SandboxDecision {
  const cands = candidatesFor(sandbox, aId, kind);
  const truth = sandbox.labels[aId] ?? [];
  const labelled = aId in sandbox.labels;
  const { chosen, row } = rowFromCandidates(cands, { labelled, truth_b_ids: new Set(truth) });
  return { a_id: aId, kind, ranked: rankCandidates(cands), chosen, row, decision: decideRow(row, policy), truth_b_ids: truth };
}

export function decideAll(sandbox: SyntheticSandbox, policy: Policy): SandboxDecision[] {
  const out: SandboxDecision[] = [];
  for (const a of sandbox.records.a) {
    for (const kind of SYN_SCORE_KINDS) out.push(decideSandbox(sandbox, a.id, kind, policy));
  }
  return out;
}

export interface ExpectationCheck {
  key: string;
  field: string;
  expected: unknown;
  actual: unknown;
  ok: boolean;
}

/**
 * Compare a case's `expected` block with the computed decisions. The block is keyed either by
 * score kind (`{synthetic_rules_like: {tier: ...}}`) or by preset then score kind
 * (`{strict: {synthetic_rules_like: {tier: ...}}}`); both shapes are handled. Only the fields
 * present in the expectation are compared (tier, reason, ambiguous, demoted, gap, chosen_b_id,
 * top1_correct, truth_reachable, n_candidates, v1, v2).
 */
export function checkExpectations(
  sandbox: SyntheticSandbox,
  caseId: string,
  preset: string,
  policy: Policy,
): ExpectationCheck[] {
  const c = sandbox.cases.find((x) => x.case_id === caseId);
  if (!c) return [];
  const out: ExpectationCheck[] = [];
  const compareBlock = (label: string, kind: SynScoreKind, block: Record<string, unknown>) => {
    const d = decideSandbox(sandbox, c.a_id, kind, policy);
    const actualOf: Record<string, unknown> = {
      tier: d.decision.tier,
      reason: d.decision.reason,
      ambiguous: d.decision.ambiguous,
      demoted: d.decision.demoted,
      gap: d.decision.gap,
      chosen: d.chosen,
      chosen_b_id: d.chosen,
      b_id: d.chosen,
      top1_correct: d.row.top1_correct,
      truth_reachable: d.row.truth_reachable,
      n_candidates: d.row.n_candidates,
      v1: d.row.v1,
      v2: d.row.v2,
    };
    for (const [field, expected] of Object.entries(block)) {
      if (!(field in actualOf)) continue;
      const actual = actualOf[field];
      const ok = typeof expected === 'number' && typeof actual === 'number' ? Object.is(expected, actual) : expected === actual;
      out.push({ key: label, field, expected, actual, ok });
    }
  };
  for (const [key, value] of Object.entries(c.expected)) {
    if ((SYN_SCORE_KINDS as readonly string[]).includes(key)) {
      compareBlock(key, key as SynScoreKind, value);
    } else if (key === preset) {
      for (const [kind, block] of Object.entries(value)) {
        if ((SYN_SCORE_KINDS as readonly string[]).includes(kind) && block && typeof block === 'object') {
          compareBlock(`${key}/${kind}`, kind as SynScoreKind, block as Record<string, unknown>);
        }
      }
    }
  }
  return out;
}

export interface JoinDemo {
  fact_rows: number;
  joined_rows: number;
  conserved_row_count: number;
  inflated: boolean;
  duplicated_b_ids: string[];
  joined: { b_id: string; a_id: string; units: number }[];
  units_before: number;
  units_after: number;
}

/** Join fact rows to the mapping with a duplicate: shows row inflation against the conserved count. */
export function joinDemo(sandbox: SyntheticSandbox): JoinDemo {
  const f = sandbox.downstream_fixture;
  const byB = new Map<string, string[]>();
  for (const m of f.mapping_with_duplicate) {
    const list = byB.get(m.b_id) ?? [];
    list.push(m.a_id);
    byB.set(m.b_id, list);
  }
  const joined: JoinDemo['joined'] = [];
  for (const row of f.fact_rows) {
    for (const a of byB.get(row.b_id) ?? []) joined.push({ b_id: row.b_id, a_id: a, units: row.units });
  }
  const duplicated = [...byB.entries()].filter(([, v]) => v.length > 1).map(([k]) => k);
  return {
    fact_rows: f.fact_rows.length,
    joined_rows: joined.length,
    conserved_row_count: f.conserved_row_count,
    inflated: joined.length !== f.conserved_row_count,
    duplicated_b_ids: duplicated,
    joined,
    units_before: f.fact_rows.reduce((s, r) => s + r.units, 0),
    units_after: joined.reduce((s, r) => s + r.units, 0),
  };
}
