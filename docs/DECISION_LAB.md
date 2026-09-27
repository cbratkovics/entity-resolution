# Decision Lab: architecture and contracts

The Decision Lab (ADR 0006) is a static, local-first workbench over the frozen benchmark that
answers one question: *which records should this matching policy accept automatically, send to
review, or leave unresolved, and what evidence and trade-offs justify that decision?* It lives at
`/entity-resolution/lab/` beside the results page and the dbt docs. This file says where each
piece lives, what the contracts are, and where the evidence stops.

## Data flow

```
committed artifacts (artifacts/*.json, methods/, mapping/*.test.csv.gz)
        │
        ├─ entity_resolution/decision_lab  (make lab-export / make lab-check)
        │       snapshot.py   → artifacts/lab/snapshot.json        aggregate comparison, floor points, legacy sweep
        │       cases.py      → artifacts/lab/cases.json           curated cases (+ case_selection.json for dbt)
        │       replay.py     → artifacts/lab/replay/*             complete-replay bundles (owner-run, hash-verified inputs)
        │       synthetic.py  → apps/decision-lab/fixtures/synthetic_sandbox.json
        │       fixtures.py   → apps/decision-lab/fixtures/policy_fixtures.json
        │       export.py     → artifacts/lab/manifest.json        hashes, capabilities, analytical digest
        │
        ├─ dbt: brz_lab_case_selection, brz_lab_cases → fct_lab_case_evidence, fct_lab_case_comparison
        │       assert_lab_case_evidence_reconciles_to_bundle; exposure decision_lab
        │
        └─ apps/decision-lab (Vite + React + TypeScript; Vitest; Playwright)
                scripts/sync-data.mjs copies artifacts/lab/ → public/data/
                src/lib/policy.ts mirrors decision_lab/policy.py (shared fixtures)
                dist/ → site/lab/ in pages.yml
```

Frozen data under `data/` (git-ignored) is read only by the owner-run replay and local-evidence
stages, and only after its file hashes match `artifacts/manifest.json`. Nothing is downloaded
and nothing is refitted.

## Package `entity_resolution/decision_lab/`

| module | role |
|---|---|
| `policy.py` | the one pure policy specification: rank by decision value with lexical B-id ties, null gap for a single candidate, inclusive accept/review bounds, strict `gap < ambiguity_gap` on non-reject decisions, ambiguity tracked separately from demotion, no-candidate records kept in the population; `evaluate` reproduces the evaluator's metrics and rounding; corrected `floor_sweep` and `accept_sweep`; `legacy_accept_sweep` restates the historical calculation for comparison only. |
| `fixtures.py` | renders the canonical fixtures the Python and TypeScript evaluators are both tested against, including the mandatory ambiguity regression (ADR 0007). |
| `contracts.py` | schema loading with cross-file references, canonical JSON, hashing, the public-export allowlist, forbidden-key scan, id validators and the two allowlisted link builders. |
| `snapshot.py` | copies every aggregate the lab shows from `eval_*.json`, `methods/*.json`, `review_sensitivity.json` and `split.json`, each with its source key, numerator and denominator. |
| `cases.py` | deterministic curated-case selection over the mapping exhibits (ascending A id per criterion, fixed caps), evidence rows, comparison class, and the owner-run label block. |
| `replay.py` | exports one row per test-fold A record with unrounded decision values, candidate counts and label metadata; proves completeness and reconciles to the evaluation artifact. |
| `synthetic.py` | the synthetic mechanics sandbox: invented records, fixture scores, boundary cases, a downstream duplicate-join fixture. |
| `ledger.py` | validation of receipts and review-event exports; effective-state derivation (append-only, undo as reversal, one effective accept per A and scenario). |
| `export.py`, `cli.py` | build, manifest, `--check`. |

## Contracts

Every file the lab reads has a strict JSON schema under `artifacts/schemas/lab_*.schema.json`
(`additionalProperties: false`, patterned identifiers, bounded strings for anything a user can
type). Contract version `1.0` is written into every file and every receipt.

| file | schema | content |
|---|---|---|
| `artifacts/lab/manifest.json` | `lab_manifest` | snapshot identity (`<run_id>@<manifest hash prefix>`), every input with its sha256, every generated file with sha256, bytes and rows, capabilities, population, selection strategy, supported operations, volatile `build` block |
| `artifacts/lab/snapshot.json` | `lab_snapshot` | per method: definition, score kind, recorded policy with its source key, metrics with numerator/denominator/source key, calibration, supported review-floor points, the legacy threshold sweep (labelled), the mapping exhibit hash |
| `artifacts/lab/cases.json` | `lab_cases` | curated cases: reason codes, three evidence rows (exported or an explicit not-exported state), comparison class, labels block (`truth_unavailable` or `verified_local`), narrative marker for the worked examples |
| `artifacts/lab/replay/replay_<m>.test.csv.gz` + `.json` | `lab_replay_meta` | complete-replay rows (no identifiers) and the completeness proof, input hashes, reconciliation and legacy divergence |
| `apps/decision-lab/fixtures/synthetic_sandbox.json` | `lab_synthetic_sandbox` | synthetic-only readable records and fixture scores; badge text |
| receipts and ledgers exported by the browser | `lab_receipt`, `lab_review_events` | policy-scenario receipts and append-only review events, namespaced by snapshot |

