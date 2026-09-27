import { KeyValue } from '../components/common';
import { fmtInt } from '../lib/format';
import { useCore } from '../store';

export function ProvenanceView() {
  const core = useCore();
  if (!core) return null;
  const { manifest, snapshot } = core;
  const caps = manifest.capabilities;
  return (
    <>
      <h2 style={{ marginTop: 0 }}>Provenance</h2>
      <p className="note">Hashes are integrity aids, not signatures. The evidence identity (evaluation run) is distinct from the lab build metadata (when this export was assembled).</p>

      <h3>Evidence identity</h3>
      <div className="panel" data-testid="evidence-identity">
        <KeyValue
          rows={[
            ['snapshot id', <code className="wrap">{manifest.snapshot_id}</code>],
            ['analytical digest', <code className="wrap" data-testid="analytical-digest">{manifest.analytical_digest}</code>],
            ['run id', manifest.evidence.run_id],
            ['evaluation code commit', <code className="wrap">{manifest.evidence.evaluation_code_commit}</code>],
            ['evaluation generated at (UTC)', manifest.evidence.evaluation_generated_at_utc],
            ['feature version', manifest.evidence.feature_version],
            ['manifest sha256 at evaluation', <code className="wrap">{manifest.evidence.manifest_sha256_at_evaluation}</code>],
            ['artifact version / sensitivity version', `${manifest.evidence.artifact_version} / ${manifest.evidence.sensitivity_version}`],
            ['lab contract version', manifest.evidence.lab_contract_version],
          ]}
        />
      </div>
      <h3>Lab build metadata (volatile, excluded from the analytical digest)</h3>
      <div className="panel" data-testid="build-metadata">
        <KeyValue
          rows={[
            ['built at (UTC)', manifest.build.built_at_utc],
            ['builder code commit', <code className="wrap">{manifest.build.builder_code_commit}</code>],
            ['builder version', manifest.build.builder_version],
            ['lab manifest version', manifest.lab_manifest_version],
          ]}
        />
      </div>

      <h3>Sources</h3>
      <div className="panel">
        <table data-testid="sources-table">
          <thead>
            <tr>
              <th className="left">path</th>
              <th className="left">role</th>
              <th className="left">sha256</th>
              <th className="left">local only</th>
            </tr>
          </thead>
          <tbody>
            {manifest.sources.map((s) => (
              <tr key={`${s.path}-${s.role}`}>
                <td className="mono small">{s.path}</td>
                <td className="small">{s.role}</td>
                <td className="mono small wrap" data-testid="source-sha">
                  {s.sha256}
                </td>
                <td className="small">{s.local_only ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Generated files</h3>
      <div className="panel">
        <table data-testid="files-table">
          <thead>
            <tr>
              <th className="left">file</th>
              <th>bytes</th>
              <th>rows</th>
              <th className="left">generated from</th>
              <th className="left">recomputable without local data</th>
              <th className="left">analytical</th>
              <th className="left">schema</th>
              <th className="left">sha256</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(manifest.files).map(([name, f]) => (
              <tr key={name}>
                <td className="mono small">{name}</td>
                <td>{fmtInt(f.bytes)}</td>
                <td>{f.rows === undefined ? '—' : fmtInt(f.rows)}</td>
                <td className="small">{f.generated_from}</td>
                <td className="small">{f.recomputable_without_local_data ? 'yes' : 'no'}</td>
                <td className="small">{f.analytical ? 'yes' : 'no'}</td>
                <td className="mono small">{f.schema ?? ''}</td>
                <td className="mono small wrap">{f.sha256}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Capabilities</h3>
      <div className="panel">
        <table data-testid="capabilities-table">
          <thead>
            <tr>
              <th className="left">capability</th>
              <th className="left">available</th>
              <th className="left">note</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                ['evidence_comparison', caps.evidence_comparison],
                ['supported_floor_control', caps.supported_floor_control],
                ['case_explorer', caps.case_explorer],
                ['decision_ledger', caps.decision_ledger],
                ['synthetic_sandbox', caps.synthetic_sandbox],
                ['local_case_evidence', caps.local_case_evidence],
              ] as const
            ).map(([name, c]) => (
              <tr key={name}>
                <td className="mono">{name}</td>
                <td>{c.available ? 'yes' : 'no'}</td>
                <td className="small">{c.note}</td>
              </tr>
            ))}
            {Object.entries(caps.complete_replay).map(([m, c]) => (
              <tr key={m}>
                <td className="mono">complete_replay.{m}</td>
                <td>{c.available ? 'yes' : 'no'}</td>
                <td className="small">
                  {c.note} (decision value kind: {c.decision_value_kind}
                  {c.reconciled_to_eval_artifact !== undefined ? `; reconciled to eval artifact: ${c.reconciled_to_eval_artifact ? 'yes' : 'no'}` : ''}
                  {c.population_conserved !== undefined ? `; population conserved: ${c.population_conserved ? 'yes' : 'no'}` : ''})
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">Supported operations: {manifest.supported_operations.join(', ')}</p>
      </div>

      <h3>Population</h3>
      <div className="panel">
        <KeyValue
          rows={[
            ['fold / grain', `${manifest.population.fold} / ${manifest.population.grain}`],
            ['A records', fmtInt(manifest.population.a_records)],
            ['labelled A records', fmtInt(manifest.population.labelled_a)],
            ['labelled A records with truth reachable', fmtInt(manifest.population.labelled_a_reachable)],
            ['source keys', <span className="mono small wrap">{manifest.population.source_keys.join('; ')}</span>],
          ]}
        />
      </div>

      <h3>Case selection strategy</h3>
      <div className="panel">
        <p className="small">
          strategy <code>{manifest.selection.strategy_version}</code>, {fmtInt(manifest.selection.total_cases)} cases
        </p>
        <table>
          <thead>
            <tr>
              <th className="left">reason code</th>
              <th className="left">description</th>
              <th>cap</th>
              <th>selected</th>
              <th>available</th>
              <th className="left">source</th>
              <th className="left">deterministic order</th>
            </tr>
          </thead>
          <tbody>
            {manifest.selection.criteria.map((c) => (
              <tr key={c.reason_code}>
                <td className="mono">{c.reason_code}</td>
                <td className="small">{c.description}</td>
                <td>{fmtInt(c.cap)}</td>
                <td>{c.selected === undefined ? '—' : fmtInt(c.selected)}</td>
                <td>{c.available === undefined ? '—' : fmtInt(c.available)}</td>
                <td className="small">{c.source}</td>
                <td className="small">{c.deterministic_order}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="small">
          {manifest.selection.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </div>

      <h3>Snapshot provenance</h3>
      <div className="panel">
        <p className="small">{snapshot.provenance.note}</p>
        <table>
          <thead>
            <tr>
              <th className="left">artifact</th>
              <th className="left">path</th>
              <th className="left">sha256</th>
              <th className="left">code commit</th>
              <th className="left">generated at</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(snapshot.provenance.eval_artifacts).map(([m, f]) => (
              <tr key={`eval-${m}`}>
                <td>eval {m}</td>
                <td className="mono small">{f.path}</td>
                <td className="mono small wrap">{f.sha256}</td>
                <td className="mono small">{f.code_commit ?? ''}</td>
                <td className="small">{f.generated_at_utc ?? ''}</td>
              </tr>
            ))}
            {Object.entries(snapshot.provenance.method_records).map(([m, f]) => (
              <tr key={`method-${m}`}>
                <td>method record {m}</td>
                <td className="mono small">{f.path}</td>
                <td className="mono small wrap">{f.sha256}</td>
                <td className="mono small">{f.code_commit ?? ''}</td>
                <td className="small">{f.generated_at_utc ?? ''}</td>
              </tr>
            ))}
            <tr>
              <td>review sensitivity</td>
              <td className="mono small">{snapshot.provenance.review_sensitivity.path}</td>
              <td className="mono small wrap">{snapshot.provenance.review_sensitivity.sha256}</td>
              <td className="mono small">{snapshot.provenance.review_sensitivity.code_commit ?? ''}</td>
              <td className="small">{snapshot.provenance.review_sensitivity.generated_at_utc ?? ''}</td>
            </tr>
            <tr>
              <td>split</td>
              <td className="mono small">{snapshot.provenance.split.path}</td>
              <td className="mono small wrap">{snapshot.provenance.split.sha256}</td>
              <td className="mono small">{snapshot.provenance.split.code_commit ?? ''}</td>
              <td className="small">{snapshot.provenance.split.generated_at_utc ?? ''}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
