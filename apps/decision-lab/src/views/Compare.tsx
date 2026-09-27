import { useEffect, useMemo, useState } from 'react';
import { BarChart } from '../components/charts';
import { FrozenBadge, MethodName, Why } from '../components/common';
import type { LabSnapshot, MethodVersion, SnapshotMethod } from '../lib/contracts';
import { assumedEffort, evidenceSays, feasibleFloors, findFloorPoint, floorPoints, methodOrder, nativeFloorPoint, whatStayedFixed } from '../lib/evidence';
import { fmtInt, fmtMetric, fmtNum, fmtRatio, metricFraction, scoreKindLabel, shortCommit } from '../lib/format';
import { DECISION_QUESTION } from '../lib/receipt';
import type { Route } from '../lib/router';
import { buildHash } from '../lib/router';
import { parseCompareQuery, serialiseCompareQuery, type CompareQuery } from '../lib/scenario';
import { useCore, useStore } from '../store';

function MetricCell({ snapshot, method, metricKey }: { snapshot: LabSnapshot; method: SnapshotMethod; metricKey: string }) {
  const m = method.metrics[metricKey];
  const def = snapshot.metric_definitions[metricKey];
  return (
    <td>
      <span>{fmtMetric(m, def?.unit ?? 'ratio')}</span>{' '}
      <Why>
        <strong>{def?.display_name ?? metricKey}</strong>
        <div>{def?.definition}</div>
        <div>
          numerator: {def?.numerator}; denominator: {def?.denominator}
        </div>
        <div>values: {metricFraction(m)}</div>
        <div className="mono wrap">source: {m?.source_key}</div>
      </Why>
    </td>
  );
}

function CountCell({ method, countKey, label }: { method: SnapshotMethod; countKey: string; label: string }) {
  const c = method.counts[countKey];
  return (
    <td>
      {c ? fmtInt(c.value) : 'unavailable'}{' '}
      <Why>
        <strong>{label}</strong>
        <div className="mono wrap">source: {c?.source_key}</div>
      </Why>
    </td>
  );
}

