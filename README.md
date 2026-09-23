# entity-resolution

Record linkage between two open music catalogues, measured against labelled ground truth.

Discogs masters (side B) are matched to album-level works in a second open catalogue (side A:
MusicBrainz release groups or Wikidata album items; the choice is made after profiling both and
recorded in `docs/adr/0001-*.md`). Because side A publishes its own links to Discogs, every
method here is scored on real labelled pairs: precision, recall against labelled pairs, pair
completeness of the blocking step, calibration of the probabilities, and the size of the human
review queue at the chosen thresholds. Coverage (how many records got a match) is reported
beside precision (how many of those matches are right), because in this data they are not the
same number.

**Status.** Complete for v1 (`docs/BRIEF.md` Phase 6): three methods evaluated on a held-out
test fold of labelled pairs, a dbt warehouse that reconciles to the artifacts, a docs site
rendered from the exported marts, and a findings document with numbered limitations.

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

Every metric is on the test fold; precision, recall and F1 are over labelled A records; the
rendered block is checked byte for byte against the artifacts in CI.

## Coverage is not precision

Half of the sampled A records carry no MusicBrainz link to Discogs, so nothing they are matched
to can be verified. <!-- cite: artifacts/manifest.json#sample.thresholds.a.unlinked_share_actual -->
Coverage counts them; precision does not. `rules_v1` auto-accepts 4,501
unlabelled test-fold records, 0.093498 of its accepts, and `learned_v1` 1,103, 0.027062 of its
accepts; those accepts lift coverage and are excluded from every accuracy figure by
construction. <!-- cite: artifacts/eval_rules_v1.json#metrics.unverified_accepts.count; artifacts/eval_rules_v1.json#metrics.unverified_accepts.share_of_accepts; artifacts/eval_learned_v1.json#metrics.unverified_accepts.count; artifacts/eval_learned_v1.json#metrics.unverified_accepts.share_of_accepts -->
`docs/FINDINGS.md` carries the narrative, the review-budget table and the numbered limitations;
`docs/METHODS_CARD.md` the method records and metric definitions; the site the same figures as
charts.

## How to run

```
make setup    # uv sync --frozen (Python 3.12, runtime + dev)
make lint     # ruff check, ruff format --check, sqlfluff
make test     # pytest; real-data tests skip when data/ is absent
make dbt      # dbt build against the committed artifacts, docs generate, description check
make docs     # regenerate docs/METHODS_CARD.md and run the number and placeholder checks
make smoke    # all of the above from a fresh clone in a temp dir
make full     # the full build over the real dumps (network, hours; not built before Phase 4)
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
This repository's own code is the author's; the data stays under `data/` and never enters git.
