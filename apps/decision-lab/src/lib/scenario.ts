/**
 * Scenario identity. A scenario is a method plus the control that produced its numbers:
 * `native:<method>`, `floor:<method>:<floor>`, `replay:<method>:<accept>:<review>:<gap>` or
 * `synthetic:<preset>` (sandbox only; never a real-snapshot scenario).
 */
import { METHODS, SCENARIO_ID, type ControlKind, type MethodVersion } from './contracts';
import type { Policy } from './policy';

export interface NativeScenario {
  kind: 'native';
  method: MethodVersion;
}
export interface FloorScenario {
  kind: 'supported_floor';
  method: MethodVersion;
  floor: number;
}
export interface ReplayScenario {
  kind: 'replay';
  method: MethodVersion;
  policy: Policy;
}
export type RealScenario = NativeScenario | FloorScenario | ReplayScenario;

export interface SyntheticScenario {
  kind: 'synthetic';
  preset: string;
}
export type Scenario = RealScenario | SyntheticScenario;

function numToken(x: number): string {
  // Shortest round-trip form; ids must match ^[a-z]+:[A-Za-z0-9_.:@-]{1,120}$ so "e-7" style is fine.
  return String(x).replace('+', '');
}

export function scenarioId(s: Scenario): string {
  let id: string;
  switch (s.kind) {
    case 'native':
      id = `native:${s.method}`;
      break;
    case 'supported_floor':
      id = `floor:${s.method}:${numToken(s.floor)}`;
      break;
    case 'replay':
      id = `replay:${s.method}:${numToken(s.policy.accept_min)}:${numToken(s.policy.review_min)}:${numToken(s.policy.ambiguity_gap)}`;
      break;
    case 'synthetic':
      id = `synthetic:${s.preset.replace(/[^A-Za-z0-9_.:@-]/g, '_').slice(0, 100)}`;
      break;
  }
  if (!SCENARIO_ID.test(id)) throw new Error(`scenario id does not match the contract: ${id}`);
  return id;
}

export function controlKind(s: RealScenario): ControlKind {
  return s.kind;
}

export function isSynthetic(id: string): boolean {
  return id.startsWith('synthetic:');
}

export function isMethod(x: unknown): x is MethodVersion {
  return typeof x === 'string' && (METHODS as readonly string[]).includes(x);
}

/** Read the compare-page query (`?method=&floor=&budget=&minutes=`) into a typed state. */
export interface CompareQuery {
  method: MethodVersion | null;
  floor: number | null;
  budget: number | null;
  minutes: number | null;
}

export function parseCompareQuery(params: URLSearchParams): CompareQuery {
  const m = params.get('method');
  const floorText = params.get('floor');
  const budgetText = params.get('budget');
  const minutesText = params.get('minutes');
  const floor = floorText !== null && /^\d*\.?\d+$/.test(floorText) ? Number(floorText) : null;
  const budget = budgetText !== null && /^\d{1,9}$/.test(budgetText) ? Number(budgetText) : null;
  const minutes = minutesText !== null && /^\d*\.?\d+$/.test(minutesText) ? Number(minutesText) : null;
  return {
    method: isMethod(m) ? m : null,
    floor: floor !== null && Number.isFinite(floor) ? floor : null,
    budget,
    minutes: minutes !== null && Number.isFinite(minutes) ? minutes : null,
  };
}

export function serialiseCompareQuery(q: CompareQuery): string {
  const p = new URLSearchParams();
  if (q.method) p.set('method', q.method);
  if (q.floor !== null) p.set('floor', numToken(q.floor));
  if (q.budget !== null) p.set('budget', String(q.budget));
  if (q.minutes !== null) p.set('minutes', numToken(q.minutes));
  const s = p.toString();
  return s ? `?${s}` : '';
}
