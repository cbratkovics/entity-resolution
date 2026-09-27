/** Choose the real scenario (method + native or supported floor) that the ledger and receipt bind to. */
import type { LabSnapshot } from '../lib/contracts';
import { floorPoints, methodOrder } from '../lib/evidence';
import { fmtInt, fmtNum } from '../lib/format';
import { scenarioId, type RealScenario } from '../lib/scenario';
import { useStore } from '../store';

export function ScenarioPicker({ snapshot }: { snapshot: LabSnapshot }) {
  const { scenario, setScenario } = useStore();
  const method = snapshot.methods[scenario.method];
  const floorValue = scenario.kind === 'supported_floor' ? String(scenario.floor) : 'native';
  return (
    <div className="controls" data-testid="scenario-picker">
      <label>
        method scenario
        <select
          value={scenario.method}
          data-testid="scenario-method"
          onChange={(e) => {
            const m = e.target.value;
            const next: RealScenario = { kind: 'native', method: m as RealScenario['method'] };
            setScenario(next);
          }}
        >
          {methodOrder(snapshot).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label>
        control
        <select
          value={scenario.kind === 'replay' ? 'replay' : floorValue}
          data-testid="scenario-control"
          onChange={(e) => {
            const v = e.target.value;
            if (v === 'native') setScenario({ kind: 'native', method: scenario.method });
            else if (v !== 'replay') setScenario({ kind: 'supported_floor', method: scenario.method, floor: Number(v) });
          }}
        >
          <option value="native">native (recorded policy)</option>
          {method
            ? floorPoints(method).map((p) => (
                <option key={p.floor} value={String(p.floor)}>
                  supported floor {fmtNum(p.floor)} (queue {fmtInt(p.queue_total)})
                </option>
              ))
            : null}
          {scenario.kind === 'replay' ? <option value="replay">replay (set on the Replay tab)</option> : null}
        </select>
      </label>
      <span className="small muted">
        scenario id <code data-testid="scenario-id">{scenarioId(scenario)}</code>
      </span>
    </div>
  );
}
