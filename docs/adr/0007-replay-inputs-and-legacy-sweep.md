# ADR-0007 — Complete-replay inputs, their boundaries, and the legacy accept sweep (2026-09-26)

**Context.** Re-applying an arbitrary policy (accept threshold, review floor, ambiguity gap) to
the test fold needs, for every A record in the population, the unrounded decision values of its
top two candidates under the method's own tie order, the size of its full blocked candidate set,
and, where accuracy is claimed, label availability, top-candidate correctness and truth
reachability in the full blocked set. The committed mapping exhibits (ADR 0005) cannot supply
this: they are rounded to six decimals, omit reject-tier and no-candidate records, and carry no
labels. Rounding matters at policy boundaries: release group
`41cb566c-8384-4a00-b944-e72280c673df` has an exported `rules_v1` gap of `0.1` but an unrounded
gap just below `0.10`, so the exhibit alone cannot say whether the ambiguity rule fired. <!-- param -->
Separately, `review_cost.sweep()` computes the accept-threshold curve in
`artifacts/review_sensitivity.json#methods.<m>.points` by reusing the `ambiguity_review` flag
that `decide()` set at the method's recorded accept threshold. That flag marks demotion from
auto-accept, not the ambiguity condition itself, so at thresholds below the recorded one a
record whose value clears the lower threshold but whose gap is below the ambiguity gap is
counted as an accept when a faithful replay would put it in review. Reproducible example: top
values `0.80` and `0.76`, gap `0.04`; at accept `0.95` the record is in review by value and the
flag is false; at accept `0.75` reusing the flag accepts it. <!-- param -->

**Decision.**
1. Replay inputs are exported per method as `artifacts/lab/replay/replay_<m>.test.csv.gz`
   (one row per test-fold A record, including no-candidate and reject records; columns `v1, v2,
   n_candidates, labelled, top1_correct, truth_reachable`; no identifiers) with a metadata file
   `replay_<m>.json` carrying the completeness proof (row count equals the split's test-fold A
   count), the input hashes, and an exact reconciliation of a replay at the recorded policy to
   every metric in `eval_<m>.json` and to the review-floor sweep. A bundle whose reconciliation
   fails is an export error, not a warning.
2. `exact_v1` and `rules_v1` bundles are built from the frozen `data/pairs/features.parquet`
   (hash-verified against `artifacts/manifest.json`) because their decision values are pure,
   unfitted functions of those features; recomputing them is not refitting. `learned_v1` has no
   frozen model binary and no unrounded scored output on disk, so its complete replay is
   declared unavailable in `artifacts/lab/manifest.json#capabilities.complete_replay`. Scores are
   never reconstructed from the rounded mapping, omitted records are never assumed negative, and
   a refit would be a new versioned run, never attributed to this snapshot. The next full run
   writes unrounded scored pairs to `data/scored/` (`pipeline/methods.py`), which the exporter
   prefers when their run id matches the manifest.
3. The policy is specified once in `entity_resolution/decision_lab/policy.py` and mirrored in
   `apps/decision-lab/src/lib/policy.ts`; both are tested against
   `apps/decision-lab/fixtures/policy_fixtures.json`, which the Python module renders and which
   contains the example above as a mandatory regression. The ambiguity condition is tracked
   separately from the demotion flag; a single candidate has a null gap; no-candidate records
   stay in the population.
4. `review_sensitivity.json` is not rewritten or relabelled. Its accept-threshold points are
   retained in the lab as "legacy snapshot calculation" with the note above, and they never
   power a claim of faithful arbitrary-policy replay. Its review-floor sweep is exact at the
   recorded accept threshold (the flag is identical there) and is the lab's supported floor
   control. The corrected sweeps live in the replay path; `replay_<m>.json#legacy_sweep_divergence`
   records, per threshold, where the legacy and corrected calculations differ.
   Alternative: regenerate the sensitivity artifact (rejected: it would overwrite a historical
   artifact that the findings and the results page cite; the correction is versioned beside it).

**Consequences.** `tests/test_lab_policy.py` carries the regression; `tests/test_lab_export.py`
re-verifies the committed bundles from the compressed files alone, so CI proves the
reconciliation without `data/`. The results page keeps its cost curve unchanged and labelled as
before; the lab shows it only under the legacy label. Owner-only inputs remain: a frozen
`learned_v1` model or unrounded learned scores from a future versioned run.
