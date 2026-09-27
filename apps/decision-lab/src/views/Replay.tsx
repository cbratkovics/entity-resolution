import { useEffect, useMemo, useState } from 'react';
import { LineChart } from '../components/charts';
import { ErrorState, KeyValue, Loading, MethodName } from '../components/common';
import { METHODS, type MethodVersion, type SnapshotMethod } from '../lib/contracts';
import { fmtInt, fmtNum, fmtRatio, scoreKindLabel, tierLabel } from '../lib/format';
import { acceptSweep, evaluate, floorSweep, makePolicy, PolicyError, type EvaluateResult, type Policy } from '../lib/policy';
import type { Route } from '../lib/router';
import { scenarioId } from '../lib/scenario';
import { useCore, useStore } from '../store';

interface Check {
  key: string;
  replay: number | null;
  artifact: number | null;
  equal: boolean;
}

/** Compare a replay result with the snapshot's recorded metrics and counts. */
function reconcile(result: EvaluateResult, m: SnapshotMethod): Check[] {
  const mv = (k: string) => {
    const x = m.metrics[k];
    return x && x.denominator !== 0 ? x.value : null;
  };
  const cv = (k: string) => m.counts[k]?.value ?? null;
  const pairs: [string, number | null, number | null][] = [
    ['precision', result.at_auto_accept.precision, mv('precision')],
    ['recall_labelled', result.at_auto_accept.recall_labelled, mv('recall_labelled')],
    ['recall_overall', result.recall_overall, mv('recall_overall')],
    ['f1', result.at_auto_accept.f1, mv('f1')],
    ['coverage', result.coverage, mv('coverage')],
    ['pair_completeness_test', result.pair_completeness_test, mv('pair_completeness_test')],
    ['unverified_accepts_share', result.unverified_accepts.share_of_accepts, mv('unverified_accepts_share')],
    ['precision_or_review', result.at_auto_accept_or_review.precision, mv('precision_or_review')],
    ['recall_labelled_or_review', result.at_auto_accept_or_review.recall_labelled, mv('recall_labelled_or_review')],
    ['test_a', result.test_a, cv('test_a')],
    ['labelled_a', result.labelled_a, cv('labelled_a')],
    ['labelled_a_reachable', result.labelled_a_reachable, cv('labelled_a_reachable')],
    ['accepted_labelled', result.at_auto_accept.accepted, cv('accepted_labelled')],
    ['correct_labelled', result.at_auto_accept.correct, cv('correct_labelled')],
    ['accepted_all', result.accepted_all, cv('accepted_all')],
    ['unverified_accepts', result.unverified_accepts.count, cv('unverified_accepts')],
    ['review_queue', result.ambiguity_rule.review_queue, cv('review_queue')],
    ['decisions_moved_to_review', result.ambiguity_rule.decisions_moved_to_review, cv('decisions_moved_to_review')],
    ['tier_auto_accept', result.tier_counts.auto_accept, cv('tier_auto_accept')],
    ['tier_review', result.tier_counts.review, cv('tier_review')],
    ['tier_reject', result.tier_counts.reject, cv('tier_reject')],
  ];
  return pairs.map(([key, replay, artifact]) => ({ key, replay, artifact, equal: Object.is(replay, artifact) }));
}

function parsePolicy(a: string, r: string, g: string): { policy: Policy | null; message: string | null } {
  const nums = [a, r, g].map((t) => (t.trim() === '' ? NaN : Number(t)));
  if (nums.some((n) => !Number.isFinite(n))) return { policy: null, message: 'every threshold must be a finite number' };
  try {
    return { policy: makePolicy(nums[0], nums[1], nums[2]), message: null };
  } catch (e) {
    return { policy: null, message: e instanceof PolicyError ? e.message : String(e) };
  }
}

