/**
 * Pure computations for the Compare view: the rule-based "what the evidence says" panel, the
 * supported review-floor control, budget feasibility and the "why this tier?" explanation.
 * No number from the artifacts is typed here; everything is computed from the loaded snapshot.
 */
import { METHODS, type ExportedEvidenceRow, type LabSnapshot, type MethodVersion, type SnapshotFloorPoint, type SnapshotMethod } from './contracts';
import { fmtInt, fmtNum, fmtRatio, scoreKindLabel } from './format';
import { decideValues, makePolicy, type Decision } from './policy';

export function methodOrder(snapshot: LabSnapshot): MethodVersion[] {
  return METHODS.filter((m) => m in snapshot.methods);
}

function metricValue(m: SnapshotMethod, key: string): number | null {
  const x = m.metrics[key];
  if (!x || x.value === null || x.denominator === 0) return null;
  return x.value;
}

function countValue(m: SnapshotMethod, key: string): number | null {
  const x = m.counts[key];
  return x ? x.value : null;
}

function argBest(
  snapshot: LabSnapshot,
  pick: (m: SnapshotMethod) => number | null,
  better: (a: number, b: number) => boolean,
): { method: MethodVersion; value: number } | null {
  let best: { method: MethodVersion; value: number } | null = null;
  for (const name of methodOrder(snapshot)) {
    const m = snapshot.methods[name];
    if (!m) continue;
    const v = pick(m);
    if (v === null) continue;
    if (best === null || better(v, best.value)) best = { method: name, value: v };
  }
  return best;
}

export interface EvidenceStatement {
  text: string;
  source_keys: string[];
}

/** Rule-based statements; wording is fixed, the methods and values are computed. */
export function evidenceSays(snapshot: LabSnapshot): EvidenceStatement[] {
  const out: EvidenceStatement[] = [];
  const f1 = argBest(snapshot, (m) => metricValue(m, 'f1'), (a, b) => a > b);
  const precision = argBest(snapshot, (m) => metricValue(m, 'precision'), (a, b) => a > b);
  const queue = argBest(snapshot, (m) => countValue(m, 'review_queue'), (a, b) => a < b);
  const src = (method: MethodVersion, key: string, kind: 'metrics' | 'counts'): string => {
    const m = snapshot.methods[method];
    const entry = kind === 'metrics' ? m?.metrics[key] : m?.counts[key];
    return entry ? entry.source_key : `${method}.${kind}.${key}`;
  };
  if (f1) {
    out.push({
      text: `Highest F1 at the recorded policies: ${f1.method} (${fmtRatio(f1.value)}).`,
      source_keys: [src(f1.method, 'f1', 'metrics')],
    });
  }
  if (precision) {
    out.push({
      text: `Highest labelled precision: ${precision.method} (${fmtRatio(precision.value)}).`,
      source_keys: [src(precision.method, 'precision', 'metrics')],
    });
  }
  if (queue) {
    out.push({
      text: `Smallest review queue: ${queue.method} (${fmtInt(queue.value)} records).`,
      source_keys: [src(queue.method, 'review_queue', 'counts')],
    });
  }
  if (precision && f1 && precision.method !== f1.method) {
    const p = snapshot.methods[precision.method];
    const f = snapshot.methods[f1.method];
    if (p && f) {
      const pr = metricValue(p, 'recall_labelled');
      const fr = metricValue(f, 'recall_labelled');
      const pc = metricValue(p, 'coverage');
      const fc = metricValue(f, 'coverage');
      const parts: string[] = [];
      if (pr !== null && fr !== null && pr < fr) parts.push(`lower reachable-labelled recall (${fmtRatio(pr)} against ${fmtRatio(fr)})`);
      if (pc !== null && fc !== null && pc < fc) parts.push(`lower coverage (${fmtRatio(pc)} against ${fmtRatio(fc)})`);
      if (parts.length) {
        out.push({
          text: `The highest-precision method (${precision.method}) has ${parts.join(' and ')} than ${f1.method}.`,
          source_keys: [
            src(precision.method, 'recall_labelled', 'metrics'),
            src(f1.method, 'recall_labelled', 'metrics'),
            src(precision.method, 'coverage', 'metrics'),
            src(f1.method, 'coverage', 'metrics'),
          ],
        });
      }
    }
  }
  const thresholds = methodOrder(snapshot)
    .map((name) => {
      const m = snapshot.methods[name];
      return m ? `${name}: accept_min ${fmtNum(m.policy.accept_min)}, review_min ${fmtNum(m.policy.review_min)}, ambiguity_gap ${fmtNum(m.policy.ambiguity_gap)}` : '';
    })
    .filter(Boolean);
  out.push({
    text: `The methods use different recorded thresholds (${thresholds.join('; ')}), so the queue difference is not an equal-recall comparison.`,
    source_keys: methodOrder(snapshot).map((name) => snapshot.methods[name]?.policy_source ?? name),
  });
  for (const name of methodOrder(snapshot)) {
    const m = snapshot.methods[name];
    if (m && m.score_kind === 'uncalibrated_score') {
      out.push({ text: `The ${name} score is an ${scoreKindLabel(m.score_kind)}; its thresholds are not probabilities.`, source_keys: [`${name}.score_kind`] });
    }
  }
  return out;
}

