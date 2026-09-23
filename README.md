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

**Status.** Phase 5 of `docs/BRIEF.md`: the methods are evaluated, the dbt warehouse builds
silver and gold marts from the committed artifacts with reconciliation tests, and the docs
site renders the results from the exported JSON. The results table below and the narrative in
`docs/FINDINGS.md` are filled in Phase 6; until then `docs/METHODS_CARD.md` carries the
figures with their keys. The results table below is filled from
`artifacts/eval_<method_version>.json` once Phase 4 has run; until then it reads from an empty
artifact tree on purpose.

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
No run has been recorded yet (`artifacts/manifest.json#run_id` is null). The table is rendered
from `artifacts/eval_*.json` by Phase 6.
<!-- generated:results end -->

See `docs/METHODS_CARD.md` for the method records and metric definitions, and
`docs/FINDINGS.md` (Phase 6) for the narrative and the numbered limitations.

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
to aggregates, hashes, native identifiers, scores, tiers and JSON artifacts.

## What is and is not proven

- Proven by tests on the committed tree: artifacts validate against their schemas, the
  warehouse reconciles to the artifacts, no record attribute is tracked by git.
- Not yet proven: anything about matching quality. There is no run.

## Data and licences

Sources, verbatim licence text and what is loaded from each dump are recorded in
`docs/DATA_SOURCES.md`. All sources are CC0.
