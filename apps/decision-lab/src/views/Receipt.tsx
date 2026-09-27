import { useEffect, useMemo, useState } from 'react';
import { ConfirmDialog, ErrorState, KeyValue, Loading } from '../components/common';
import { ConsequencesPanel } from '../components/ConsequencesPanel';
import { ScenarioPicker } from '../components/ScenarioPicker';
import { CHOSEN_ACTIONS, type ChosenAction, type LabReceipt } from '../lib/contracts';
import { casesWithEvents } from '../lib/consequences';
import { downloadJson, readFileText } from '../lib/download';
import { fmtInt, fmtNum } from '../lib/format';
import { exportLedger, type ImportResult } from '../lib/ledger';
import { buildReceipt, DECISION_QUESTION, DEFAULT_ASSUMPTIONS, defaultAlternatives, defaultLimitations, importReceipt, receiptFileName, scenarioObservations, type Observation, type ReceiptDraft, type ReceiptImportResult } from '../lib/receipt';
import { useCore, useStore } from '../store';

export function ReceiptView() {
  const core = useCore();
  const { scenario, scenarioIdText, events, cases, ensureCases, importLedgerText, resetLedger, lastReplay, setStatus } = useStore();
  const [question, setQuestion] = useState(DECISION_QUESTION);
  const [budgetText, setBudgetText] = useState('');
  const [minutesText, setMinutesText] = useState('');
  const [notes, setNotes] = useState('');
  const [userObs, setUserObs] = useState<Observation[]>([]);
  const [obsClaim, setObsClaim] = useState('');
  const [obsValue, setObsValue] = useState('');
  const [obsSource, setObsSource] = useState('');
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [assumptionText, setAssumptionText] = useState('');
  const [alternatives, setAlternatives] = useState<{ option: string; why_not: string }[] | null>(null);
  const [action, setAction] = useState<ChosenAction>('defer');
  const [rationale, setRationale] = useState('');
  const [limitations, setLimitations] = useState<string[]>([]);
  const [limitationText, setLimitationText] = useState('');
  const [preview, setPreview] = useState<LabReceipt | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [receiptImport, setReceiptImport] = useState<ReceiptImportResult | null>(null);
  const [ledgerImport, setLedgerImport] = useState<ImportResult | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [caseSetMode, setCaseSetMode] = useState<'events' | 'all'>('events');

  useEffect(() => {
    ensureCases();
  }, [ensureCases]);
  useEffect(() => {
    // Rebinding to another scenario invalidates the preview and prefilled alternatives.
    setPreview(null);
    setAlternatives(null);
  }, [scenarioIdText]);

  const snapshot = core?.snapshot;
  const manifest = core?.manifest;
  const replayForScenario = scenario.kind === 'replay' && lastReplay && lastReplay.scenario_id === scenarioIdText ? lastReplay.result : null;
  const autoObs = useMemo(() => (snapshot ? scenarioObservations(snapshot, scenario, replayForScenario) : []), [snapshot, scenario, replayForScenario]);
  const alts = alternatives ?? (snapshot ? defaultAlternatives(snapshot, scenario) : []);
  if (!core || !snapshot || !manifest) return null;

  const draft = (): ReceiptDraft => ({
    decision_question: question,
    queue_budget: /^\d{1,9}$/.test(budgetText) ? Number(budgetText) : null,
    review_minutes_per_row: minutesText.trim() !== '' && Number.isFinite(Number(minutesText)) && Number(minutesText) >= 0 ? Number(minutesText) : null,
    notes,
    user_observations: userObs,
    extra_assumptions: assumptions,
    alternatives: alts,
    chosen_action: action,
    rationale,
    extra_limitations: limitations,
  });

  const build = (): LabReceipt | null => {
    try {
      const r = buildReceipt(manifest, snapshot, scenario, draft(), replayForScenario);
      setBuildError(null);
      setPreview(r);
      return r;
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : String(e));
      setPreview(null);
      return null;
    }
  };

  const caseData = cases.status === 'ready' ? cases.data : null;
  const eventCases = caseData ? casesWithEvents(events, scenarioIdText, caseData.cases) : [];
  const caseSet = caseSetMode === 'events' ? eventCases : caseData ? caseData.cases : [];
  const realEvents = events.filter((e) => !e.scenario_id.startsWith('synthetic:'));

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Scenario receipt</h2>
      <p className="note">A policy_scenario receipt records the question, the frozen evidence, the selected controls, the observations with their sources, the assumptions and the chosen action. Sandbox scenarios are refused.</p>
      <ScenarioPicker snapshot={snapshot} />
      {scenario.kind === 'replay' && !replayForScenario ? <p className="notice">The replay scenario has no result in memory; run it on the Replay tab to fill replay-verified observations.</p> : null}

      <div className="panel">
        <div className="field">
          <label htmlFor="rq">decision question</label>
          <textarea id="rq" maxLength={2000} value={question} onChange={(e) => setQuestion(e.target.value)} data-testid="receipt-question" />
        </div>
        <KeyValue
          rows={[
            ['snapshot', <code className="wrap">{manifest.snapshot_id}</code>],
            ['analytical digest', <code className="wrap">{manifest.analytical_digest}</code>],
            ['evaluation code commit', <code className="wrap">{manifest.evidence.evaluation_code_commit}</code>],
            ['feature version', manifest.evidence.feature_version],
            ['population', `${fmtInt(snapshot.population.a_records)} test-fold A records, ${fmtInt(snapshot.population.labelled_a)} labelled`],
            ['method / policy', `${scenario.method}: accept_min ${fmtNum(snapshot.methods[scenario.method]?.policy.accept_min)}, review_min ${fmtNum(snapshot.methods[scenario.method]?.policy.review_min)}, ambiguity_gap ${fmtNum(snapshot.methods[scenario.method]?.policy.ambiguity_gap)} (${snapshot.methods[scenario.method]?.policy_source})`],
            ['selected controls', `${scenario.kind}; scenario ${scenarioIdText}`],
          ]}
        />
        <h3>User constraints</h3>
        <div className="controls">
          <label>
            queue budget (integer, optional)
            <input type="number" min="0" step="1" value={budgetText} onChange={(e) => setBudgetText(e.target.value)} data-testid="receipt-budget" />
          </label>
          <label>
            minutes per row (assumed effort, optional)
            <input type="number" min="0" step="any" value={minutesText} onChange={(e) => setMinutesText(e.target.value)} />
          </label>
        </div>
        <div className="field">
          <label htmlFor="rnotes">notes</label>
          <textarea id="rnotes" maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>

        <h3>Observations</h3>
        <table>
          <thead>
            <tr>
              <th className="left">claim</th>
              <th>value</th>
              <th className="left">source key</th>
              <th className="left">verified by</th>
            </tr>
          </thead>
          <tbody>
            {[...autoObs, ...userObs].map((o, i) => (
              <tr key={`${o.claim}-${i}`}>
                <td className="small">{o.claim}</td>
                <td>{o.value === null ? 'unavailable' : String(o.value)}</td>
                <td className="mono small wrap">{o.source_key}</td>
                <td className="left">{o.verified_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="controls">
          <label>
            add a user observation: claim
            <input type="text" maxLength={500} value={obsClaim} onChange={(e) => setObsClaim(e.target.value)} />
          </label>
          <label>
            value
            <input type="text" maxLength={100} value={obsValue} onChange={(e) => setObsValue(e.target.value)} />
          </label>
          <label>
            source
            <input type="text" maxLength={300} value={obsSource} onChange={(e) => setObsSource(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={!obsClaim.trim()}
            onClick={() => {
              const v = obsValue.trim();
              const num = v !== '' && /^-?\d*\.?\d+([eE][-+]?\d+)?$/.test(v) ? Number(v) : null;
              setUserObs([...userObs, { claim: obsClaim.trim(), value: v === '' ? null : num ?? v, source_key: obsSource.trim() || 'user', verified_by: 'user' }]);
              setObsClaim('');
              setObsValue('');
              setObsSource('');
            }}
          >
            add (verified_by: user)
          </button>
        </div>

        <h3>Assumptions</h3>
        <ul className="small">
          {DEFAULT_ASSUMPTIONS.map((a) => (
            <li key={a}>{a}</li>
          ))}
          {assumptions.map((a, i) => (
            <li key={`${a}-${i}`}>
              {a}{' '}
              <button type="button" className="small" onClick={() => setAssumptions(assumptions.filter((_, j) => j !== i))}>
                remove
              </button>
            </li>
          ))}
        </ul>
        <div className="controls">
          <label>
            add an assumption
            <input type="text" maxLength={500} value={assumptionText} onChange={(e) => setAssumptionText(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={!assumptionText.trim()}
            onClick={() => {
              setAssumptions([...assumptions, assumptionText.trim()]);
              setAssumptionText('');
            }}
          >
            add
          </button>
        </div>

        <h3>Alternatives considered</h3>
        {alts.map((a, i) => (
          <div className="controls" key={`${a.option}-${i}`}>
            <label>
              option
              <input type="text" maxLength={200} value={a.option} onChange={(e) => setAlternatives(alts.map((x, j) => (j === i ? { ...x, option: e.target.value } : x)))} />
            </label>
            <label>
              why not
              <input type="text" maxLength={1000} value={a.why_not} style={{ width: '28em', maxWidth: '100%' }} onChange={(e) => setAlternatives(alts.map((x, j) => (j === i ? { ...x, why_not: e.target.value } : x)))} />
            </label>
            <button type="button" onClick={() => setAlternatives(alts.filter((_, j) => j !== i))}>
              remove
            </button>
          </div>
        ))}
        <button type="button" onClick={() => setAlternatives([...alts, { option: '', why_not: '' }])}>
          add alternative
        </button>

        <h3>Decision</h3>
        <div className="controls">
          <label>
            chosen action
            <select value={action} onChange={(e) => setAction(e.target.value as ChosenAction)} data-testid="receipt-action">
              {CHOSEN_ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field">
          <label htmlFor="rrat">rationale</label>
          <textarea id="rrat" maxLength={4000} value={rationale} onChange={(e) => setRationale(e.target.value)} data-testid="receipt-rationale" />
        </div>

        <h3>Limitations</h3>
        <ul className="small">
          {defaultLimitations(manifest).map((l) => (
            <li key={l}>{l}</li>
          ))}
          {limitations.map((l, i) => (
            <li key={`${l}-${i}`}>
              {l}{' '}
              <button type="button" className="small" onClick={() => setLimitations(limitations.filter((_, j) => j !== i))}>
                remove
              </button>
            </li>
          ))}
        </ul>
        <div className="controls">
          <label>
            add a limitation
            <input type="text" maxLength={500} value={limitationText} onChange={(e) => setLimitationText(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={!limitationText.trim()}
            onClick={() => {
              setLimitations([...limitations, limitationText.trim()]);
              setLimitationText('');
            }}
          >
            add
          </button>
        </div>
        <p className="small muted">outcome: status not_observed, measured_value null (nothing here is a measured result).</p>

        <div className="button-row">
          <button type="button" onClick={build} data-testid="receipt-preview">
            build preview
          </button>
          <button
            type="button"
            className="primary"
            data-testid="receipt-export"
            onClick={() => {
              const r = build();
              if (r) {
                downloadJson(receiptFileName(r), r);
                setStatus(`exported ${receiptFileName(r)}`);
              }
            }}
          >
            export receipt JSON
          </button>
        </div>
        {buildError ? (
          <p className="bad-text" role="alert">
            {buildError}
          </p>
        ) : null}
        {preview ? (
          <details open>
            <summary>receipt preview ({preview.receipt_id})</summary>
            <pre className="small wrap" style={{ whiteSpace: 'pre-wrap' }} data-testid="receipt-json">
              {JSON.stringify(preview, null, 1)}
            </pre>
          </details>
        ) : null}
      </div>

      <h3>Import a receipt</h3>
      <div className="panel">
        <label>
          receipt file (JSON)
          <input
            type="file"
            accept="application/json,.json"
            data-testid="receipt-import"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const text = await readFileText(f);
              const r = importReceipt(text, core.ref);
              setReceiptImport(r);
              setStatus(r.status === 'ok' ? `receipt ${r.receipt.receipt_id} is compatible with this snapshot` : `receipt rejected: ${r.message}`);
              e.target.value = '';
            }}
          />
        </label>
        {receiptImport ? (
          receiptImport.status === 'ok' ? (
            <div data-testid="receipt-import-ok">
              <p className="ok-text">compatible receipt {receiptImport.receipt.receipt_id} (scenario {receiptImport.receipt.selected_controls.scenario_id}, action {receiptImport.receipt.chosen_action})</p>
              <details>
                <summary>contents</summary>
                <pre className="small" style={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(receiptImport.receipt, null, 1)}
                </pre>
              </details>
            </div>
          ) : (
            <div className="error" role="alert" data-testid="receipt-import-rejected">
              <strong>{receiptImport.reason === 'incompatible_snapshot' ? 'incompatible snapshot' : receiptImport.reason === 'synthetic' ? 'sandbox receipt refused' : 'invalid receipt file'}</strong>
              <p className="small">{receiptImport.message} Nothing was applied.</p>
              {receiptImport.quarantine ? (
                <KeyValue
                  rows={[
                    ['quarantined receipt id', receiptImport.quarantine.receipt_id],
                    ['its snapshot id', receiptImport.quarantine.snapshot_id],
                    ['its analytical digest', <code className="wrap">{receiptImport.quarantine.analytical_digest}</code>],
                    ['its scenario', receiptImport.quarantine.scenario_id],
                    ['created', receiptImport.quarantine.created_at_utc],
                  ]}
                />
              ) : null}
            </div>
          )
        ) : null}
      </div>

      <h3>Decision ledger</h3>
      <div className="panel">
        <p className="small">
          {fmtInt(realEvents.length)} real-scenario event(s) stored locally ({fmtInt(events.length - realEvents.length)} synthetic, excluded from receipts). Storage key <code>erlab:v1:{manifest.snapshot_id}:{manifest.analytical_digest.slice(0, 12)}…</code>
        </p>
        <div className="button-row">
          <button
            type="button"
            data-testid="ledger-export"
            onClick={() => {
              downloadJson(`review-events-${manifest.snapshot_id.replace(/[^A-Za-z0-9_@.+-]/g, "_")}.json`, exportLedger(core.ref, events));
              setStatus('exported the decision ledger');
            }}
          >
            export ledger JSON ({fmtInt(events.length)} events)
          </button>
          <label>
            import ledger JSON
            <input
              type="file"
              accept="application/json,.json"
              data-testid="ledger-import"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                const text = await readFileText(f);
                setLedgerImport(importLedgerText(text));
                e.target.value = '';
              }}
            />
          </label>
          <button type="button" className="danger" onClick={() => setConfirmReset(true)} data-testid="ledger-reset">
            reset local decisions
          </button>
        </div>
        {ledgerImport ? (
          ledgerImport.status === 'ok' ? (
            <p className="ok-text" data-testid="ledger-import-ok">
              imported {fmtInt(ledgerImport.imported)} new event(s); ledger now has {fmtInt(ledgerImport.events.length)} events
            </p>
          ) : (
            <div className="error" role="alert" data-testid="ledger-import-rejected">
              <strong>{ledgerImport.reason === 'incompatible_snapshot' ? 'incompatible snapshot' : ledgerImport.reason === 'corrupt' ? 'corrupted or invalid file' : 'invalid ledger'}</strong>
              <p className="small">{ledgerImport.message} Nothing was applied.</p>
              {ledgerImport.quarantine ? (
                <KeyValue
                  rows={[
                    ['its snapshot id', ledgerImport.quarantine.snapshot_id],
                    ['its analytical digest', <code className="wrap">{ledgerImport.quarantine.analytical_digest}</code>],
                    ['events in file', fmtInt(ledgerImport.quarantine.event_count)],
                    ['exported', ledgerImport.quarantine.exported_at_utc],
                  ]}
                />
              ) : null}
            </div>
          )
        ) : null}
        <ConfirmDialog
          open={confirmReset}
          title="Reset local decisions?"
          body="This deletes every locally stored review event for this snapshot from this browser. Export the ledger first if you want to keep it. The frozen benchmark is unaffected."
          confirmLabel="Reset decisions"
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => {
            resetLedger();
            setConfirmReset(false);
          }}
        />
      </div>

      <h3>Consequences</h3>
      {cases.status === 'loading' || cases.status === 'idle' ? <Loading what="cases (for the consequence panel)" /> : cases.status === 'error' ? <ErrorState error={cases.error} /> : null}
      {caseData ? (
        <>
          <div className="controls">
            <label>
              case set
              <select value={caseSetMode} onChange={(e) => setCaseSetMode(e.target.value as 'events' | 'all')} data-testid="receipt-case-set">
                <option value="events">cases with events in this scenario ({fmtInt(eventCases.length)})</option>
                <option value="all">all curated cases ({fmtInt(caseData.cases.length)})</option>
              </select>
            </label>
          </div>
          <ConsequencesPanel events={events} scenarioId={scenarioIdText} method={scenario.method} caseSet={caseSet} setLabel={caseSetMode === 'events' ? 'the cases with events in this scenario' : 'all curated cases'} />
        </>
      ) : null}
    </>
  );
}
