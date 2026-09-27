import type { LabCase, MethodVersion, ReviewEvent } from '../lib/contracts';
import { CONSEQUENCE_DISCLAIMER, consequences } from '../lib/consequences';
import { fmtInt } from '../lib/format';

export function ConsequencesPanel({
  events,
  scenarioId,
  method,
  caseSet,
  setLabel,
}: {
  events: readonly ReviewEvent[];
  scenarioId: string;
  method: MethodVersion;
  caseSet: readonly LabCase[];
  setLabel: string;
}) {
  const c = consequences(events, scenarioId, method, caseSet);
  return (
    <div className="panel" data-testid="consequences">
      <h3 style={{ marginTop: 0 }}>Consequences for {setLabel}</h3>
      <p className="small muted">scenario {scenarioId}; baseline chosen B from {method}</p>
      <table>
        <tbody>
          <tr>
            <td>cases in the set</td>
            <td data-testid="cq-set">{fmtInt(c.cases_in_set)}</td>
          </tr>
          <tr>
            <td>cases with events</td>
            <td data-testid="cq-with-events">{fmtInt(c.cases_with_events)}</td>
          </tr>
          <tr>
            <td>effective accepted mappings</td>
            <td data-testid="cq-accepted">{fmtInt(c.accepted_mappings)}</td>
          </tr>
          <tr>
            <td>deferred</td>
            <td data-testid="cq-deferred">{fmtInt(c.deferred)}</td>
          </tr>
          <tr>
            <td>rejected candidates</td>
            <td data-testid="cq-rejected">{fmtInt(c.rejected_candidates)}</td>
          </tr>
          <tr>
            <td>changed mappings vs the baseline chosen B</td>
            <td data-testid="cq-changed">{fmtInt(c.changed_vs_baseline)}</td>
          </tr>
          <tr>
            <td>unresolved evidence</td>
            <td data-testid="cq-unresolved">{fmtInt(c.unresolved)}</td>
          </tr>
        </tbody>
      </table>
      {c.accepted_list.length ? (
        <details>
          <summary className="small">accepted mappings</summary>
          <table>
            <thead>
              <tr>
                <th>a_id</th>
                <th>accepted b_id</th>
                <th>baseline b_id</th>
              </tr>
            </thead>
            <tbody>
              {c.accepted_list.map((r) => (
                <tr key={r.a_id}>
                  <td className="mono">{r.a_id}</td>
                  <td className="mono">{r.b_id}</td>
                  <td className="mono">{r.baseline_b_id ?? 'not exported'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      <p className="note">{CONSEQUENCE_DISCLAIMER}</p>
    </div>
  );
}
