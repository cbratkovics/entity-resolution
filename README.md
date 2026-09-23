# Entity resolution: Discogs masters against MusicBrainz release groups

Record linkage between two open music catalogues, measured against labelled ground truth.

[Live site](https://cbratkovics.github.io/entity-resolution/) · [dbt docs](https://cbratkovics.github.io/entity-resolution/dbt/) · [Findings](docs/FINDINGS.md) · [Methods card](docs/METHODS_CARD.md) · [Brief](docs/BRIEF.md) · ![ci](https://github.com/cbratkovics/entity-resolution/actions/workflows/ci.yml/badge.svg)

## What the numbers say

- **Rules is the best single method at fixed tiers.** `rules_v1` auto-accepts with precision
  0.994615 and recall 0.930917 against labelled pairs, F1 0.961712; `learned_v1` trades recall
  for precision, 0.999344 at 0.849952, F1 0.918614; the exact rule stops at recall 0.760858.
  <!-- cite: artifacts/eval_rules_v1.json#metrics.at_auto_accept.precision; artifacts/eval_rules_v1.json#metrics.at_auto_accept.recall_labelled; artifacts/eval_rules_v1.json#metrics.at_auto_accept.f1; artifacts/eval_learned_v1.json#metrics.at_auto_accept.precision; artifacts/eval_learned_v1.json#metrics.at_auto_accept.recall_labelled; artifacts/eval_learned_v1.json#metrics.at_auto_accept.f1; artifacts/eval_exact_v1.json#metrics.at_auto_accept.recall_labelled -->
- **Unverified accepts are the coverage-versus-accuracy exhibit.** `rules_v1` auto-accepts 4,501
  unlabelled test-fold records, 0.093498 of its accepts, against 1,103 and 0.027062 for
  `learned_v1`; they lift coverage and are excluded from every accuracy figure.
  <!-- cite: artifacts/eval_rules_v1.json#metrics.unverified_accepts.count; artifacts/eval_rules_v1.json#metrics.unverified_accepts.share_of_accepts; artifacts/eval_learned_v1.json#metrics.unverified_accepts.count; artifacts/eval_learned_v1.json#metrics.unverified_accepts.share_of_accepts -->
- **Calibration is where `learned_v1` earns its place.** Its pair-level ECE on the test fold is
  0.000147 and its decision-level ECE 0.047858: the argmax over calibrated pair probabilities
  selects upward, so the tiers act on slightly overconfident numbers; the uncalibrated rules
  score sits at 0.402040 at pair level.
  <!-- cite: artifacts/eval_learned_v1.json#metrics.calibration.pair_level.ece; artifacts/eval_learned_v1.json#metrics.calibration.decision_level.ece; artifacts/eval_rules_v1.json#metrics.calibration.pair_level.ece -->

`docs/FINDINGS.md` carries the full argument with the review-budget table and the limitations.

## Overview

Discogs masters (side B) are matched to MusicBrainz release groups (side A, chosen after
profiling both candidates, ADR-0001). Because side A publishes its own links to Discogs, every
method here is scored on real labelled pairs: precision, recall against labelled pairs, pair
completeness of the blocking step, calibration of the probabilities, and the size of the human
review queue at the chosen thresholds. Coverage (how many records got a match) is reported
beside precision (how many of those matches are right), because in this data they are not the
same number.

**Status.** Complete for v1 (`docs/BRIEF.md` Phase 6): three methods evaluated on a held-out
test fold of labelled pairs, a dbt warehouse that reconciles to the artifacts, a docs site
rendered from the exported marts, and a findings document with numbered limitations.

## How this was built

An independent project on open data: no employer code or data is involved, and every source is
CC0 (`docs/DATA_SOURCES.md`). It was built with Claude Code under `docs/BRIEF.md`, a contract
with phase gates and checkpoints the owner reviewed at every phase, an ADR for every departure
([0001](docs/adr/0001-side-a-musicbrainz-and-album-sample-scope.md),
[0002](docs/adr/0002-musicbrainz-first-release-year-from-core-tables.md),
[0003](docs/adr/0003-fold-by-a-record.md),
[0004](docs/adr/0004-various-artists-canonical-token.md),
[0005](docs/adr/0005-mapping-table-scope.md)), and CI that fails on any number in the docs
without an artifact citation whose value matches. That is why a Claude model is listed as a
co-author on the commits.

## Pipeline

```mermaid
flowchart LR
    dumps["Discogs and MusicBrainz dumps"] --> adapters["Source adapters"]
    adapters --> sample["Deterministic sample and truth audit"]
    sample --> blocking["Blocking"]
    blocking --> features["Pair features"]
    features --> methods["exact / rules / learned methods"]
    methods --> artifacts["Committed artifacts"]
    artifacts --> bronze["dbt bronze"] --> silver["dbt silver"] --> gold["dbt gold"]
    gold --> site["Docs site"]
```

## Why ground truth matters

A matcher that reports "linked most records" has said nothing about how many of those links
are right. This project separates the two claims: `coverage` is a volume measure, `precision`
is an accuracy measure, and `recall_labelled` is recall against the pairs the source itself
labels, stated as such because an unlinked record is not evidence of a non-match. Every number
is read from a committed artifact and cited by key; `scripts/check_numbers.py` fails CI when a
number in this file has no citation or does not match its artifact.

## Methods compared

| method_version | definition | fitted on |
|---|---|---|
| `exact_v1` | normalised title and full artist credit equal, year equal or missing | nothing |
| `rules_v1` | fixed-weight score over title, artist and year agreement; thresholds chosen on the `fit` fold | thresholds: `fit` |
| `learned_v1` | gradient-boosted classifier on the pair features; isotonic calibration on the `calibrate` fold | model: `fit`; calibrator: `calibrate` |

All three share the same blocking, pair features, folds and tiering step, so the comparison is
fair. Every reported metric comes from the `test` fold.

## Results

<!-- generated:results start -->
| method | pair completeness (test) | precision | recall (labelled) | recall (overall) | F1 | coverage | unverified accepts | review queue | ECE (decisions) |
|---|---|---|---|---|---|---|---|---|---|
| `exact_v1` | 0.963884 | 0.998733 | 0.760858 | 0.733379 | 0.863717 | 0.378315 | 1,009 (0.027622 of accepts) | 207 | 0.093735 |
| `rules_v1` | 0.963884 | 0.994615 | 0.930917 | 0.897296 | 0.961712 | 0.498566 | 4,501 (0.093498 of accepts) | 25,076 | 0.012978 |
| `learned_v1` | 0.963884 | 0.999344 | 0.849952 | 0.819255 | 0.918614 | 0.422113 | 1,103 (0.027062 of accepts) | 6,016 | 0.047858 |

Keys, per method, in `artifacts/eval_<method_version>.json#metrics`: `pair_completeness_test`, `at_auto_accept.precision`, `at_auto_accept.recall_labelled`, `recall_overall`, `at_auto_accept.f1`, `coverage`, `unverified_accepts.count`, `unverified_accepts.share_of_accepts`, `ambiguity_rule.review_queue`, `calibration.decision_level.ece`. Every metric is on the test fold; precision, recall and F1 are over labelled A records; coverage counts every test-fold A record.
<!-- generated:results end -->

## Coverage is not precision

Half of the sampled A records carry no MusicBrainz link to Discogs, so nothing they are matched
to can be verified. <!-- cite: artifacts/manifest.json#sample.thresholds.a.unlinked_share_actual -->
Coverage counts them; precision does not. `rules_v1` auto-accepts 4,501
unlabelled test-fold records, 0.093498 of its accepts, and `learned_v1` 1,103, 0.027062 of its
accepts; those accepts lift coverage and are excluded from every accuracy figure by
construction. <!-- cite: artifacts/eval_rules_v1.json#metrics.unverified_accepts.count; artifacts/eval_rules_v1.json#metrics.unverified_accepts.share_of_accepts; artifacts/eval_learned_v1.json#metrics.unverified_accepts.count; artifacts/eval_learned_v1.json#metrics.unverified_accepts.share_of_accepts -->
`docs/METHODS_CARD.md` carries the method records and metric definitions; the site renders the
same figures as charts.

Site: https://cbratkovics.github.io/entity-resolution/ (published by `pages.yml` once Pages is enabled).

## How to run

```
make setup    # uv sync --frozen (Python 3.12, runtime + dev)
make lint     # ruff check, ruff format --check, sqlfluff
make test     # pytest; real-data tests skip when data/ is absent
make dbt      # dbt build against the committed artifacts, docs generate, description check
make docs     # regenerate docs/METHODS_CARD.md and run the number and placeholder checks
make smoke    # all of the above from a fresh clone in a temp dir
make full     # the full build over the real dumps (network; about an hour cold on the owner's machine, see docs/REPRODUCIBILITY.md)
```

`data/` holds the dumps and every derived row and is git-ignored. Committed data is limited
to aggregates, hashes, native identifiers, scores, tiers and JSON artifacts. The full build is
owner-run: it needs about `14 GiB` of disk for the dumps and extracted tables and about `10 GiB`
of memory in the feature stage (`docs/REPRODUCIBILITY.md`); the `verify` workflow checks the
committed artifacts without it.

## What is and is not proven

- Proven by tests on the committed tree: every artifact validates against its schema, the
  warehouse reconciles to the artifacts to 1e-9, the mapping exhibits match the hashes in the
  method records, no record attribute is tracked by git, and every number in the docs cites an
  artifact key whose value matches.
- Proven on the real sample, on the owner's machine: fitted objects saw only their folds (no
  test-fold A record in any fitted index; thresholds recompute from the fit fold alone), two
  full runs are byte-identical, and 200 stored pairs recompute exactly from the raw fields.
- Not proven: anything about records outside the Album scope or without a label (unlinked is
  not non-match), the stability of the learned model under refitting, and the equality of the
  derived first-release year with MusicBrainz's own. `docs/FINDINGS.md` lists every limitation.

## Data and licences

Discogs monthly data dump (masters), CC0, from data.discogs.com; MusicBrainz core database
dump, CC0, from data.metabrainz.org; Wikidata (profiled, not used as a side), CC0. Verbatim
licence text, URLs, dump dates and what is loaded from each are in `docs/DATA_SOURCES.md`.
The code is MIT licensed (`LICENSE`); the data is CC0 as recorded in `docs/DATA_SOURCES.md`, stays
under `data/` and never enters git.
