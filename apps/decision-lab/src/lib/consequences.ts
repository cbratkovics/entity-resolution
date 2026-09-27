/**
 * Consequences of local decisions for an explicitly selected case set, in one scenario.
 * These are counts of local decisions: not labels, not new ground truth, not measured quality;
 * the frozen benchmark metrics are unchanged.
 */
import type { LabCase, MethodVersion, ReviewEvent } from './contracts';
import { effectiveState, effectiveStatus } from './ledger';

export interface Consequences {
  scenario_id: string;
  cases_in_set: number;
  cases_with_events: number;
  accepted_mappings: number;
  deferred: number;
  rejected_candidates: number;
  changed_vs_baseline: number;
  unresolved: number;
  accepted_list: { a_id: string; b_id: string; baseline_b_id: string | null }[];
}

export const CONSEQUENCE_DISCLAIMER =
  'local decisions; not labels, not new ground truth, not measured quality; frozen benchmark metrics are unchanged';

export function baselineChosenB(c: LabCase, method: MethodVersion): string | null {
  const row = c.evidence.find((r) => r.method_version === method);
  return row && row.exported ? row.b_id : null;
}

/** Cases that have at least one event (live or reversed) in the scenario. */
export function casesWithEvents(events: readonly ReviewEvent[], scenarioId: string, cases: readonly LabCase[]): LabCase[] {
  const ids = new Set(events.filter((e) => e.scenario_id === scenarioId).map((e) => e.a_id));
  return cases.filter((c) => ids.has(c.a_id));
}

export function consequences(events: readonly ReviewEvent[], scenarioId: string, method: MethodVersion, caseSet: readonly LabCase[]): Consequences {
  const out: Consequences = {
    scenario_id: scenarioId,
    cases_in_set: caseSet.length,
    cases_with_events: 0,
    accepted_mappings: 0,
    deferred: 0,
    rejected_candidates: 0,
    changed_vs_baseline: 0,
    unresolved: 0,
    accepted_list: [],
  };
  for (const c of caseSet) {
    const s = effectiveState(events, scenarioId, c.a_id);
    if (s.event_count > 0) out.cases_with_events += 1;
    out.rejected_candidates += s.rejected_b.length;
    const status = effectiveStatus(s);
    if (status === 'accepted' && s.accepted_b) {
      out.accepted_mappings += 1;
      const base = baselineChosenB(c, method);
      if (base !== s.accepted_b) out.changed_vs_baseline += 1;
      out.accepted_list.push({ a_id: c.a_id, b_id: s.accepted_b, baseline_b_id: base });
    } else {
      out.unresolved += 1;
      if (status === 'deferred') out.deferred += 1;
    }
  }
  return out;
}
