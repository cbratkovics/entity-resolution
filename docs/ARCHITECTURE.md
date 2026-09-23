# Architecture

The design is `docs/BRIEF.md` section 2; this file says where each piece lives.

## Package `entity_resolution/`

| module | role |
|---|---|
| `config.py` | `PROJECT`: sides, method versions, folds, tiers, paths. `side_a` is `None` until ADR 0001. |
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
| `eval/evaluator.py` | the evaluation artifact writer and metric definitions. Metric computation in Phase 4. |
| `eval/methods_card.py` | renders `docs/METHODS_CARD.md` from artifacts; byte-stable. |
| `models/labels.py` | truth sets per labelled A record; pair labels (1, 0, or unlabelled). The only place the truth table meets the pairs besides the evaluator. |
| `models/exact.py`, `models/rules.py`, `models/learned.py` | the three methods: nothing fitted; fixed weights with thresholds searched on fit-fold decisions; gradient boosting on fit-fold labelled pairs with isotonic calibration on the calibrate fold. |
| `models/tiering.py` | tier thresholds, ambiguity gap, review-cost constants and `decide`: one decision per A record. |
| `models/registry.py` | manifest and method version records. |
| `eval/evaluator.py` | test-fold metrics at A-record grain over labelled A records; unverified accepts; decision- and pair-level calibration; confusion. |
| `eval/review_cost.py` | the accept-threshold sweep and cost curve. |
| `pipeline/methods.py` | the Phase 4 stage: fit, decide, mapping exhibits (ADR 0005), evaluate, sweep, too-good-to-be-true rule. |
| `pipeline/match.py` | `make full`: acquire, load both sides, truth, sample, contracts, manifest and truth audit, then block, split and pair features (`data/pairs/`), with per-stage wall time, `data/` size, free disk and peak RSS recorded in `manifest.json#runtime`. then the methods stage (`pipeline/methods.py`). |
| `citations.py` | the number checker's rules, shared verbatim with demo 1. |

## Artifacts `artifacts/`

Committed, schema-validated (`artifacts/schemas/`), identifiers and numbers only:
`manifest.json`, `truth_audit.json`, `contracts.json`, `blocking_report.json`, `split.json`,
`methods/<method_version>.json`, `eval_<method_version>.json`, `review_sensitivity.json` and the
test-fold mapping exhibits `mapping/mapping_<method_version>.test.csv.gz` (ADR 0005).

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
