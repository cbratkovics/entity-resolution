/** Number and text formatting. No figure is typed here; these only render values read from the data. */
import type { Metric, ScoreKind } from './contracts';

export const UNAVAILABLE = 'unavailable';

export function fmtInt(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return UNAVAILABLE;
  return x.toLocaleString('en-US');
}

export function fmtRatio(x: number | null | undefined, digits = 6): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return UNAVAILABLE;
  return x.toFixed(digits);
}

/** Shortest round-trip form of a threshold or score (what the data files carry). */
export function fmtNum(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return UNAVAILABLE;
  return String(x);
}

export function fmtPercent(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return UNAVAILABLE;
  return `${(x * 100).toFixed(digits)}%`;
}

/**
 * Render a snapshot metric. A null value or a zero denominator renders as
 * "unavailable (denominator 0)" and never as 0 or 1 (a null denominator with a value is a
 * derived ratio such as F1 and renders its value).
 */
export function fmtMetric(m: Metric | undefined, unit: 'ratio' | 'count' | 'share' = 'ratio'): string {
  if (!m) return UNAVAILABLE;
  if (m.value === null || m.denominator === 0) {
    return m.unavailable_reason ? `unavailable (${m.unavailable_reason})` : 'unavailable (denominator 0)';
  }
  return unit === 'count' ? fmtInt(m.value) : fmtRatio(m.value);
}

export function metricFraction(m: Metric | undefined): string {
  if (!m || m.numerator === null || m.denominator === null) return 'numerator / denominator not exported';
  return `${fmtInt(m.numerator)} / ${fmtInt(m.denominator)}`;
}

export function scoreKindLabel(kind: ScoreKind | 'unavailable' | string): string {
  switch (kind) {
    case 'binary_score':
      return 'binary score';
    case 'uncalibrated_score':
      return 'uncalibrated score';
    case 'calibrated_probability':
      return 'calibrated probability (pair-level)';
    case 'unavailable':
      return 'unavailable';
    default:
      return kind;
  }
}

export function shortCommit(commit: string): string {
  return commit.slice(0, 12);
}

export function tierLabel(tier: string): string {
  switch (tier) {
    case 'auto_accept':
      return 'auto-accept';
    case 'review':
      return 'review';
    case 'reject':
      return 'reject';
    default:
      return tier;
  }
}

export function reasonLabel(reason: string): string {
  switch (reason) {
    case 'no_candidate':
      return 'no candidate';
    case 'value_at_or_above_accept_min':
      return 'value at or above accept_min';
    case 'value_at_or_above_review_min':
      return 'value at or above review_min (below accept_min)';
    case 'value_below_review_min':
      return 'value below review_min';
    case 'ambiguity_gap_below_threshold':
      return 'top-two gap below ambiguity_gap';
    default:
      return reason;
  }
}
