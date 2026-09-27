import { useEffect, useMemo, useState } from 'react';
import { ConsequencesPanel } from '../components/ConsequencesPanel';
import { ErrorState, KeyValue, Loading, MethodName, Why } from '../components/common';
import { ReviewActions, type ReviewTarget } from '../components/ReviewActions';
import { ScenarioPicker } from '../components/ScenarioPicker';
import { METHODS, type LabCase, type LabCases, type MethodVersion } from '../lib/contracts';
import { casesWithEvents } from '../lib/consequences';
import { whyTier } from '../lib/evidence';
import { fmtInt, fmtNum, reasonLabel, tierLabel } from '../lib/format';
import { discogsLink, musicbrainzLink } from '../lib/links';
import { buildHash, type Route } from '../lib/router';
import { useCore, useStore } from '../store';

const AGREEMENT = ['all_exported_agree', 'methods_disagree', 'single_method_exported', 'none_exported'] as const;

interface Filters {
  reasons: Set<string>;
  method: string;
  tier: string;
  agreement: string;
  verifiedOnly: boolean;
  search: string;
}

function applyFilters(cases: LabCase[], f: Filters): LabCase[] {
  const q = f.search.trim();
  return cases.filter((c) => {
    if (f.reasons.size && !c.reason_codes.some((r) => f.reasons.has(r))) return false;
    if (f.method && !c.evidence.some((r) => r.method_version === f.method && r.exported)) return false;
    if (f.tier && !c.evidence.some((r) => r.exported && r.tier === f.tier && (!f.method || r.method_version === f.method))) return false;
    if (f.agreement && c.comparison.agreement_class !== f.agreement) return false;
    if (f.verifiedOnly && c.labels.state !== 'verified_local') return false;
    if (q) {
      const inA = c.a_id.includes(q);
      const inB = c.evidence.some((r) => r.exported && r.b_id.includes(q));
      const inTruth = c.labels.state === 'verified_local' && c.labels.truth_b_ids.some((b) => b.includes(q));
      if (!inA && !inB && !inTruth) return false;
    }
    return true;
  });
}

function IdLink({ kind, id }: { kind: 'a' | 'b'; id: string }) {
  const href = kind === 'a' ? musicbrainzLink(id) : discogsLink(id);
  if (!href) return <code>{id}</code>;
  return (
    <a href={href} rel="noopener noreferrer" target="_blank" className="mono" data-testid={kind === 'a' ? 'link-mb' : 'link-discogs'}>
      {id}
    </a>
  );
}

