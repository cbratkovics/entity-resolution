# Decision Lab: case-based QA guide

A technical reviewer can check the lab scenario by scenario. The machine-readable catalog is
`docs/lab/scenarios.json` (stable ids `S01` to `S12`); `tests/test_lab_qa_catalog.py` verifies
that every case id, fixture id, file and Make target it names exists. Each scenario states the
question, the exact evidence reference, the code and warehouse models involved, the expected
outcome, a controlled perturbation, and what evidence would disprove the interpretation. Real
scenarios read the committed snapshot; synthetic scenarios read fixture rows and claim nothing
about the data.

## Before you start

```
make setup lint test dbt docs      # the Python-only gates (no Node)
make lab-check                     # the committed export is current and reconciles
cd apps/decision-lab && npm ci && cd ../..
make lab-test lab-build            # type check, unit tests, production build, sizes
make lab-verify                    # adds the Playwright journeys against the built app
make lab-dev                       # http://localhost:5173/entity-resolution/lab/
```

`make test` reports passes and skips separately: the only expected skip in a clone without
`data/` is the owner-run replay generation; the committed replay bundles are still re-verified
from the compressed files. Passing with that skip is not an owner-run real-data validation; the
owner-run figures are recorded in `artifacts/lab/replay/replay_<m>.json#reconciliation`.

## Best starting cases

Open these first in `#/cases/<a_id>`; each is also a catalog scenario.

| case | why |
|---|---|
| `ac8ca6a0-b24b-314c-ba05-c6b22c564ac9` | a verified method disagreement: two methods auto-accept one B, the third ties on another and goes to review; the local truth says which is right (S04, S08) |
| `03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2` | a tie at the maximum score in all three methods: the ambiguity rule, not the score, sends it to review (S03) |
| `41cb566c-8384-4a00-b944-e72280c673df` | an exported gap that rounds to the ambiguity threshold: the exhibit cannot explain the tier, the unrounded local gap can (S11) |
| `00013f25-4f52-40e8-bb72-e15b84a5fdc7` | a single candidate with a null gap, exported by two methods only (S07) |
| `0002f32f-e125-3453-9277-fdbb647b4967` | a no-candidate record: three not-exported rows, kept in the population (S07) |
| `00056fde-ad36-4f8f-8768-f350839e5eda` | an unverified accept: unlabelled, so it counts toward coverage only (S05) |

The narrative on the first three comes from `docs/FINDINGS.md` and is marked as narrative in
the case view; everything else on the page is machine-verified against the exhibits and, where
the labels block says `verified_local`, against the hash-checked local truth table.

## Scenario summaries

- **S01 published trade-off.** The Compare view must show rules with the higher F1 and learned
  with higher precision and a smaller queue at lower recall and coverage, every value with its
  artifact key. Disproof: an artifact ordering the methods the other way.
- **S02 supported floor change.** Only exported floors are selectable; the accept threshold and
  gap stay fixed and the page says so; a budget below every queue yields "no supported setting".
- **S03 high-score ambiguous pair and the regression.** The tie case is review by the gap rule;
  the fixture shows the legacy flag reuse accepting a record the corrected replay reviews, and
  the replay metadata reports the divergence only below the recorded accept threshold.
- **S04 verified disagreement.** Disagreement across methods is classified separately from
  ambiguity within one method, in Python, in dbt and on the page.
- **S05 missing labels.** An unlabelled accept moves coverage and unverified accepts, never
  precision or recall; zero-denominator metrics are unavailable, not perfect.
- **S06 blocking loss.** Reachable and overall recall use different denominators; reachability
  comes from the full blocked set, never from displayed candidates.
- **S07 single and no candidate.** Null gap, never demoted; no-candidate records are reject with
  a stated reason and stay in the population.
- **S08 accept, defer, reject candidate, undo.** Effective state and consequence counts change;
  the frozen metrics table does not; one effective accept per A and scenario.
- **S09 receipt round trip.** Export validates; a foreign snapshot is refused; hostile text is
  rendered as text and over-long text is rejected.
- **S10 missing input, stale export.** Learned replay is a declared limitation; an altered byte
  fails the check; nothing is rewritten or substituted.
- **S11 rounded gap at the boundary.** The exhibit flag says "cannot classify"; the unrounded
  local value says ambiguous; without local data the tier stays unexplained.
- **S12 synthetic sandbox.** Badged everywhere, ids that cannot collide with real ones, words
  from a fixed vocabulary, expected decisions reproduced, nothing reaching a real figure.

## What a reviewer cannot verify here

- Anything about `learned_v1` under a different policy: no frozen model exists, so the lab
  declares the replay unavailable instead of reconstructing it (ADR 0007).
- Reviewer performance: review-recall figures are upper bounds under perfect resolution.
- The deployed site: local builds and Playwright runs verify the app at its base path; the live
  Pages deployment is verified only by opening it after the owner pushes.
- Business impact: local decisions are not mapping writes, labels or measured outcomes, and no
  cost figure in the lab is a measured dollar amount.