// ---------------------------------------------------------------- floors and budgets

export function floorPoints(method: SnapshotMethod): SnapshotFloorPoint[] {
  return [...method.review_floor.points].sort((a, b) => a.floor - b.floor);
}

export function findFloorPoint(method: SnapshotMethod, floor: number): SnapshotFloorPoint | null {
  return method.review_floor.points.find((p) => p.floor === floor) ?? null;
}

/** The recorded policy's floor equals review_min; the native row is the point at that floor if exported. */
export function nativeFloorPoint(method: SnapshotMethod): SnapshotFloorPoint | null {
  return findFloorPoint(method, method.policy.review_min);
}

export interface FeasibleFloor {
  method: MethodVersion;
  point: SnapshotFloorPoint;
}

/** Exported floor points whose queue_total fits the budget, largest feasible floor first per method. Never interpolates. */
export function feasibleFloors(snapshot: LabSnapshot, budget: number): FeasibleFloor[] {
  const out: FeasibleFloor[] = [];
  if (!Number.isInteger(budget) || budget < 0) return out;
  for (const name of methodOrder(snapshot)) {
    const m = snapshot.methods[name];
    if (!m) continue;
    const pts = m.review_floor.points.filter((p) => p.queue_total <= budget).sort((a, b) => b.floor - a.floor);
    for (const p of pts) out.push({ method: name, point: p });
  }
  return out;
}

export function whatStayedFixed(method: SnapshotMethod): string {
  return `accept_min = ${fmtNum(method.policy.accept_min)}, ambiguity_gap = ${fmtNum(method.policy.ambiguity_gap)} (the method's recorded values); only the floor moved`;
}

/** Assumed reviewer effort: minutes per row times the queue. Displayed as an assumption, never as a cost or saving. */
export function assumedEffort(queueTotal: number, minutesPerRow: number | null): { minutes: number; hours: number } | null {
  if (minutesPerRow === null || !Number.isFinite(minutesPerRow) || minutesPerRow < 0) return null;
  const minutes = queueTotal * minutesPerRow;
  return { minutes, hours: minutes / 60 };
}

// ---------------------------------------------------------------- why this tier

export interface WhyTier {
  decision: Decision;
  basis: 'unrounded_local' | 'rounded_exported';
  matches_exported_tier: boolean;
  lines: string[];
}

/**
 * Explain a method's tier for a case from the exported (six-decimal rounded) values. When the
 * local verification stage exported the unrounded gap, that gap is used for the ambiguity test.
 */
export function whyTier(
  row: ExportedEvidenceRow,
  policy: { accept_min: number; review_min: number; ambiguity_gap: number },
  unroundedGap: number | null | undefined,
): WhyTier {
  const p = makePolicy(policy.accept_min, policy.review_min, policy.ambiguity_gap);
  const useLocal = unroundedGap !== undefined && unroundedGap !== null;
  const gap = useLocal ? unroundedGap : row.top2_gap;
  const v2 = gap === null ? null : row.probability - gap;
  const decision = decideValues(row.probability, v2, p);
  const lines: string[] = [];
  lines.push(
    `probability ${fmtNum(row.probability)} ${row.probability >= p.accept_min ? '>=' : '<'} accept_min ${fmtNum(p.accept_min)}` +
      (row.probability < p.accept_min ? `; ${row.probability >= p.review_min ? '>=' : '<'} review_min ${fmtNum(p.review_min)}` : ''),
  );
  if (gap === null) {
    lines.push(row.gap_state === 'single_candidate' ? 'single candidate: null gap, never ambiguous' : 'gap not exported');
  } else {
    lines.push(`top-two gap ${fmtNum(gap)} ${gap < p.ambiguity_gap ? '<' : '>='} ambiguity_gap ${fmtNum(p.ambiguity_gap)}${useLocal ? ' (unrounded local gap)' : ' (exported, six-decimal rounded)'}`);
  }
  if (row.gap_at_rounded_boundary && !useLocal) {
    lines.push('the rounded gap equals the threshold: the exhibit cannot classify ambiguity; the recorded tier is authoritative');
  }
  return { decision, basis: useLocal ? 'unrounded_local' : 'rounded_exported', matches_exported_tier: decision.tier === row.tier, lines };
}
