# Architecture

The design is `docs/BRIEF.md` section 2; this file says where each piece lives.

## Package `entity_resolution/`

| module | role |
|---|---|
| `config.py` | `PROJECT`: sides, method versions, folds, tiers, paths. `side_a` is `"musicbrainz"` (ADR-0001). |
| `interfaces.py` | `SourceAdapter` protocol; `Record`, `TruthLink`, `CandidatePair`, `Decision` dataclasses. |
| `data/loader.py` | adapter registry: `discogs` (side B), `musicbrainz` (side A, ADR 0001) and `fixture` for offline tests. |
| `data/acquire.py` | dump specs, timed and hashed downloads behind a free-disk check, streaming extraction of named tar members. |
| `data/discogs.py` | `DiscogsAdapter`: iterparse over the masters XML, year 0 as missing, joins only between artists, parquet cache. |
| `data/musicbrainz.py` | `MusicBrainzAdapter`: ten core tables read positionally through DuckDB with fixed projections (release is `(id, release_group)` only), first-release year from release events (ADR 0002), truth links from master URLs. |
| `data/truth.py` | truth links in their own frame with the statuses dead, out of scope, unsampled, in sample; the audit block. |
| `data/sample.py` | deterministic membership hash, solved per-side thresholds, unlinked share, content hashes for the reproducibility gate. |
| `data/contracts.py` | pure contract checks (grain, id format, year range, null rates) returning count-only reports. |
| `features/normalize.py` | section 2.3 in full plus the various-artists canonical token (ADR 0004); the one normaliser. |
| `features/blocking.py` | the five blocking keys, union of blocks in DuckDB, per-A cap with counted overflow, pair completeness per key. |
| `features/pairs.py` | `PAIR_FEATURES` in fixed order, rapidfuzz similarities on the normalised forms, nullable year. |
| `eval/split.py` | folds by the A record's hash (ADR 0003); pairs and truth inherit A's fold. |
| `eval/methods_card.py` | renders `docs/METHODS_CARD.md` from artifacts; byte-stable. |
| `models/labels.py` | truth sets per labelled A record; pair labels (1, 0, or unlabelled). The only place the truth table meets the pairs besides the evaluator. |
| `models/exact.py`, `models/rules.py`, `models/learned.py` | the three methods: nothing fitted; fixed weights with thresholds searched on fit-fold decisions; gradient boosting on fit-fold labelled pairs with isotonic calibration on the calibrate fold. |
| `models/tiering.py` | tier thresholds, ambiguity gap, review-cost constants and `decide`: one decision per A record. |
| `models/registry.py` | manifest and method version records. |
| `eval/evaluator.py` | test-fold metrics at A-record grain over labelled A records; unverified accepts; decision- and pair-level calibration; confusion. |
| `eval/review_cost.py` | the accept-threshold sweep and cost curve. |
| `pipeline/methods.py` | the Phase 4 stage: fit, decide, mapping exhibits (ADR 0005), evaluate, sweep, too-good-to-be-true rule. |
| `pipeline/match.py` | `make full`: acquire, load both sides, truth, sample, contracts, manifest and truth audit, then block, split and pair features (`data/pairs/`), with per-stage wall time, `data/` size, free disk and peak RSS recorded in `manifest.json#runtime`, then the methods stage (`pipeline/methods.py`). |
| `citations.py` | the number checker's rules, shared verbatim with demo 1. |
| `decision_lab/` | the Decision Lab (ADR 0006, 0007): `policy.py` (the one pure policy specification, mirrored in the app), `fixtures.py` (shared canonical fixtures), `contracts.py` (schemas, canonical JSON, allowlist, id and link validation), `snapshot.py`, `cases.py`, `replay.py`, `synthetic.py`, `ledger.py`, `export.py`, `cli.py` (`make lab-export`, `make lab-check`). `docs/DECISION_LAB.md` has the data flow and contracts. |

## Artifacts `artifacts/`

Committed, schema-validated (`artifacts/schemas/`), identifiers and numbers only:
`manifest.json`, `truth_audit.json`, `contracts.json`, `blocking_report.json`, `split.json`,
`methods/<method_version>.json`, `eval_<method_version>.json`, `review_sensitivity.json` and the
test-fold mapping exhibits `mapping/mapping_<method_version>.test.csv.gz` (ADR 0005).

## Decision Lab exports `artifacts/lab/`

