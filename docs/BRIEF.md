# Build brief — `entity-resolution`

Open-data project that builds a hybrid SQL/Python record-linkage pattern on music catalogue data with labelled ground truth, so precision, recall, pair completeness and calibration are measured rather than asserted, and the difference between coverage and accuracy is shown with numbers.

This file is the implementation contract for the repo. Read it fully before any phase. It lives at `docs/BRIEF.md` and has an amendments log at the bottom; the log is the only part that changes after Phase 0.

---

## 1. Hard rules (non-negotiable)

1. **Real open data only.** Every source must carry an explicit, verbatim open licence recorded in `docs/DATA_SOURCES.md` with the URL it was read from and the date. Unstated licence = source dropped. Approved: Discogs monthly data dumps (CC0), MusicBrainz core dump `mbdump.tar.bz2` (CC0), Wikidata (CC0). Nothing else without an ADR.
2. **No raw rows in the tree.** Committed data is limited to: aggregates, hashes, source-native identifiers, scores, tiers, and JSON artifacts. Titles, artist credits and any other record attributes never enter git. `data/` is git-ignored; `.gitignore` is checked in CI.
3. **$0 runtime.** DuckDB, dbt-core, uv, pytest, rapidfuzz, scikit-learn, GitHub Actions, GitHub Pages. No paid services, no API keys, no secrets, no LLM in the loop. Third-party endpoints used only where a dump is impossible (Wikidata SPARQL), with a User-Agent, backoff, and a cached response hash in the manifest.
4. **Evidence-first.** No number appears in README, docs, dbt descriptions or model card unless read from a committed artifact under `artifacts/` and referenced by its key. `scripts/check_numbers.py` (ported from demo 1's convention) fails CI when a documented number has no artifact key.
5. **One normalisation/feature module.** `entity_resolution/features/` is the only place names are normalised or pair features computed. Blocking, rules, learned model, evaluation and dbt exports all call it. `FEATURE_VERSION` is a constant and travels into every artifact.
6. **Leakage discipline.** Anything fitted (thresholds, classifier, calibrator) is fitted on its fold only. Truth identifiers never enter the matcher. Proven by tests on the real sample, not on fixtures.
7. **Phase gates.** Before each phase: print a plan (files to touch, tests to add, artifacts to produce) and wait for approval. After each phase: one conventional commit locally, then the checkpoint (section 8). Never push. Never rewrite history.
8. **Depart loudly.** Any deviation from this brief gets an ADR in `docs/adr/NNNN-*.md` (template `0000-template.md`) and a line in the amendments log, and is named in the checkpoint. Silent deviation is the failure mode.
9. **Hard stop after profiling.** Phase 1 ends with a stop-and-present. No sampling, matching or modelling code is written until the owner has chosen side A and sample scope.
10. **Personal data.** No user-level fields exist in these sources; if any appear (Discogs submitter names, MB editor ids in supplementary dumps) they are never loaded. Artist credits are work attributes and stay in `data/`, never in git.
11. **Honest limitations.** `docs/FINDINGS.md` has a Limitations section with specific, numbered limitations. "Unlinked ≠ non-match" and "recall is against labelled pairs only" are mandatory entries.
12. **Scope.** v1 = pipeline + artifacts + dbt project + docs site + README. No frontend, no API, no active learning, no third source. Ideas go to `docs/ROADMAP.md`.

---

## 2. Target design

### 2.1 Entities and sources

The entity is an album-level work: a Discogs **master** on side B; a MusicBrainz **release group** (candidate #1) or a Wikidata **album item** (candidate #3) on side A. Side A is decided at the Phase 1 gate. All code takes side A as a `SourceAdapter` so the decision is a config value, not a rewrite.

| Side | Source | Fields loaded | Native id |
|---|---|---|---|
| B | Discogs `discogs_YYYYMMDD_masters.xml.gz` (streamed, never fully materialised) | `title`, `artists[].name` joined with the join fields as printed, `year`, `genres`, `main_release` | `master_id` (int) |
| A (#1) | MusicBrainz `mbdump.tar.bz2`, tables only: `release_group`, `release_group_meta`, `artist_credit`, `release_group_primary_type`, `l_release_group_url`, `url`, `link`, `link_type` | `name`, `artist_credit.name`, `first_release_date_year`, `primary_type` | `release_group.gid` (UUID) |
| A (#3) | Wikidata SPARQL: items with P1954 | `label@en` (fallback any), `P175` performer label(s), `P577` year, `P31` | `QID` |

Truth links: (#1) `l_release_group_url → url.url` matching `^https?://(www\.)?discogs\.com/master/(\d+)`; (#3) `P1954`. Truth is loaded into a separate table and **never joined to the matcher's input**.

Both candidates are profiled in Phase 1. Sample scope (whole dump vs a slice) is decided at the gate from the profile numbers.

### 2.2 Sample design

- Deterministic: membership = `sha256(source || native_id)` compared to a threshold recorded in `artifacts/manifest.json`; re-running on the same dump reproduces the sample byte-for-byte.
- Composition: all truth-linked pairs in scope + hash-selected unlinked records on both sides, so the sample's linked share is realistic and coverage ≠ accuracy is visible. The unlinked share is a manifest parameter, chosen at the gate from the profile.
- Truth pairs whose A or B record falls outside the sample are counted as `truth_unsampled` in `artifacts/truth_audit.json` and excluded from evaluation. Truth links whose Discogs master id is absent from the current dump (merged/deleted masters) are counted as `truth_dead`.
- `manifest.json` records: dump filenames, sizes, sha256, download URLs, licence URLs, sample rule, thresholds, counts per side, `FEATURE_VERSION`, code commit.

### 2.3 Normalisation (`features/normalize.py`)

Pure functions, unit-tested, no I/O. Applied identically to both sides.

- Unicode NFKD → strip combining marks → casefold → replace `&` with `and` → strip punctuation → collapse whitespace.
- Artist credit: strip Discogs numeric disambiguators `(2)`, `(3)`; reorder `"Beatles, The"` → `"the beatles"`; then drop a leading article from a fixed list (`the`, `a`, `an`, `los`, `las`, `les`, `die`, `der`, `das`) — the pre-drop form is kept as `artist_norm_full`.
- Title: drop bracketed edition qualifiers from a fixed list (`remaster`, `deluxe`, `anniversary`, `edition`, `expanded`, `reissue`) into `title_qualifiers`; keep original in `title_norm_full`.
- Flags: `is_various_artists` (credit in `{various, various artists, va, v/a}`), `is_self_titled` (title_norm == artist_norm), `year_missing`.
- Tokens: `title_tokens`, `artist_tokens` (sorted, deduplicated), and double-metaphone of the first token of each.

### 2.4 Blocking (`features/blocking.py`)

Union of independent keys; every candidate pair records which keys produced it.

| key | definition |
|---|---|
| `k_title3` | first three title tokens joined |
| `k_artist_year` | `artist_norm` + year ± 1 (three keys emitted per record) |
| `k_title_sorted` | hash of sorted title tokens |
| `k_phonetic` | metaphone(first title token) + metaphone(first artist token) |
| `k_self_titled` | `artist_norm` when `is_self_titled` |

- Per-A candidate cap 200; overflow counted in `artifacts/blocking_report.json` (never silently truncated).
- Various-artists records are blocked on title keys only (artist keys would create a mega-block).
- `blocking_report.json`: per-key and union pair completeness (share of *sampled* truth pairs recovered), candidate counts, reduction ratio, cap overflow count, largest block sizes.

### 2.5 Split (`eval/split.py`)

Group-aware by side-B id: `sha256(master_id) mod 100` → `fit` [0,60), `calibrate` [60,80), `test` [80,100). Every candidate pair and every truth pair inherits the fold of its B record. Anything fitted sees only `fit`; calibration only `calibrate`; every reported metric comes from `test`. Fold assignment is written to `artifacts/split.json` (counts per fold, hash rule, seed-free by construction).

### 2.6 Pair features (`features/pairs.py`)

Computed for every candidate pair, one function, returns a fixed column list published as `PAIR_FEATURES`:

`title_ratio`, `title_partial`, `title_token_sort`, `title_token_set`, `title_jw`, `artist_ratio`, `artist_token_set`, `artist_jw`, `artist_full_exact`, `title_exact_norm`, `year_diff` (nullable), `year_either_missing`, `both_va`, `title_len_diff`, `n_block_keys`, `qualifier_mismatch`.

### 2.7 Methods (`models/`)

All three share blocking, features, folds and the tiering step, so the results table is a fair comparison.

| method_version | definition | fitted on |
|---|---|---|
| `exact_v1` | accept iff `title_exact_norm and artist_full_exact and year_diff in {0, null}` | nothing |
| `rules_v1` | `score = 0.45·title_token_set + 0.35·artist_token_set + 0.20·year_agreement` (`year_agreement` = 1 if diff 0, 0.5 if 1, 0.25 if missing, else 0); weights fixed a priori and written in the method version record; accept/review thresholds chosen on `fit` by maximising F1 with a review band around the crossover | thresholds: `fit` |
| `learned_v1` | `HistGradientBoostingClassifier` on `PAIR_FEATURES`, class weight balanced, fixed hyperparameters recorded; isotonic calibration on `calibrate` | model: `fit`; calibrator: `calibrate` |

Labels for the classifier: candidate pair ∈ truth → 1, else 0, within `fit` only. Pairs involving a B record that has a truth link to a *different* A are hard negatives and are kept.

### 2.8 Decision and tiering (`models/tiering.py`)

- One A record gets at most one accepted B: for each A take the top-probability candidate; if the top-2 gap < `AMBIGUITY_GAP` (0.10) the pair goes to `review` regardless of probability.
- Tiers on calibrated probability (`rules_v1` uses its raw score with thresholds from `fit`; its calibration is reported to show why calibration matters): `auto_accept` p ≥ 0.95, `review` 0.50 ≤ p < 0.95, `reject` p < 0.50.
- Review cost: `REVIEW_COST_UNITS = 1.0` per review row; `FALSE_ACCEPT_COST_RATIO ∈ {1, 5, 20}`. `artifacts/review_sensitivity.json` sweeps the accept threshold from 0.50 to 0.99 and reports queue size, expected false accepts (from test precision at that threshold) and total cost per ratio. The chosen thresholds are reported next to the curve, not hidden inside it.

### 2.9 Evaluation artifacts (`eval/evaluator.py`)

One `artifacts/eval_<method_version>.json` per method, schema-validated, containing: `input` (manifest hash, `FEATURE_VERSION`, code commit), `fold_counts`, and on **test only**:

- `pair_completeness` (from blocking, union and per key)
- `precision`, `recall_labelled`, `f1` at `auto_accept`; the same at `auto_accept ∪ review` (upper bound if every review were resolved correctly)
- `recall_overall` = recall_labelled × pair_completeness (blocking loss included; stated as such)
- `coverage` = accepted A records / all A records in test fold; `coverage_all_folds` reported separately and labelled as not an accuracy measure
- `tier_shares` (partition of all A records in test)
- `calibration`: 10-bin reliability table, ECE, Brier
- `confusion` at each tier boundary
- `metric_definitions`: prose for every key

`artifacts/truth_audit.json`: link counts, `truth_dead`, `truth_unsampled`, one-to-many rates on each side, duplicate truth pairs, sample of 20 hashed pair ids per anomaly class.

`artifacts/mapping/mapping_<method_version>.csv`: one row per A record with a non-reject decision — `a_id, b_id, method_version, feature_version, score, probability, tier, block_keys, top2_gap, fold, run_id, decided_at_utc`. Identifiers and numbers only; no attributes.

### 2.10 dbt project (`entity_resolution_dbt`, DuckDB)

Bronze reads only committed artifacts (`read_json_auto`, `read_csv_auto`), so `dbt build` runs in slim CI without any download.

| layer | models |
|---|---|
| bronze | `brz_manifest`, `brz_truth_audit`, `brz_blocking_report`, `brz_split`, `brz_eval_artifacts`, `brz_review_sensitivity`, `brz_mapping`, `brz_method_versions` |
| silver | `slv_eval_folds`, `slv_eval_metrics` (long: method × fold × metric × value), `slv_mapping` (typed, deduplicated at `(a_id, method_version)`), `slv_tier_thresholds` |
| gold | `dim_source`, `dim_method_version`, `fct_mapping` (the auditable table, grain `(a_id, method_version)`), `fct_review_queue` (grain `(method_version, threshold, cost_ratio)`), `fct_eval_metrics` (wide, one row per method), `fct_blocking` (one row per block key) |

Every model and column has a description; `scripts/check_dbt_descriptions.py` enforces it. `export_gold` writes CSV/JSON to `docs/site/data/` for the Pages site.

### 2.11 Tests

Python (`tests/`, `pytest`, all offline against committed artifacts or inline fixtures):

- `test_normalize.py`: every rule in 2.3 with edge cases (`"Beatles, The"`, `"Prince (2)"`, `"Various"`, diacritics, self-titled).
- `test_blocking.py`: keys emitted as specified; VA records skip artist keys; cap overflow counted not dropped.
- `test_pairs.py`: `PAIR_FEATURES` order stable; nullable year handled; symmetric where it should be.
- `test_split.py`: fold assignment is a pure function of B id; truth and candidate pairs inherit B's fold.
- `test_features_no_leakage.py` (real sample, skipped with a clear reason when `data/` is absent): no `test` B id appears in any fitted object's training index; rules thresholds equal the value recomputed from `fit` alone; calibrator's fit index ⊆ `calibrate`; recomputing 200 random real pairs' features from raw fields matches the stored features exactly.
- `test_tiering.py`: tiers partition; ambiguity rule fires; thresholds monotone.
- `test_evaluator.py`: metrics on a hand-built 12-pair fixture match hand-computed values; `recall_overall == recall_labelled × pair_completeness`.
- `test_contracts.py`: grain uniqueness, id format, year range [1900, current+1], null rates, injected violations detected.
- `test_artifact_schemas.py`: every committed artifact validates against `artifacts/schemas/*.schema.json`.
- `test_no_raw_rows.py`: greps `git ls-files` for forbidden attribute columns and fails if any CSV under the tree has a `title`/`artist`/`name` column.
- `test_project_config.py`, `test_loader.py`, `test_interfaces.py`: kept from chassis, reworked.

dbt (`dbt/tests/`):

- Generic: `unique`, `not_null`, `accepted_values` on tiers, `relationships` mapping → method versions.
- `assert_tiers_partition`: tier shares sum to 1 ± 1e-9 per method.
- `assert_shares_in_unit_interval`: every share/probability in [0, 1].
- `assert_recall_not_above_pair_completeness`.
- `assert_accepted_subset_of_candidates`.
- `assert_marts_reconcile_to_eval_artifacts`: `fct_eval_metrics` equals the JSON values to 1e-9.
- `assert_baseline_reconciles_to_eval_artifacts`: `exact_v1` and `rules_v1` rows present and reconciled.
- `assert_one_accept_per_a_record`.
- dbt unit tests on `slv_mapping` deduplication and `fct_review_queue` cost arithmetic.

### 2.12 CI and workflows

`ci.yml` (every push/PR, target < 10 min): `uv sync --frozen` → `ruff check` + `ruff format --check` → `sqlfluff lint` → `pytest` (real-data tests skip) → `dbt deps && dbt build` against committed artifacts → `python scripts/check_dbt_descriptions.py` → `python scripts/check_numbers.py` → `python scripts/check_model_card.py` → `bash scripts/smoke.sh` from a fresh clone in a temp dir.

`full-build.yml` (`workflow_dispatch` + monthly schedule, may run 1–2 h): download dumps → verify sha256 vs manifest (fail on mismatch unless `refresh=true` input) → run `make full` → run the real-data tests → upload `artifacts/` as a workflow artifact and print a diff against committed artifacts. Commits nothing; the owner reviews and commits. Same pattern as demo 1's full build.

`pages.yml`: builds `dbt docs generate` + `docs/site/` and deploys to GitHub Pages on push to `main`.

### 2.13 Docs

- `README.md`: problem, why ground truth matters, results table (every cell keyed), how coverage differs from precision in this data, how to run, what is and isn't proven, limitations pointer, licence attributions.
- `docs/FINDINGS.md`: narrative with every number keyed; Limitations numbered.
- `docs/METHODS_CARD.md` (renamed from `MODEL_CARD.md`): generated by `scripts/check_model_card.py --write` from artifacts; byte-stable on rerun.
- `docs/DATA_SOURCES.md`: verbatim licence text and URLs, dump dates, what is loaded, what is deliberately not.
- `docs/ARCHITECTURE.md`, `docs/REPRODUCIBILITY.md` (clean-clone steps, expected runtimes measured), `docs/ROADMAP.md`, `docs/adr/`.

---

## 3. Phases

Each phase: plan → approval → build → tests green → one commit → checkpoint. Do not start the next phase without approval.

### Phase 0 — Chassis repair
Resolve every entry in the dangling-reference list (`grep` from the strip commit) so nothing references serving, periods, targets, drift, snapshots, HF, Vercel or MotherDuck. Rework copier placeholders: `record`/`record_id`/`batch`/`source` names become the vocabulary in section 2; `interfaces.py` defines `SourceAdapter`, `Record`, `CandidatePair`, `Decision`. `pyproject.toml` extras reduced to `dev`; `Makefile` targets `setup lint test dbt full smoke docs`. `ci.yml` and `scheduled.yml → full-build.yml` reshaped per 2.12 with the full build stubbed. `MODEL_CARD.md → METHODS_CARD.md`. `.gitignore` covers `data/`, `*.xml.gz`, `*.tar.bz2`, `.venv`.
**Done when:** `make lint test dbt smoke` passes on a tree with no data and empty-but-valid artifacts; `git grep -niE "hf_|vercel|motherduck|serve\b|period_key|target_rules|asof|drift|snapshot"` returns hits only under `docs/adr/`; checkpoint lists the placeholder mapping used.

### Phase 1 — Acquire and profile both candidates (HARD STOP)
Write `scripts/profile_sources.py` only. Download Discogs masters (record URL, size, sha256, dump date); stream-count masters, field completeness, year distribution, VA share, numeric-disambiguator share, duplicate `(title_norm, artist_norm)` rate. For #1: stream-extract only the listed tables from `mbdump.tar.bz2` (record wall time and disk), count release groups by primary type, count Discogs master links, one-to-many rates, dead-id rate against the masters dump. For #3: SPARQL count of P1954 items and how many have performer + year; note WDQS timeouts. Write `artifacts/profile/<source>.json` (aggregates only) and `docs/PROFILE.md` with a side-by-side table and 15 example name-convention differences shown as *normalised hashes plus a one-line description of the pattern*, never the raw strings.
**Done when:** the profile artifacts validate and `docs/PROFILE.md` ends with a recommendation section stating, for each candidate: truth-pair count in scope, acquisition cost (time, GB), truth quality (dead/one-to-many), and a proposed sample scope with expected pair counts. Then **stop and present**. The owner decides side A and sample scope; the decision is recorded as ADR 0001.

### Phase 2 — Loaders, contracts, sample, truth audit, bronze
`SourceAdapter` implementations for Discogs and the chosen side A; streaming parsers with a local parquet cache in `data/`; contracts as pure functions returning reports; deterministic sample per 2.2; `manifest.json`, `truth_audit.json`; bronze models reading the artifacts.
**Done when:** sample reproduces byte-for-byte on a second run; contracts pass on real data and detect injected violations in tests; `test_no_raw_rows.py` passes; `truth_audit.json` committed and its numbers appear nowhere else yet.

### Phase 3 — Normalisation, blocking, pair features, split
Sections 2.3–2.6 exactly; `blocking_report.json` and `split.json`; leakage test on real data.
**Done when:** union pair completeness is reported with per-key breakdown; cap overflow is a number, not a warning; `test_features_no_leakage.py` passes on the real sample; if union pair completeness < 0.95, the checkpoint says why and proposes a key — do not add keys silently.

### Phase 4 — Methods, calibration, tiering, mapping, evaluation
Sections 2.7–2.9. Fit order: rules thresholds on `fit`; classifier on `fit`; calibrator on `calibrate`; everything reported on `test`. Write `eval_*.json`, `calibration_*.json`, `review_sensitivity.json`, mapping CSVs, method version records. **Too-good-to-be-true rule:** if `learned_v1` test F1 exceeds `rules_v1` by more than 0.15, or any precision ≥ 0.995 on more than 1,000 pairs, stop and audit for leakage before the checkpoint.
**Done when:** all artifacts validate; every metric definition is written; the results table in the checkpoint cites keys; the ambiguity rule's effect on queue size is a number.

### Phase 5 — dbt silver/gold, tests, exports, site
Section 2.10–2.11 dbt parts; `export_gold`; dbt docs; `docs/site/` with a methods table, reliability plot and review-cost curve rendered from exported JSON with plain HTML + inline SVG (no build step).
**Done when:** `dbt build` green in slim CI with committed artifacts; all custom tests pass; exposures declared; site renders from a clean clone.

### Phase 6 — Findings, checker, docs, release
`FINDINGS.md`, `README.md`, `METHODS_CARD.md`, `REPRODUCIBILITY.md` with measured runtimes, `ROADMAP.md`, `check_numbers.py` wired into CI, full-build workflow exercised locally with `act` or documented as owner-run.
**Done when:** `check_numbers.py` passes with zero unkeyed numbers; Limitations has at least the mandatory entries plus every gap found in Phases 1–5; owner TODO list printed (push, enable Pages, run full build, tag `v0.1.0`).

---

## 4. Checkpoint format

Print after every phase commit, verbatim headings:

```
## Checkpoint — Phase N: <name>
Commit: <sha> <message>
### Changed
<files added / modified / deleted, grouped>
### Tests
<pytest summary>; <dbt build summary>; <checkers>
### Numbers (each with artifact key)
<metric> = <value>  [artifacts/<file>.json#<key>]
### Departures from brief
<ADR ids and one line each, or "none">
### Open questions for the owner
<numbered, or "none">
### Next phase plan
<files, tests, artifacts>
```

---

## 5. Definition of done (whole project)

- Every number in README, FINDINGS, METHODS_CARD and dbt descriptions traces to an artifact key; `check_numbers.py` is green.
- Slim CI green under 10 minutes; smoke test passes from a clean clone.
- Full build has run at least once and its artifacts are the committed ones.
- Results table shows `exact_v1`, `rules_v1`, `learned_v1` on the same test fold with pair completeness, precision, recall (labelled and overall), coverage, ECE, and review-queue size at the chosen thresholds.
- Limitations are honest and specific.
- Owner TODO explicit.

---

## 6. Amendments log

| date | phase | ADR | change |
|---|---|---|---|
| 2026-09-22 | — | — | Brief created. |
| 2026-09-22 | 0 | — | Chassis: Python pins move from `constraints.txt` to a committed `uv.lock` (`uv sync --frozen`); `constraints.txt` deleted. |
| 2026-09-22 | 1 | — | `check_numbers.py` measure words gain this domain's unit words (pairs, records, masters, release groups, links, keys, candidates, blocks, folds); demo 1's words kept so the scripts stay diffable. |
| 2026-09-22 | 1 | — | Phase 1 file list gains `entity_resolution/features/normalize.py` (section 2.3 in full) and `tests/test_normalize.py`, so the profiler uses the one normaliser (rule 5) instead of a second implementation. |
| 2026-09-22 | 1 | 0002 | MusicBrainz first-release year comes from the core tables `release`, `release_country`, `release_unknown_country` instead of `release_group_meta`, which is not in `mbdump.tar.bz2` (it ships in the derived archive with user ratings, CC BY-NC-SA). Table list in 2.1 amended. |
| 2026-09-23 | 1→2 | 0001 | Side A = MusicBrainz release groups. Sample scope (2.2): A = primary type Album only, B = all masters, every alive Album truth pair, unlinked share 0.50 per side; `truth_out_of_scope` added to the truth audit beside `truth_unsampled` and `truth_dead`; masters linked only from out-of-scope release groups stay as B distractors flagged `b_linked_out_of_scope`. |
| 2026-09-23 | 1→2 | 0001 | Evaluation scoping (2.7, 2.9): pairs whose A record has no truth link are scored but excluded from fit and calibration; precision, recall_labelled, f1 and calibration are over labelled A records only; accepts on unlabelled A records are reported as `unverified_accepts` (count, share), counted by coverage and not by the accuracy metrics. Unlinked B records stay in blocking. |
| 2026-09-23 | 3 | 0003 | Folds (2.5) are assigned by the A record: `sha256(a native id) mod 100`; every candidate pair and truth pair inherits A's fold; B may appear in any fold. Leakage test restated accordingly. |
| 2026-09-23 | 3 | 0004 | Various-artists credits normalise to one token (2.3); `FEATURE_VERSION` 0.2.0; Phase 2 stages re-run with counts asserted unchanged; Phase 1 profile kept as a dated 0.1.0 record. |
| 2026-09-23 | 4 | — | `rules_v1` thresholds (2.7) are searched on fit-fold A-record decisions (argmax per A, then sweep): `t_accept` maximises F1 over labelled fit-fold A records; `t_review` is the score below which the cumulative precision of those decisions falls under 0.50. |
| 2026-09-23 | 4 | — | `learned_v1` (2.7) is trained on fit-fold pairs of labelled A records only; isotonic calibration on calibrate-fold labelled pairs; reliability and ECE are reported on test-fold top-1 decisions of labelled A records, with the pair-level table secondary. |
| 2026-09-23 | 4 | — | Evaluation (2.9): an accept is correct if the accepted B is in the A record's truth set; `recall_labelled` = correct accepts over labelled test A records whose truth survived blocking; `recall_overall` = correct accepts over all labelled test A records; `pair_completeness_test` is computed on that same set so the product identity holds exactly. |
| 2026-09-23 | 4 | — | Too-good-to-be-true rule (Phase 4): `exact_v1` is expected to exceed 0.995 precision because most truth pairs are identical after normalisation; its audit is the leakage test plus a check that no truth column reaches the method. The hard stop stays for `rules_v1` and `learned_v1`. |
| 2026-09-23 | 4 | 0005 | Mapping table scope (2.9, 2.10): the committed exhibit is `artifacts/mapping/mapping_<method_version>.test.csv.gz` (test fold, non-reject decisions, ids and numbers only); the full mapping is a `make full` output under `data/` and a workflow artifact; `fct_mapping` is test-fold grain. |
| 2026-09-23 | 5 | — | `review_sensitivity.json` (2.8) gains a review-floor sweep per method: for floors 0.05 to 0.95, the review queue, its share of the test fold and recall with review, so a queue budget can be priced. No new method. |
