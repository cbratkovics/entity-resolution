# Architecture

The design is `docs/BRIEF.md` section 2; this file says where each piece lives.

## Package `entity_resolution/`

| module | role |
|---|---|
| `config.py` | `PROJECT`: sides, method versions, folds, tiers, paths. `side_a` is `None` until ADR 0001. |
| `interfaces.py` | `SourceAdapter` protocol; `Record`, `TruthLink`, `CandidatePair`, `Decision` dataclasses. |
| `data/loader.py` | adapter registry; `FixtureAdapter` for offline tests. Real adapters arrive in Phase 2. |
| `data/contracts.py` | pure contract checks (grain, id format, year range, null rates) returning count-only reports. |
| `features/` | the one normalisation and pair-feature module; `FEATURE_VERSION`. Filled in Phase 3. |
| `eval/evaluator.py` | the evaluation artifact writer and metric definitions. Metric computation in Phase 4. |
| `eval/methods_card.py` | renders `docs/METHODS_CARD.md` from artifacts; byte-stable. |
| `models/registry.py` | manifest and method version records. |
| `models/tiering.py` | tier thresholds, ambiguity gap and review-cost constants. |
| `pipeline/match.py` | `make full` entry point; refuses to run until the pipeline exists. |
| `citations.py` | the number checker's rules, shared verbatim with demo 1. |
| `features/normalize.py` | section 2.3 in full: the one normaliser (rule 5); the profiler already calls it. |

## Artifacts `artifacts/`

Committed, schema-validated (`artifacts/schemas/`), identifiers and numbers only:
`manifest.json`, `methods/<method_version>.json`, `eval_<method_version>.json`, and from later
phases `truth_audit.json`, `blocking_report.json`, `split.json`, `review_sensitivity.json`,
`mapping/mapping_<method_version>.csv`.

## Warehouse `dbt/`

Bronze reads only committed artifacts through `read_json_auto`, so `dbt build` runs in CI with
no download. Families that do not exist yet build as empty typed relations (`files_exist`).
Silver flattens the artifacts into long, grain-enforced tables; gold is contracted marts the
site reads. `assert_marts_reconcile_to_eval_artifacts` proves gold equals the artifacts;
`export_gold` writes CSV and JSON to `docs/site/data/` for the Pages site.

## Phase 1 profiler

`scripts/profile_sources.py` downloads the dumps (free disk checked first), stream-extracts the
listed MusicBrainz tables, pages Wikidata, writes `artifacts/profile/<source>.json` (aggregates,
hashes and pattern codes only, schema `profile.schema.json`) and renders `docs/PROFILE.md`;
`render --check` fails when the rendered block is stale.

## Checks

`scripts/check_numbers.py` (every number in README, FINDINGS, METHODS_CARD and the ADRs cites
an artifact key and matches it), `scripts/check_model_card.py` (the card equals a fresh render
and carries no placeholder), `scripts/check_dbt_descriptions.py` (every model, column, source
and exposure described), `scripts/smoke.sh` (all of it from a fresh clone).

## Workflows

`ci.yml` on every push and pull request (offline); `full-build.yml` on dispatch and monthly
(downloads the dumps, runs `make full`, uploads artifacts, commits nothing); `pages.yml`
publishes the dbt docs and `docs/site/` on push to `main`.