The analytical digest in the manifest is a hash over the analytical files' content hashes, so
unchanged evidence yields the same digest whatever the build time; `build.built_at_utc` and the
builder commit are outside it. Evaluation provenance (original code commit, feature version,
evaluation timestamps) is copied from the artifacts and kept distinct from lab build metadata.

## Capabilities and their boundaries

| capability | status | what it rests on |
|---|---|---|
| method comparison at recorded settings | real snapshot | `eval_<m>.json#metrics`, `methods/<m>.json#tier_policy` |
| supported review-floor control | real snapshot | `review_sensitivity.json#methods.<m>.review_floor_sweep`; exact at the recorded accept threshold; only exported floors; nothing interpolated |
| queue-budget feasibility | real snapshot | the same points; "no supported setting" is a valid answer |
| curated case explorer | real snapshot | the mapping exhibits (`fct_mapping` grain), plus owner-run labels from the local truth table when present |
| decision ledger and receipts | local browser | user decisions, never labels or mapping writes |
| complete replay, `exact_v1` and `rules_v1` | real snapshot, owner-run export | unrounded scores recomputed from the frozen features (pure functions, hash-verified), reconciled to the artifacts |
| complete replay, `learned_v1` | unavailable | no frozen model binary; rounded mappings are insufficient (ADR 0007) |
| synthetic mechanics sandbox | synthetic only | invented records; never enters a real figure |

## Metric invariants

At A-record grain on the test fold: labelled precision is correct labelled auto-accepts over
labelled auto-accepts; reachable-labelled recall divides by labelled records whose truth
survived blocking; overall-labelled recall divides by all labelled records; coverage divides all
auto-accepts by all A records; unverified accepts are auto-accepts on unlabelled records and
count toward coverage only; review-recall figures are upper bounds that assume every queued
reachable record is resolved correctly. Denominator-zero metrics are shown as unavailable. Rules
scores are uncalibrated; the learned model's pair-level calibration is distinct from its
selected-top-candidate calibration. Full-snapshot metrics, curated-case counts, synthetic
outcomes and user-decision overlays are kept in separate stores and never combined.

The legacy cost expression extrapolates labelled precision to all accepts and costs no missed
match; the lab retains it only under the label "legacy snapshot calculation" with that
assumption stated, never as measured cost, savings or ROI. User-entered effort values are
displayed as assumptions with units.

## Legacy views: retained, restricted, annotated

- Retained unchanged: the results page's cost curve and review-floor chart, `fct_review_queue`,
  `fct_review_floor`, `review_sensitivity.json`.
- Restricted: the accept-threshold sweep never powers a replay claim in the lab; it is shown
  collapsed, labelled legacy, with the flag-reuse note and the per-threshold divergence from the
  corrected replay (`replay_<m>.json#legacy_sweep_divergence`).
- Annotated: the review-floor sweep is labelled "supported, exact at the recorded accept
  threshold"; floors at or above the accept threshold are shown as omitted with the reason.

## Public-data rules

Real cases carry identifiers, numbers, controlled reason codes and provenance only. No source
title, artist, year or excerpt is exported; `tests/test_no_raw_rows.py` scans the lab files like
every other artifact, and `make lab-check` rejects unknown files and forbidden keys under
`artifacts/lab/`. Readable records exist only in the synthetic sandbox, whose identifiers cannot
collide with real ones and whose words come from a fixed nonsense vocabulary. Imported receipts
and ledgers are untrusted: strict schemas, length limits, pattern-checked identifiers, text-only
rendering, allowlisted link hosts, a snapshot check before anything is applied. All local
decisions stay in the browser unless the user exports them; the app makes no request outside its
own base path.

## Make targets

| target | runs |
|---|---|
| `make lab-export` | `python -m entity_resolution.decision_lab.cli export`: snapshot, cases, selection, synthetic sandbox, policy fixtures, and, when the frozen local inputs are present and hash-verified, the replay bundles and local case labels; then the manifest |
| `make lab-check` | `... cli check`: recomputes every recomputable file in memory, verifies hashes, schemas, allowlist, digest, and re-verifies the replay bundles from the compressed files; rewrites nothing |
| `make lab-fixtures` | rewrites the shared policy fixtures |
| `make lab-dev` | `npm run dev` in `apps/decision-lab` (after syncing the export into `public/data`) |
| `make lab-test` | the lab's pytest modules plus `npm run typecheck`, `npm run lint` and `npm test` |
| `make lab-build` | `npm run build` at the Pages base path, then `npm run size` |
| `make lab-verify` | `lab-check`, `lab-test`, `lab-build` and the Playwright journeys against the built app |

`make setup`, `lint`, `test`, `dbt`, `docs` and `smoke` remain Python-only and do not need Node;
`smoke.sh` additionally runs `make lab-check` so a stale export fails in a fresh clone.