Built from the committed artifacts by `entity_resolution.decision_lab` (owner-run stages add the
replay bundles and local case labels from the hash-verified `data/` inputs), schema-validated
(`artifacts/schemas/lab_*.schema.json`), identifiers and numbers only: `manifest.json`,
`snapshot.json`, `cases.json`, `case_selection.json`, `replay/replay_<m>.json` and
`replay/replay_<m>.test.csv.gz`. `make lab-check` recomputes what it can and hash-checks the
rest without rewriting anything.

## Warehouse `dbt/`

Bronze reads only committed artifacts through `read_json_auto`, so `dbt build` runs in CI with
no download. Families that do not exist yet build as empty typed relations (`files_exist`).
Silver flattens the artifacts into long, grain-enforced tables (`slv_eval_folds`,
`slv_eval_metrics`, `slv_mapping` deduplicated at `(a_id, method_version)`,
`slv_tier_thresholds`, `slv_calibration`); gold is the contracted marts the site reads:
`dim_source`, `dim_method_version`, `fct_mapping` (test-fold grain, ADR 0005),
`fct_review_queue`, `fct_review_floor`, `fct_eval_metrics`, `fct_blocking`, `fct_calibration`.
`brz_lab_case_selection` and `brz_lab_cases` read the lab exports; `fct_lab_case_evidence`
(case × method grain, projected from `fct_mapping`) and `fct_lab_case_comparison` (case grain)
are reconciled to the bundle by `assert_lab_case_evidence_reconciles_to_bundle`; the
`decision_lab` exposure lists what the lab depends on.
`assert_marts_reconcile_to_eval_artifacts` proves gold equals the artifacts; the other custom
tests hold the tier partition, unit-interval shares, recall not above pair completeness, one
accept per A record, block keys on every decided pair and the review-cost arithmetic; two dbt
unit tests cover the mapping deduplication and the cost arithmetic. `export_gold` writes CSV and
JSON to `docs/site/data/` for the Pages site.

## Site

`docs/site/index.html` is plain HTML with inline SVG drawn by a small script that reads only
`data/<gold model>.json`; no number is typed into the page (the number checker covers
`docs/site/`, and `tests/test_site.py` checks the wiring). `pages.yml` builds the warehouse,
exports, and publishes the page with the dbt docs under `/dbt/`.

## Decision Lab app `apps/decision-lab/`

React, TypeScript and Vite, built at `/entity-resolution/lab/` with hash routing so direct loads
work on Pages; `scripts/sync-data.mjs` copies `artifacts/lab/` into `public/data/`;
`src/lib/policy.ts` mirrors `decision_lab/policy.py` and is tested against the same fixtures;
`src/lib/ledger.ts` keeps the append-only review events in the browser, namespaced by snapshot.
Vitest for the library, Playwright for the journeys; `pages.yml` copies `dist/` to `site/lab/`.

## Phase 1 profiler

`scripts/profile_sources.py` downloads the dumps (free disk checked first), stream-extracts the
listed MusicBrainz tables, pages Wikidata, writes `artifacts/profile/<source>.json` (aggregates,
hashes and pattern codes only, schema `profile.schema.json`) and renders `docs/PROFILE.md`;
`render --check` fails when the rendered block is stale.

## Checks

`scripts/check_numbers.py` (every number in README, FINDINGS, METHODS_CARD, PROFILE,
REPRODUCIBILITY, the ADRs and the site cites an artifact key and matches it), `scripts/render_findings.py --check`
(the results and review-floor tables are rendered from the artifacts), `scripts/check_model_card.py` (the card equals a fresh render
and carries no placeholder), `scripts/check_dbt_descriptions.py` (every model, column, source
and exposure described), `scripts/smoke.sh` (all of it from a fresh clone, plus `make lab-check`). The lab adds
`make lab-check` (export staleness, hashes, allowlist, replay re-verification), `make lab-test`
(pytest lab modules, type check, lint, Vitest), `make lab-build` and `make lab-verify`
(Playwright).

## Workflows

`ci.yml` on every push and pull request (offline: lint, tests, warehouse, exports, docs checks,
`lab-check`, smoke from a fresh clone, and a `lab` job that type-checks, unit-tests, builds and
browser-tests the app); `verify.yml` on dispatch checks the committed artifacts alone
(schemas, exhibit hashes, the manifest hash the evaluation ran against, warehouse
reconciliation, docs citations); `pages.yml` publishes the site, the dbt docs and the lab (`site/lab/`) on push to `main`. The full build is owner-run (`docs/REPRODUCIBILITY.md`).
