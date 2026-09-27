/** Record accept / reject / defer / undo for one record in the current scenario. */
import { useState } from 'react';
import { REASON_CODES, type EventMethod, type ReasonCode } from '../lib/contracts';
import { effectiveState, effectiveStatus, type EffectiveState } from '../lib/ledger';
import type { ReviewEvent } from '../lib/contracts';

export interface ReviewTarget {
  scenario_id: string;
  a_id: string;
  method_version: EventMethod;
  evidence_ref: { case_id: string; source: 'cases.json' | 'synthetic_sandbox' };
  /** Candidate B ids the user may accept or reject (exported choices plus truth ids). */
  candidates: { b_id: string; origin: string }[];
}

export function EffectiveStateText({ state }: { state: EffectiveState }) {
  const status = effectiveStatus(state);
  const text =
    status === 'accepted'
      ? `accepted candidate ${state.accepted_b}`
      : status === 'deferred'
        ? 'deferred'
        : status === 'rejected_only'
          ? `no accepted candidate; rejected: ${state.rejected_b.join(', ')}`
          : 'no local decision';
  return (
    <span data-testid="effective-state">
      <span className={`badge ${status === 'accepted' ? 'ok' : status === 'none' ? '' : 'warn'}`}>{status.replace('_', ' ')}</span> {text}
      {state.rejected_b.length && status !== 'rejected_only' ? <span className="muted"> (rejected: {state.rejected_b.join(', ')})</span> : null}
    </span>
  );
}

export function ReviewActions({
  target,
  events,
  onRecord,
  onUndo,
}: {
  target: ReviewTarget;
  events: readonly ReviewEvent[];
  onRecord: (input: { action: 'accept_candidate' | 'reject_candidate' | 'defer'; b_id: string | null; reason_code: ReasonCode; rationale: string | null }) => void;
  onUndo: () => void;
}) {
  const state = effectiveState(events, target.scenario_id, target.a_id);
  const [candidate, setCandidate] = useState<string>(target.candidates[0]?.b_id ?? '');
  const [reason, setReason] = useState<ReasonCode>('evidence_sufficient');
  const [rationale, setRationale] = useState('');
  const chosen = target.candidates.some((c) => c.b_id === candidate) ? candidate : target.candidates[0]?.b_id ?? '';
  const submit = (action: 'accept_candidate' | 'reject_candidate' | 'defer') => {
    onRecord({ action, b_id: action === 'defer' ? null : chosen, reason_code: reason, rationale: rationale.trim() ? rationale.trim().slice(0, 2000) : null });
  };
  return (
    <div className="panel" data-testid="review-actions">
      <h3 style={{ marginTop: 0 }}>Review actions (scenario {target.scenario_id})</h3>
      <p className="small">
        Effective state: <EffectiveStateText state={state} />
      </p>
      <div className="controls">
        <label>
          candidate B id
          <select value={chosen} onChange={(e) => setCandidate(e.target.value)} disabled={target.candidates.length === 0} data-testid="candidate-select">
            {target.candidates.map((c) => (
              <option key={`${c.b_id}-${c.origin}`} value={c.b_id}>
                {c.b_id} ({c.origin})
              </option>
            ))}
          </select>
        </label>
        <label>
          reason code
          <select value={reason} onChange={(e) => setReason(e.target.value as ReasonCode)} data-testid="reason-select">
            {REASON_CODES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="field">
        <label htmlFor={`rationale-${target.a_id}`}>rationale (optional, max 2000 characters, stored locally, never in the URL)</label>
        <textarea id={`rationale-${target.a_id}`} maxLength={2000} value={rationale} onChange={(e) => setRationale(e.target.value)} />
      </div>
      <div className="button-row">
        <button type="button" className="primary" disabled={!chosen} onClick={() => submit('accept_candidate')} data-testid="btn-accept">
          accept candidate {chosen || '—'}
        </button>
        <button type="button" disabled={!chosen} onClick={() => submit('reject_candidate')} data-testid="btn-reject">
          reject candidate {chosen || '—'}
        </button>
        <button type="button" onClick={() => submit('defer')} data-testid="btn-defer">
          defer
        </button>
        <button type="button" disabled={!state.last_event_id} onClick={onUndo} data-testid="btn-undo">
          undo last
        </button>
      </div>
      <p className="note">rejecting a candidate does not assert this record has no match anywhere. Decisions are local: not labels, not upstream writes.</p>
    </div>
  );
}