export function ReplayView({ route: _route }: { route: Route }) {
  const core = useCore();
  const { replays, ensureReplay, setScenario, setLastReplay } = useStore();
  const caps = core?.manifest.capabilities.complete_replay ?? {};
  const available = METHODS.filter((m) => caps[m]?.available);
  const [method, setMethod] = useState<MethodVersion | null>(available[0] ?? null);
  const active = method && caps[method]?.available ? method : available[0] ?? null;
  const bundle = active ? replays[active] : undefined;
  const snapMethod = active && core ? core.snapshot.methods[active] : undefined;
  const native = snapMethod?.policy;
  const [acceptText, setAcceptText] = useState('');
  const [reviewText, setReviewText] = useState('');
  const [gapText, setGapText] = useState('');
  const [result, setResult] = useState<{ method: MethodVersion; policy: Policy; result: EvaluateResult; ms: number } | null>(null);
  const [floorRun, setFloorRun] = useState<ReturnType<typeof floorSweep> | null>(null);
  const [acceptRun, setAcceptRun] = useState<ReturnType<typeof acceptSweep> | null>(null);

  useEffect(() => {
    if (active) ensureReplay(active);
  }, [active, ensureReplay]);
  useEffect(() => {
    if (native) {
      setAcceptText(String(native.accept_min));
      setReviewText(String(native.review_min));
      setGapText(String(native.ambiguity_gap));
      setResult(null);
      setFloorRun(null);
      setAcceptRun(null);
    }
  }, [native]);

  const parsed = useMemo(() => parsePolicy(acceptText, reviewText, gapText), [acceptText, reviewText, gapText]);
  if (!core) return null;
  const rowsReady = bundle && bundle.status === 'ready' ? bundle.data : null;
  const isNative = (p: Policy) => native !== undefined && p.accept_min === native.accept_min && p.review_min === native.review_min && p.ambiguity_gap === native.ambiguity_gap;

  const run = () => {
    if (!rowsReady || !parsed.policy || !active) return;
    const t0 = performance.now();
    const r = evaluate(rowsReady.rows, parsed.policy);
    const ms = performance.now() - t0;
    setResult({ method: active, policy: parsed.policy, result: r, ms });
    setFloorRun(null);
    setAcceptRun(null);
    setLastReplay({ scenario_id: scenarioId({ kind: 'replay', method: active, policy: parsed.policy }), method: active, result: r });
  };

  const checks = result && snapMethod ? reconcile(result.result, snapMethod) : [];
  const nativeRun = result ? isNative(result.policy) : false;
  const allEqual = checks.length > 0 && checks.every((c) => c.equal);
  const floors = snapMethod ? [...snapMethod.review_floor.points.map((p) => p.floor), ...snapMethod.review_floor.floors_omitted_at_or_above_accept_min].sort((a, b) => a - b) : [];
  const thresholds = snapMethod ? snapMethod.legacy_threshold_sweep.points.map((p) => p.threshold) : [];

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Complete policy replay</h2>
      <p className="note">
        Re-apply a policy to every test-fold A record of a method's replay bundle with the same engine the Python evaluator uses. Browsing test-fold scenarios does not validate a new policy; nothing here refits or selects a
        champion.
      </p>
      <div className="controls">
        <label>
          method
          <select value={active ?? ''} data-testid="replay-method" onChange={(e) => setMethod(e.target.value as MethodVersion)}>
            {METHODS.map((m) => (
              <option key={m} value={m} disabled={!caps[m]?.available}>
                {m}
                {caps[m]?.available ? '' : ' (unavailable)'}
              </option>
            ))}
          </select>
        </label>
      </div>
      {METHODS.filter((m) => !caps[m]?.available).map((m) => (
        <div className="notice" key={m} data-testid={`replay-unavailable-${m}`}>
          <MethodName method={m} />: {caps[m]?.note ?? 'complete replay is not declared in the manifest'}
        </div>
      ))}
      {!active ? <p>No method has a complete replay bundle in this export.</p> : null}
      {active && bundle?.status === 'loading' ? <Loading what={`the ${active} replay bundle (decompressing in the browser)`} /> : null}
      {active && bundle?.status === 'error' ? (
        bundle.error.kind === 'unsupported' ? (
          <div className="notice" role="alert" data-testid="replay-unsupported">
            complete replay needs a browser with DecompressionStream; every other view keeps working.
          </div>
        ) : (
          <ErrorState error={bundle.error} />
        )
      ) : null}

      {active && rowsReady && snapMethod ? (
        <>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Bundle: {active}</h3>
            <KeyValue
              rows={[
                ['decision value kind', scoreKindLabel(rowsReady.meta.decision_value_kind)],
                ['rows loaded', fmtInt(rowsReady.rows.length)],
                ['native policy', `accept_min ${fmtNum(rowsReady.meta.native_policy.accept_min)}, review_min ${fmtNum(rowsReady.meta.native_policy.review_min)}, ambiguity_gap ${fmtNum(rowsReady.meta.native_policy.ambiguity_gap)}`],
                ['note', rowsReady.meta.note],
              ]}
            />
            <details>
              <summary>Completeness proof and inputs</summary>
              <KeyValue
                rows={[
                  ['A records expected', fmtInt(rowsReady.meta.completeness.a_records_expected)],
                  ['A records in file', fmtInt(rowsReady.meta.completeness.a_records_in_file)],
                  ['with candidates', fmtInt(rowsReady.meta.completeness.with_candidates)],
                  ['without candidates', fmtInt(rowsReady.meta.completeness.without_candidates)],
                  ['labelled', fmtInt(rowsReady.meta.completeness.labelled)],
                  ['labelled reachable', fmtInt(rowsReady.meta.completeness.labelled_reachable)],
                  ['conserved', rowsReady.meta.completeness.conserved ? 'yes' : 'no'],
                  ['a_id order sha256', <code className="wrap">{rowsReady.meta.a_id_order_sha256}</code>],
                  ['reconciled to evaluation artifact (export time)', `${rowsReady.meta.reconciliation.all_equal ? 'all equal' : 'NOT all equal'} (${rowsReady.meta.reconciliation.eval_artifact})`],
                  ['floor sweep reconciliation (export time)', `${rowsReady.meta.floor_sweep_reconciliation.all_equal ? 'all equal' : 'NOT all equal'}, ${fmtInt(rowsReady.meta.floor_sweep_reconciliation.points_compared)} points`],
                ]}
              />
              <table>
                <thead>
                  <tr>
                    <th className="left">input</th>
                    <th className="left">role</th>
                    <th className="left">sha256</th>
                  </tr>
                </thead>
                <tbody>
                  {rowsReady.meta.inputs.map((i) => (
                    <tr key={i.path}>
                      <td className="mono small">{i.path}</td>
                      <td className="small">{i.role}</td>
                      <td className="mono small wrap">{i.sha256}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
            <details>
              <summary>Legacy-sweep divergence (from the replay metadata)</summary>
              <p className="small">{rowsReady.meta.legacy_sweep_divergence.note}</p>
              <p className="small" data-testid="legacy-divergence">
                thresholds differing: {fmtInt(rowsReady.meta.legacy_sweep_divergence.thresholds_differing)}; max accepts difference: {fmtInt(rowsReady.meta.legacy_sweep_divergence.max_accepts_difference)}
              </p>
              <table>
                <thead>
                  <tr>
                    <th>threshold</th>
                    <th>legacy accepts</th>
                    <th>corrected accepts</th>
                    <th>legacy queue</th>
                    <th>corrected queue</th>
                    <th className="left">legacy matches artifact</th>
                  </tr>
                </thead>
                <tbody>
                  {rowsReady.meta.legacy_sweep_divergence.points.map((p) => (
                    <tr key={p.threshold}>
                      <td>{fmtNum(p.threshold)}</td>
                      <td>{fmtInt(p.legacy_accepts)}</td>
                      <td>{fmtInt(p.corrected_accepts)}</td>
                      <td>{fmtInt(p.legacy_review_queue)}</td>
                      <td>{fmtInt(p.corrected_review_queue)}</td>
                      <td className="left">{p.legacy_matches_artifact ? 'yes' : 'no'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Policy to replay</h3>
            <div className="controls">
              <label>
                accept_min
                <input type="number" min="0" max="1" step="any" inputMode="decimal" value={acceptText} onChange={(e) => setAcceptText(e.target.value)} data-testid="replay-accept" />
              </label>
              <label>
                review_min
                <input type="number" min="0" max="1" step="any" inputMode="decimal" value={reviewText} onChange={(e) => setReviewText(e.target.value)} data-testid="replay-review" />
              </label>
              <label>
                ambiguity_gap
                <input type="number" min="0" max="1" step="any" inputMode="decimal" value={gapText} onChange={(e) => setGapText(e.target.value)} data-testid="replay-gap" />
              </label>
              <button type="button" className="primary" disabled={!parsed.policy} onClick={run} data-testid="replay-run">
                Run replay
              </button>
              <button
                type="button"
                onClick={() => {
                  setAcceptText(String(snapMethod.policy.accept_min));
                  setReviewText(String(snapMethod.policy.review_min));
                  setGapText(String(snapMethod.policy.ambiguity_gap));
                }}
              >
                reset to native
              </button>
            </div>
            {parsed.message ? (
              <p className="bad-text small" role="alert" data-testid="replay-invalid">
                {parsed.message} (rules: finite numbers, 0 ≤ review_min ≤ accept_min ≤ 1, 0 ≤ ambiguity_gap ≤ 1)
              </p>
            ) : null}
          </div>

          {result && result.method === active ? (
            <>
              <div className="panel" data-testid="replay-result">
                <h3 style={{ marginTop: 0 }}>
                  Result at accept_min {fmtNum(result.policy.accept_min)}, review_min {fmtNum(result.policy.review_min)}, ambiguity_gap {fmtNum(result.policy.ambiguity_gap)}{' '}
                  <span className="muted small">({fmtInt(result.result.test_a)} rows in {result.ms.toFixed(0)} ms)</span>
                </h3>
                {nativeRun ? (
                  allEqual ? (
                    <p className="ok-text" data-testid="reconcile-ok">
                      reconciles to the frozen evaluation artifact (native policy; every listed key equal)
                    </p>
                  ) : (
                    <p className="bad-text" role="alert" data-testid="reconcile-diff">
                      native policy but these keys differ from the evaluation artifact (they should not): {checks.filter((c) => !c.equal).map((c) => c.key).join(', ')}
                    </p>
                  )
                ) : (
                  <p className="small muted">Not the native policy: the baseline column shows the recorded values for comparison only.</p>
                )}
                <table>
                  <thead>
                    <tr>
                      <th className="left">key</th>
                      <th>replay</th>
                      <th>native baseline (snapshot)</th>
                      <th className="left">numerator / denominator (replay)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {checks.map((c) => {
                      const r = result.result;
                      const frac: Record<string, string> = {
                        precision: `${fmtInt(r.at_auto_accept.correct)} / ${fmtInt(r.at_auto_accept.accepted)} (${r.denominators.precision})`,
                        recall_labelled: `${fmtInt(r.at_auto_accept.correct)} / ${fmtInt(r.labelled_a_reachable)} (${r.denominators.recall_labelled})`,
                        recall_overall: `${fmtInt(r.at_auto_accept.correct)} / ${fmtInt(r.labelled_a)} (${r.denominators.recall_overall})`,
                        coverage: `${fmtInt(r.accepted_all)} / ${fmtInt(r.test_a)} (${r.denominators.coverage})`,
                        unverified_accepts_share: `${fmtInt(r.unverified_accepts.count)} / ${fmtInt(r.accepted_all)} (${r.denominators.share_of_accepts})`,
                        pair_completeness_test: `${fmtInt(r.labelled_a_reachable)} / ${fmtInt(r.labelled_a)}`,
                        precision_or_review: `${fmtInt(r.at_auto_accept_or_review.correct)} / ${fmtInt(r.at_auto_accept_or_review.accepted)}`,
                        recall_labelled_or_review: `${fmtInt(r.at_auto_accept_or_review.correct)} / ${fmtInt(r.labelled_a_reachable)}`,
                        f1: 'from the rounded precision and recall_labelled',
                      };
                      const isRatio = c.key in frac;
                      const show = (v: number | null) => (v === null ? 'unavailable (denominator 0)' : isRatio ? fmtRatio(v) : fmtInt(v));
                      return (
                        <tr key={c.key}>
                          <td className="mono">{c.key}</td>
                          <td>{show(c.replay)}</td>
                          <td>{show(c.artifact)}</td>
                          <td className="left small">{frac[c.key] ?? ''}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="small" data-testid="tier-counts">
                  Tier counts: {tierLabel('auto_accept')} {fmtInt(result.result.tier_counts.auto_accept)}, review {fmtInt(result.result.tier_counts.review)}, reject {fmtInt(result.result.tier_counts.reject)}; sum{' '}
                  {fmtInt(result.result.tier_counts.auto_accept + result.result.tier_counts.review + result.result.tier_counts.reject)} = population {fmtInt(result.result.test_a)}. No-candidate A records:{' '}
                  {fmtInt(result.result.no_candidate_a)} (reject with reason no_candidate). Ambiguous non-reject decisions: {fmtInt(result.result.ambiguity_rule.ambiguous_non_reject)}.
                </p>
                <div className="button-row">
                  <button type="button" onClick={() => setScenario({ kind: 'replay', method: active, policy: result.policy })} data-testid="replay-use-scenario">
                    use this replay as the current scenario ({scenarioId({ kind: 'replay', method: active, policy: result.policy })})
                  </button>
                </div>
              </div>

              <div className="panel">
                <h3 style={{ marginTop: 0 }}>Corrected sweeps (on demand)</h3>
                <div className="button-row">
                  <button type="button" onClick={() => setFloorRun(floorSweep(rowsReady.rows, { accept_min: result.policy.accept_min, ambiguity_gap: result.policy.ambiguity_gap, floors }))} data-testid="run-floor-sweep">
                    floor sweep at accept_min {fmtNum(result.policy.accept_min)} over the exported floors
                  </button>
                  <button type="button" onClick={() => setAcceptRun(acceptSweep(rowsReady.rows, { review_min: result.policy.review_min, ambiguity_gap: result.policy.ambiguity_gap, thresholds }))} data-testid="run-accept-sweep">
                    accept sweep at review_min {fmtNum(result.policy.review_min)} over the legacy thresholds
                  </button>
                </div>
                {floorRun ? (
                  <>
                    <table data-testid="floor-sweep-table">
                      <thead>
                        <tr>
                          <th>floor</th>
                          <th>queue (floor)</th>
                          <th>queue (ambiguity)</th>
                          <th>queue (total)</th>
                          <th>share of test A</th>
                          <th>recall with review</th>
                        </tr>
                      </thead>
                      <tbody>
                        {floorRun.map((p) => (
                          <tr key={p.floor}>
                            <td>{fmtNum(p.floor)}</td>
                            <td>{fmtInt(p.queue_floor)}</td>
                            <td>{fmtInt(p.queue_ambiguity)}</td>
                            <td>{fmtInt(p.queue_total)}</td>
                            <td>{fmtRatio(p.queue_share_of_test_a)}</td>
                            <td>{fmtRatio(p.recall_with_review)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <LineChart title="Corrected floor sweep: recall with review against the review floor" series={[{ name: active, method: active, points: floorRun.map((p) => ({ x: p.floor, y: p.recall_with_review })) }]} xLabel="review floor" yLabel="recall with review" />
                  </>
                ) : null}
                {acceptRun ? (
                  <>
                    <table data-testid="accept-sweep-table">
                      <thead>
                        <tr>
                          <th>threshold</th>
                          <th>accepts</th>
                          <th>queue (floor)</th>
                          <th>queue (ambiguity)</th>
                          <th>review queue</th>
                          <th>labelled precision</th>
                          <th>labelled accepts</th>
                          <th>labelled false accepts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {acceptRun.map((p) => (
                          <tr key={p.threshold}>
                            <td>{fmtNum(p.threshold)}</td>
                            <td>{fmtInt(p.accepts)}</td>
                            <td>{fmtInt(p.queue_floor)}</td>
                            <td>{fmtInt(p.queue_ambiguity)}</td>
                            <td>{fmtInt(p.review_queue)}</td>
                            <td>{p.precision_labelled === null ? 'unavailable (denominator 0)' : fmtRatio(p.precision_labelled)}</td>
                            <td>{fmtInt(p.labelled_accepts)}</td>
                            <td>{fmtInt(p.labelled_false_accepts)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <LineChart title="Corrected accept sweep: review queue against the accept threshold" series={[{ name: active, method: active, points: acceptRun.map((p) => ({ x: p.threshold, y: p.review_queue })) }]} xLabel="accept threshold" yLabel="review queue" yFormat={(v) => fmtInt(Math.round(v))} />
                  </>
                ) : null}
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}