function CaseDetail({ data, c }: { data: LabCases; c: LabCase }) {
  const core = useCore();
  const { scenario, scenarioIdText, events, record, undo } = useStore();
  if (!core) return null;
  const labels = c.labels;
  const per = labels.state === 'verified_local' ? labels.per_method : {};
  const candidates: ReviewTarget['candidates'] = [];
  for (const r of c.evidence) if (r.exported && !candidates.some((x) => x.b_id === r.b_id)) candidates.push({ b_id: r.b_id, origin: `chosen by ${r.method_version}` });
  if (labels.state === 'verified_local') for (const b of labels.truth_b_ids) if (!candidates.some((x) => x.b_id === b)) candidates.push({ b_id: b, origin: 'truth' });
  const target: ReviewTarget = {
    scenario_id: scenarioIdText,
    a_id: c.a_id,
    method_version: scenario.method,
    evidence_ref: { case_id: c.case_id, source: 'cases.json' },
    candidates,
  };
  const disagree = c.comparison.agreement_class === 'methods_disagree';
  const withinAmbiguity = c.evidence.filter((r) => r.exported && r.ambiguity_demoted_derived === true).map((r) => r.method_version);
  return (
    <article aria-labelledby="case-heading" data-testid="case-detail">
      <p>
        <a href={buildHash('cases')}>← all cases</a>
      </p>
      <h2 id="case-heading" style={{ marginTop: 0 }}>
        Case <code className="wrap">{c.case_id}</code>
      </h2>
      <ScenarioPicker snapshot={core.snapshot} />
      <div className="panel">
        <KeyValue
          rows={[
            ['A record (MusicBrainz release group)', <IdLink kind="a" id={c.a_id} />],
            ['reason codes', c.reason_codes.join(', ')],
            ['agreement class', c.comparison.agreement_class],
          ]}
        />
      </div>

      <h3>Evidence per method</h3>
      <div className="panel">
        <table data-testid="evidence-table">
          <thead>
            <tr>
              <th className="left">method</th>
              <th className="left">chosen B (Discogs master)</th>
              <th>score</th>
              <th>probability</th>
              <th className="left">score kind</th>
              <th className="left">baseline tier</th>
              <th className="left">exported top-two gap</th>
              <th className="left">block keys</th>
              <th className="left">policy</th>
              <th className="left">run / decided</th>
              <th className="left">provenance</th>
            </tr>
          </thead>
          <tbody>
            {METHODS.map((m) => {
              const r = c.evidence.find((x) => x.method_version === m);
              const pol = data.policies[m];
              if (!r) {
                return (
                  <tr key={m} data-testid={`evidence-row-${m}`}>
                    <td>
                      <MethodName method={m} />
                    </td>
                    <td colSpan={10} className="left muted">
                      not in the exhibit
                    </td>
                  </tr>
                );
              }
              if (!r.exported) {
                const text = r.reason === 'reject_or_no_candidate' ? 'not exported: rejected or no candidate' : r.reason === 'rejected' ? 'not exported: rejected' : 'not exported: no candidate';
                return (
                  <tr key={m} data-testid={`evidence-row-${m}`}>
                    <td>
                      <MethodName method={m} />
                    </td>
                    <td colSpan={9} className="left muted">
                      {text}
                    </td>
                    <td className="mono small wrap">{r.source}</td>
                  </tr>
                );
              }
              const why = pol ? whyTier(r, pol, per[m]?.unrounded_gap) : null;
              return (
                <tr key={m} data-testid={`evidence-row-${m}`}>
                  <td>
                    <MethodName method={m} />
                  </td>
                  <td>
                    <IdLink kind="b" id={r.b_id} />
                  </td>
                  <td>{fmtNum(r.score)}</td>
                  <td>{fmtNum(r.probability)}</td>
                  <td className="left small">{pol ? pol.score_kind.replace('_', ' ') : 'unknown'}</td>
                  <td className="left">
                    {tierLabel(r.tier)}{' '}
                    {why ? (
                      <Why label="why this tier?">
                        <div>
                          derived from {why.basis === 'unrounded_local' ? 'the unrounded local gap (preferred)' : 'rounded exported values (six decimals)'}:
                        </div>
                        <ul>
                          {why.lines.map((l) => (
                            <li key={l}>{l}</li>
                          ))}
                        </ul>
                        <div>
                          engine result: {tierLabel(why.decision.tier)} ({reasonLabel(why.decision.reason)}){why.matches_exported_tier ? ', matches the recorded tier' : ', differs from the recorded tier: the exhibit rounding cannot settle it'}
                        </div>
                      </Why>
                    ) : null}
                  </td>
                  <td className="left">
                    {r.gap_state === 'single_candidate' ? 'single candidate: null gap' : `${fmtNum(r.top2_gap)} (exported)`}{' '}
                    {r.gap_at_rounded_boundary ? (
                      <span className="badge warn" title="the six-decimal rounded gap equals the threshold; the exhibit cannot classify ambiguity">
                        rounded boundary
                      </span>
                    ) : null}
                    {r.ambiguity_demoted_derived === true ? <span className="badge"> demoted by ambiguity (derived)</span> : null}
                  </td>
                  <td className="left mono small">{r.block_keys.join(', ') || '—'}</td>
                  <td className="left small">{pol ? `accept ${fmtNum(pol.accept_min)}, review ${fmtNum(pol.review_min)}, gap ${fmtNum(pol.ambiguity_gap)}` : 'unknown'}</td>
                  <td className="left small">
                    {r.run_id}
                    <br />
                    {r.decided_at_utc}
                  </td>
                  <td className="left mono small wrap">{r.source}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="note">The rounded boundary badge means the exhibit's six-decimal rounding cannot classify the gap against the threshold; the recorded tier stands.</p>
      </div>

      <h3>Comparison</h3>
      <div className="panel">
        <p className="small">
          {c.comparison.methods_exported} method(s) exported a choice; {c.comparison.distinct_chosen_b_ids} distinct chosen B id(s); agreement class <code>{c.comparison.agreement_class}</code>.
        </p>
        <p className="small">
          {disagree
            ? 'Method disagreement: different methods chose different B ids for this record.'
            : 'No method disagreement: every exported method chose the same B id (or only one method exported).'}{' '}
          {withinAmbiguity.length
            ? `Within-method ambiguity: ${withinAmbiguity.join(', ')} had a top-two gap below the threshold inside its own ranking, which is a different thing.`
            : 'Within-method ambiguity (a gap below threshold inside one method) is not indicated by the exported values here.'}
        </p>
        <p className="note">The chosen B ids of different methods are not a ranked candidate list. {c.comparison.note}</p>
      </div>

      <h3>Labels</h3>
      <div className="panel" data-testid="labels-block">
        {labels.state === 'truth_unavailable' ? (
          <p>
            truth unavailable (not exported){labels.note ? <span className="muted"> — {labels.note}</span> : null}
          </p>
        ) : (
          <>
            <KeyValue
              rows={[
                ['labelled', labels.labelled ? 'labelled (has an in-sample truth link)' : 'unlabelled (not a known non-match)'],
                ['truth B ids', labels.truth_b_ids.length ? labels.truth_b_ids.map((b) => <IdLink key={b} kind="b" id={b} />) : '—'],
                ['candidates in the full blocked set', fmtInt(labels.n_candidates_full)],
                ['truth reachable in the full blocked set', labels.truth_reachable_full === null ? 'unavailable' : labels.truth_reachable_full ? 'yes' : 'no'],
                [
                  'truth visible among the exported choices',
                  labels.truth_visible_in_exported_choices === undefined || labels.truth_visible_in_exported_choices === null ? 'unavailable' : labels.truth_visible_in_exported_choices ? 'yes' : 'no',
                ],
                ['verifier', <code>{labels.verifier}</code>],
              ]}
            />
            <table>
              <thead>
                <tr>
                  <th className="left">method</th>
                  <th className="left">chosen correct</th>
                  <th>unrounded gap</th>
                  <th className="left">unrounded ambiguous</th>
                  <th className="left">note</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(labels.per_method).map(([m, v]) => (
                  <tr key={m}>
                    <td>
                      <MethodName method={m} />
                    </td>
                    <td className="left">{v.chosen_correct === null ? 'unavailable' : v.chosen_correct ? 'yes' : 'no'}</td>
                    <td>{v.unrounded_gap === null ? 'null' : fmtNum(v.unrounded_gap)}</td>
                    <td className="left">{v.unrounded_ambiguous === null ? 'unavailable' : v.unrounded_ambiguous ? 'yes' : 'no'}</td>
                    <td className="left small">{v.note ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      {c.narrative ? (
        <>
          <h3>Narrative</h3>
          <div className="panel" data-testid="narrative">
            <p className="small">
              <span className="badge warn">narrative ({c.narrative.source}), not machine-verified</span>
            </p>
            <p>{c.narrative.note}</p>
          </div>
        </>
      ) : null}

      <ReviewActions
        target={target}
        events={events}
        onRecord={(input) => record({ scenario_id: target.scenario_id, a_id: target.a_id, method_version: target.method_version, evidence_ref: target.evidence_ref, ...input })}
        onUndo={() => undo({ scenario_id: target.scenario_id, a_id: target.a_id, method_version: target.method_version, evidence_ref: target.evidence_ref })}
      />
      <ConsequencesPanel events={events} scenarioId={scenarioIdText} method={scenario.method} caseSet={[c]} setLabel="this case" />
    </article>
  );
}

export function CasesView({ route }: { route: Route }) {
  const core = useCore();
  const { cases, ensureCases, events, scenario, scenarioIdText } = useStore();
  const [filters, setFilters] = useState<Filters>({ reasons: new Set(), method: '', tier: '', agreement: '', verifiedOnly: false, search: '' });
  const [consequenceSet, setConsequenceSet] = useState<'events' | 'filtered'>('events');
  useEffect(() => {
    ensureCases();
  }, [ensureCases]);

  const data = cases.status === 'ready' ? cases.data : null;
  const filtered = useMemo(() => (data ? applyFilters(data.cases, filters) : []), [data, filters]);
  if (!core) return null;
  if (cases.status === 'loading' || cases.status === 'idle') return <Loading what="the curated cases (cases.json)" />;
  if (cases.status === 'error') return <ErrorState error={cases.error} />;
  if (!data) return null;

  if (route.caseId) {
    const c = data.cases.find((x) => x.a_id === route.caseId || x.case_id === route.caseId);
    if (!c) {
      return (
        <div className="error" role="alert">
          No curated case with id <code>{route.caseId}</code>. <a href={buildHash('cases')}>Back to the list</a>.
        </div>
      );
    }
    return <CaseDetail data={data} c={c} />;
  }

  const reasonCodes = Object.keys(data.selection.counts_by_reason).sort();
  const eventCases = casesWithEvents(events, scenarioIdText, data.cases);
  const setForConsequences = consequenceSet === 'events' ? eventCases : filtered;
  return (
    <>
      <h2 style={{ marginTop: 0 }}>Curated cases</h2>
      <p className="note">
        {fmtInt(data.selection.total_cases)} cases selected by strategy <code>{data.selection.strategy_version}</code>; a curated exhibit, not a representative sample. Local evidence:{' '}
        {data.selection.local_evidence.available ? 'available' : 'unavailable'} — {data.selection.local_evidence.note}
      </p>
      <ScenarioPicker snapshot={core.snapshot} />
      <div className="panel">
        <details open>
          <summary>Selection counts and limitations</summary>
          <table>
            <thead>
              <tr>
                <th className="left">reason code</th>
                <th>cases</th>
                <th className="left">criterion</th>
                <th>cap</th>
                <th className="left">source</th>
              </tr>
            </thead>
            <tbody>
              {reasonCodes.map((r) => {
                const crit = data.selection.criteria.find((x) => x.reason_code === r);
                return (
                  <tr key={r}>
                    <td>
                      <code>{r}</code>
                    </td>
                    <td>{fmtInt(data.selection.counts_by_reason[r])}</td>
                    <td className="left small">{crit?.description ?? ''}</td>
                    <td>{crit ? fmtInt(crit.cap) : ''}</td>
                    <td className="left small">{crit?.source ?? ''}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <ul className="small">
            {data.selection.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </details>
      </div>

      <h3>Filters</h3>
      <div className="panel">
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="small muted">reason codes (any of)</legend>
          <div className="chips">
            {reasonCodes.map((r) => (
              <label key={r}>
                <input
                  type="checkbox"
                  checked={filters.reasons.has(r)}
                  data-testid={`filter-reason-${r}`}
                  onChange={(e) => {
                    const next = new Set(filters.reasons);
                    if (e.target.checked) next.add(r);
                    else next.delete(r);
                    setFilters({ ...filters, reasons: next });
                  }}
                />
                {r}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="controls">
          <label>
            method exported
            <select value={filters.method} onChange={(e) => setFilters({ ...filters, method: e.target.value })} data-testid="filter-method">
              <option value="">any</option>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label>
            tier
            <select value={filters.tier} onChange={(e) => setFilters({ ...filters, tier: e.target.value })} data-testid="filter-tier">
              <option value="">any</option>
              <option value="auto_accept">auto-accept</option>
              <option value="review">review</option>
            </select>
          </label>
          <label>
            agreement class
            <select value={filters.agreement} onChange={(e) => setFilters({ ...filters, agreement: e.target.value })} data-testid="filter-agreement">
              <option value="">any</option>
              {AGREEMENT.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={filters.verifiedOnly} onChange={(e) => setFilters({ ...filters, verifiedOnly: e.target.checked })} data-testid="filter-verified" /> has verified labels
          </label>
          <label>
            search a_id / b_id (substring)
            <input type="search" value={filters.search} maxLength={40} onChange={(e) => setFilters({ ...filters, search: e.target.value })} data-testid="filter-search" />
          </label>
        </div>
        <p className="small" data-testid="filter-count">
          {fmtInt(filtered.length)} of {fmtInt(data.cases.length)} cases match.
        </p>
      </div>

      {filtered.length === 0 ? (
        <p data-testid="empty-cases">No cases match the current filters.</p>
      ) : (
        <ul className="case-list" data-testid="case-list">
          {filtered.map((c) => (
            <li key={c.case_id} data-testid="case-item">
              <a href={buildHash('cases', { caseId: c.a_id })} className="mono" data-testid="case-link">
                {c.a_id}
              </a>
              <span className="small">{c.reason_codes.join(', ')}</span>
              <span className="small muted">{c.comparison.agreement_class}</span>
              <span className="small muted">{c.labels.state === 'verified_local' ? (c.labels.labelled ? 'labelled' : 'unlabelled (verified)') : 'truth unavailable'}</span>
              <span className="small">
                {c.evidence
                  .filter((r) => r.exported)
                  .map((r) => (r.exported ? `${r.method_version}: ${tierLabel(r.tier)}` : ''))
                  .join(' · ') || 'nothing exported'}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3>Consequences</h3>
      <div className="controls">
        <label>
          case set
          <select value={consequenceSet} onChange={(e) => setConsequenceSet(e.target.value as 'events' | 'filtered')} data-testid="consequence-set">
            <option value="events">cases with events in this scenario ({fmtInt(eventCases.length)})</option>
            <option value="filtered">the filtered case list ({fmtInt(filtered.length)})</option>
          </select>
        </label>
      </div>
      <ConsequencesPanel
        events={events}
        scenarioId={scenarioIdText}
        method={scenario.method as MethodVersion}
        caseSet={setForConsequences}
        setLabel={consequenceSet === 'events' ? 'the cases with events in this scenario' : 'the filtered case list'}
      />
    </>
  );
}