export function CompareView({ route }: { route: Route }) {
  const core = useCore();
  const { setScenario } = useStore();
  const query = useMemo(() => parseCompareQuery(route.params), [route.params]);
  const snapshot = core?.snapshot;
  const methods = useMemo(() => (snapshot ? methodOrder(snapshot) : []), [snapshot]);
  const method: MethodVersion | null = query.method && snapshot && snapshot.methods[query.method] ? query.method : methods[0] ?? null;
  const mBlock = method && snapshot ? snapshot.methods[method] : undefined;
  const floorSelected = mBlock && query.floor !== null && findFloorPoint(mBlock, query.floor) ? query.floor : null;
  const [minutesText, setMinutesText] = useState(query.minutes === null ? '' : String(query.minutes));
  const [budgetText, setBudgetText] = useState(query.budget === null ? '' : String(query.budget));

  useEffect(() => {
    if (!method) return;
    if (floorSelected !== null) setScenario({ kind: 'supported_floor', method, floor: floorSelected });
    else setScenario({ kind: 'native', method });
  }, [method, floorSelected, setScenario]);

  const navigate = (next: Partial<CompareQuery>) => {
    const q: CompareQuery = { method, floor: floorSelected, budget: query.budget, minutes: query.minutes, ...next };
    window.location.hash = buildHash('compare', { query: serialiseCompareQuery(q) });
  };

  if (!core || !snapshot || !method || !mBlock) return null;
  const manifest = core.manifest;
  const says = evidenceSays(snapshot);
  const selectedPoint = floorSelected !== null ? findFloorPoint(mBlock, floorSelected) : null;
  const nativePoint = nativeFloorPoint(mBlock);
  const budget = query.budget;
  const feasible = budget !== null ? feasibleFloors(snapshot, budget) : [];
  const effort = selectedPoint ? assumedEffort(selectedPoint.queue_total, query.minutes) : null;
  const bar = (key: string, title: string) => (
    <BarChart
      title={title}
      data={methods.map((name) => {
        const mm = snapshot.methods[name];
        const met = mm?.metrics[key];
        const ok = met && met.value !== null && met.denominator !== 0;
        return { label: name, method: name, value: ok ? met.value : null, text: ok ? fmtRatio(met.value) : 'unavailable (denominator 0)' };
      })}
    />
  );

  return (
    <>
      <section aria-labelledby="q-heading">
        <h2 id="q-heading" style={{ marginTop: 0 }}>
          {DECISION_QUESTION}
        </h2>
        <p className="small" data-testid="identity-line">
          snapshot <code data-testid="snapshot-id">{snapshot.snapshot_id}</code> · evaluation code commit <code>{shortCommit(snapshot.evidence.evaluation_code_commit)}</code> · feature version{' '}
          <code>{snapshot.evidence.feature_version}</code> · generated {snapshot.evidence.evaluation_generated_at_utc} · <FrozenBadge />
        </p>
        <p className="note">
          Test fold, one decision per A record ({fmtInt(snapshot.population.a_records)} A records, {fmtInt(snapshot.population.labelled_a)} labelled,{' '}
          {fmtInt(snapshot.population.labelled_a_reachable)} labelled with truth reachable after blocking). Every figure is read from the exported snapshot; nothing is typed into the app.
        </p>
      </section>

      <section aria-labelledby="methods-heading">
        <h2 id="methods-heading">Methods at their recorded policies</h2>
        <div className="panel">
          <table data-testid="methods-table">
            <thead>
              <tr>
                <th>method</th>
                <th className="left">recorded policy</th>
                <th>labelled precision</th>
                <th>recall (reachable labelled)</th>
                <th>recall (overall labelled)</th>
                <th>F1</th>
                <th>coverage</th>
                <th>unverified accepts</th>
                <th>review queue</th>
                <th>moved by ambiguity</th>
              </tr>
            </thead>
            <tbody>
              {methods.map((name) => {
                const mm = snapshot.methods[name];
                if (!mm) return null;
                const share = mm.metrics.unverified_accepts_share;
                return (
                  <tr key={name} data-testid={`method-row-${name}`}>
                    <td>
                      <MethodName method={name} />
                    </td>
                    <td className="left small">
                      accept_min {fmtNum(mm.policy.accept_min)}, review_min {fmtNum(mm.policy.review_min)}, ambiguity_gap {fmtNum(mm.policy.ambiguity_gap)}
                      <br />
                      <span className="muted">{scoreKindLabel(mm.score_kind)}</span>{' '}
                      <Why>
                        <div>{mm.definition}</div>
                        <div className="mono wrap">policy source: {mm.policy_source}</div>
                      </Why>
                    </td>
                    <MetricCell snapshot={snapshot} method={mm} metricKey="precision" />
                    <MetricCell snapshot={snapshot} method={mm} metricKey="recall_labelled" />
                    <MetricCell snapshot={snapshot} method={mm} metricKey="recall_overall" />
                    <MetricCell snapshot={snapshot} method={mm} metricKey="f1" />
                    <MetricCell snapshot={snapshot} method={mm} metricKey="coverage" />
                    <td>
                      {fmtInt(mm.counts.unverified_accepts?.value)} ({fmtMetric(share, 'share')} of accepts){' '}
                      <Why>
                        <div>{snapshot.metric_definitions.unverified_accepts_share?.definition}</div>
                        <div>values: {metricFraction(share)}</div>
                        <div className="mono wrap">source: {mm.counts.unverified_accepts?.source_key}</div>
                      </Why>
                    </td>
                    <CountCell method={mm} countKey="review_queue" label="review queue: A records in the review tier (floor plus ambiguity demotions)" />
                    <CountCell method={mm} countKey="decisions_moved_to_review" label="decisions the ambiguity rule moved from auto-accept to review" />
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="note">
            Precision, recall and F1 are over labelled A records; coverage counts every test-fold A record; unverified accepts are auto-accepts on unlabelled A records, counted by coverage and never by the accuracy
            metrics. Metrics with a zero denominator render as unavailable.
          </p>
        </div>
        <div className="grid">
          {bar('f1', 'F1 at the recorded policy')}
          {bar('precision', 'Labelled precision at the recorded policy')}
          {bar('recall_labelled', 'Reachable-labelled recall at the recorded policy')}
          {bar('coverage', 'Coverage at the recorded policy')}
        </div>
      </section>

      <section aria-labelledby="says-heading">
        <h2 id="says-heading">What the evidence says</h2>
        <div className="panel" data-testid="evidence-says">
          <ul>
            {says.map((s) => (
              <li key={s.text}>
                {s.text}{' '}
                <Why label="sources">
                  <ul className="mono small wrap">
                    {s.source_keys.map((k) => (
                      <li key={k}>{k}</li>
                    ))}
                  </ul>
                </Why>
              </li>
            ))}
          </ul>
          <p className="note">Computed by fixed rules over the snapshot values; no method is named as a winner in the app's source.</p>
        </div>
      </section>

      <section aria-labelledby="budget-heading">
        <h2 id="budget-heading">Review budget: supported floor control</h2>
        <div className="panel">
          <div className="controls">
            <label>
              method
              <select value={method} data-testid="floor-method" onChange={(e) => navigate({ method: e.target.value as MethodVersion, floor: null })}>
                {methods.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              review floor (exported points only)
              <select value={floorSelected === null ? 'native' : String(floorSelected)} data-testid="floor-select" onChange={(e) => navigate({ floor: e.target.value === 'native' ? null : Number(e.target.value) })}>
                <option value="native">original benchmark row (review_min {fmtNum(mBlock.policy.review_min)})</option>
                {floorPoints(mBlock).map((p) => (
                  <option key={p.floor} value={String(p.floor)}>
                    historical scenario at recorded settings: floor {fmtNum(p.floor)}
                  </option>
                ))}
                {mBlock.review_floor.floors_omitted_at_or_above_accept_min.map((f) => (
                  <option key={`omitted-${f}`} value={`omitted-${f}`} disabled>
                    floor {fmtNum(f)}: omitted, at or above accept_min {fmtNum(mBlock.review_floor.accept_min)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              minutes per review (optional, assumed effort)
              <input
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={minutesText}
                data-testid="minutes-input"
                onChange={(e) => setMinutesText(e.target.value)}
                onBlur={() => {
                  const v = Number(minutesText);
                  navigate({ minutes: minutesText !== '' && Number.isFinite(v) && v >= 0 ? v : null });
                }}
              />
            </label>
          </div>
          <p className="note">{mBlock.review_floor.note}</p>
          <table data-testid="floor-table">
            <thead>
              <tr>
                <th className="left">row</th>
                <th>floor</th>
                <th>queue (floor)</th>
                <th>queue (ambiguity)</th>
                <th>queue (total)</th>
                <th>share of test A</th>
                <th>recall with review</th>
              </tr>
            </thead>
            <tbody>
              <tr className="baseline" data-testid="baseline-row">
                <td>original benchmark row (never editable)</td>
                <td>{fmtNum(mBlock.policy.review_min)}</td>
                <td>{nativePoint ? fmtInt(nativePoint.queue_floor) : fmtInt((mBlock.counts.review_queue?.value ?? 0) - (mBlock.counts.decisions_moved_to_review?.value ?? 0))}</td>
                <td>{fmtInt(nativePoint ? nativePoint.queue_ambiguity : mBlock.counts.decisions_moved_to_review?.value)}</td>
                <td>{fmtInt(nativePoint ? nativePoint.queue_total : mBlock.counts.review_queue?.value)}</td>
                <td>{nativePoint ? fmtRatio(nativePoint.queue_share_of_test_a) : 'not exported'}</td>
                <td>{nativePoint ? fmtRatio(nativePoint.recall_with_review) : fmtMetric(mBlock.metrics.recall_labelled_or_review)}</td>
              </tr>
              {selectedPoint ? (
                <tr data-testid="selected-floor-row">
                  <td>historical scenario at recorded settings</td>
                  <td>{fmtNum(selectedPoint.floor)}</td>
                  <td data-testid="sel-queue-floor">{fmtInt(selectedPoint.queue_floor)}</td>
                  <td data-testid="sel-queue-ambiguity">{fmtInt(selectedPoint.queue_ambiguity)}</td>
                  <td data-testid="sel-queue-total">{fmtInt(selectedPoint.queue_total)}</td>
                  <td>{fmtRatio(selectedPoint.queue_share_of_test_a)}</td>
                  <td data-testid="sel-recall-review">{fmtRatio(selectedPoint.recall_with_review)}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <p className="small" data-testid="fixed-text">
            What stayed fixed: {whatStayedFixed(mBlock)}.
          </p>
          <p className="note">
            recall with review is an upper bound if every queued reachable record were resolved correctly; not observed reviewer performance. Source: <code>{mBlock.review_floor.source_key}</code>.
          </p>
          {selectedPoint && effort ? (
            <p className="small" data-testid="assumed-effort">
              Assumed effort at {fmtNum(query.minutes)} minutes per review: {fmtInt(Math.round(effort.minutes))} minutes ({fmtRatio(effort.hours, 1)} hours) for {fmtInt(selectedPoint.queue_total)} queued records. An assumption, not a
              measured cost, saving or return.
            </p>
          ) : null}
        </div>

        <h3>Queue budget</h3>
        <div className="panel">
          <div className="controls">
            <label>
              maximum review queue (integer)
              <input
                type="number"
                min="0"
                step="1"
                inputMode="numeric"
                value={budgetText}
                data-testid="budget-input"
                onChange={(e) => setBudgetText(e.target.value)}
                onBlur={() => navigate({ budget: /^\d{1,9}$/.test(budgetText) ? Number(budgetText) : null })}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') navigate({ budget: /^\d{1,9}$/.test(budgetText) ? Number(budgetText) : null });
                }}
              />
            </label>
            <button type="button" onClick={() => navigate({ budget: /^\d{1,9}$/.test(budgetText) ? Number(budgetText) : null })} data-testid="budget-apply">
              apply budget
            </button>
          </div>
          {budget === null ? (
            <p className="note">Enter a budget to list the exported floor points whose total queue fits it. Nothing is interpolated between exported points.</p>
          ) : feasible.length === 0 ? (
            <p data-testid="budget-result">no supported setting meets this budget ({fmtInt(budget)})</p>
          ) : (
            <div data-testid="budget-result">
              <p className="small">Exported floor points with queue_total at most {fmtInt(budget)} (largest feasible floor first per method):</p>
              <table data-testid="feasible-table">
                <thead>
                  <tr>
                    <th>method</th>
                    <th>floor</th>
                    <th>queue (total)</th>
                    <th>recall with review</th>
                    <th className="left">use</th>
                  </tr>
                </thead>
                <tbody>
                  {feasible.map((f) => (
                    <tr key={`${f.method}-${f.point.floor}`}>
                      <td>
                        <MethodName method={f.method} />
                      </td>
                      <td>{fmtNum(f.point.floor)}</td>
                      <td>{fmtInt(f.point.queue_total)}</td>
                      <td>{fmtRatio(f.point.recall_with_review)}</td>
                      <td className="left">
                        <button type="button" onClick={() => navigate({ method: f.method, floor: f.point.floor })}>
                          select
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="legacy-heading">
        <details>
          <summary id="legacy-heading">
            <strong>Legacy cost curve (snapshot calculation)</strong> for {method}: not a faithful arbitrary-policy replay
          </summary>
          <div className="panel">
            <p className="note">{mBlock.legacy_threshold_sweep.note}</p>
            <p className="note">
              Cost expression assumption: review rows + expected false accepts × ratio, where expected false accepts extrapolate labelled precision to all accepts, and missed matches are not costed. Recorded review_min{' '}
              {fmtNum(mBlock.legacy_threshold_sweep.review_min)}; chosen accept threshold {fmtNum(mBlock.legacy_threshold_sweep.chosen_accept_threshold)}; ratios{' '}
              {mBlock.legacy_threshold_sweep.false_accept_cost_ratios.map(fmtNum).join(', ')}. Source: <code>{mBlock.legacy_threshold_sweep.source_key}</code>.
            </p>
            <table>
              <thead>
                <tr>
                  <th>threshold</th>
                  <th>accepts</th>
                  <th>queue (floor)</th>
                  <th>queue (ambiguity)</th>
                  <th>review queue</th>
                  <th>labelled precision</th>
                  <th>expected false accepts</th>
                  {mBlock.legacy_threshold_sweep.false_accept_cost_ratios.map((r) => (
                    <th key={r}>total cost × {fmtNum(r)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mBlock.legacy_threshold_sweep.points.map((p) => (
                  <tr key={p.threshold} className={p.threshold === mBlock.legacy_threshold_sweep.chosen_accept_threshold ? 'baseline' : undefined}>
                    <td>{fmtNum(p.threshold)}</td>
                    <td>{fmtInt(p.accepts)}</td>
                    <td>{fmtInt(p.queue_floor)}</td>
                    <td>{fmtInt(p.queue_ambiguity)}</td>
                    <td>{fmtInt(p.review_queue)}</td>
                    <td>{fmtRatio(p.precision_labelled)}</td>
                    <td>{fmtRatio(p.expected_false_accepts, 2)}</td>
                    {mBlock.legacy_threshold_sweep.false_accept_cost_ratios.map((r) => (
                      <td key={r}>{fmtRatio(p.total_cost[String(r)] ?? null, 2)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <p className="note">
        Capabilities: {manifest.capabilities.evidence_comparison.note} {manifest.capabilities.supported_floor_control.note}
      </p>
    </>
  );
}
