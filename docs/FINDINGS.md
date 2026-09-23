# Findings

Every number below is read from a committed artifact and cited by key; the two tables are
rendered from the artifacts by `scripts/render_findings.py` and checked byte for byte in CI.
The unit of evaluation is the A record (a MusicBrainz release group of primary type Album):
each gets one decision, its top Discogs master and a tier. Accuracy is measured over labelled
A records on the test fold; coverage counts every test-fold A record.

## Results on the test fold

<!-- generated:results start -->
| method | pair completeness (test) | precision | recall (labelled) | recall (overall) | F1 | coverage | unverified accepts | review queue | ECE (decisions) |
|---|---|---|---|---|---|---|---|---|---|
| `exact_v1` | 0.963884 | 0.998733 | 0.760858 | 0.733379 | 0.863717 | 0.378315 | 1,009 (0.027622 of accepts) | 207 | 0.093735 |
| `rules_v1` | 0.963884 | 0.994615 | 0.930917 | 0.897296 | 0.961712 | 0.498566 | 4,501 (0.093498 of accepts) | 25,076 | 0.012978 |
| `learned_v1` | 0.963884 | 0.999344 | 0.849952 | 0.819255 | 0.918614 | 0.422113 | 1,103 (0.027062 of accepts) | 6,016 | 0.047858 |

Keys, per method, in `artifacts/eval_<method_version>.json#metrics`: `pair_completeness_test`, `at_auto_accept.precision`, `at_auto_accept.recall_labelled`, `recall_overall`, `at_auto_accept.f1`, `coverage`, `unverified_accepts.count`, `unverified_accepts.share_of_accepts`, `ambiguity_rule.review_queue`, `calibration.decision_level.ece`. Every metric is on the test fold; precision, recall and F1 are over labelled A records; coverage counts every test-fold A record.
<!-- generated:results end -->

## Three things the numbers say

**Rules is the best single method at fixed tiers.** With its two thresholds searched on
fit-fold decisions, `rules_v1` auto-accepts with precision 0.994615 and recall 0.930917
against labelled pairs, F1 0.961712; the learned model reaches higher precision, 0.999344, at
lower recall, 0.849952, F1 0.918614; the exact rule stops at recall 0.760858.
<!-- cite: artifacts/eval_rules_v1.json#metrics.at_auto_accept.precision; artifacts/eval_rules_v1.json#metrics.at_auto_accept.recall_labelled; artifacts/eval_rules_v1.json#metrics.at_auto_accept.f1; artifacts/eval_learned_v1.json#metrics.at_auto_accept.precision; artifacts/eval_learned_v1.json#metrics.at_auto_accept.recall_labelled; artifacts/eval_learned_v1.json#metrics.at_auto_accept.f1; artifacts/eval_exact_v1.json#metrics.at_auto_accept.recall_labelled -->
The price of the rules recall is its review tier: 25,076 of the 96,557 test-fold A records
are queued, because the review floor searched under the precision rule lands at 0.075676 and
almost every record with a candidate clears it. <!-- cite: artifacts/eval_rules_v1.json#metrics.ambiguity_rule.review_queue; artifacts/eval_rules_v1.json#metrics.test_a; artifacts/methods/rules_v1.json#parameters.thresholds.t_review -->
If every one of those reviews were resolved correctly, recall would be 0.998477, so the queue is
where the missing recall lives. <!-- cite: artifacts/eval_rules_v1.json#metrics.at_auto_accept_or_review.recall_labelled -->

**Unverified accepts are the coverage-versus-accuracy exhibit.** Half of the sampled A records
have no MusicBrainz link to Discogs, and the methods score them anyway. <!-- cite: artifacts/manifest.json#sample.thresholds.a.unlinked_share_actual -->
On the test fold
`rules_v1` auto-accepts 4,501 unlabelled records, 0.093498 of its accepts; `learned_v1`
accepts 1,103, 0.027062 of its accepts. <!-- cite: artifacts/eval_rules_v1.json#metrics.unverified_accepts.count; artifacts/eval_rules_v1.json#metrics.unverified_accepts.share_of_accepts; artifacts/eval_learned_v1.json#metrics.unverified_accepts.count; artifacts/eval_learned_v1.json#metrics.unverified_accepts.share_of_accepts -->
Those accepts raise coverage, 0.498566 against 0.422113, and nothing about them is verified:
the precision figures exclude them by construction. <!-- cite: artifacts/eval_rules_v1.json#metrics.coverage; artifacts/eval_learned_v1.json#metrics.coverage -->
A matcher reported by coverage alone would rank the methods by how boldly they accept
unlabelled records; reported by precision over labelled records, the ranking is about
correctness. Both numbers are in the table because they answer different questions.

**Calibration is where the learned model earns its place.** Its pair-level probabilities are
isotonic-calibrated on the calibrate fold and the test-fold pair-level ECE is 0.000147; the
decision-level ECE, measured on each A record's top candidate, is 0.047858.
<!-- cite: artifacts/eval_learned_v1.json#metrics.calibration.pair_level.ece; artifacts/eval_learned_v1.json#metrics.calibration.decision_level.ece -->
The gap is a selection effect: the argmax over calibrated pair probabilities picks the
candidate whose probability is highest, and that choice biases the chosen probability upward,
so the tiers act on slightly overconfident numbers even though the pair probabilities are not.
The rules score, used as a probability without calibration, shows the opposite pattern: a
decision-level ECE of 0.012978 not by design and a pair-level ECE of 0.402040, because the raw
score is nowhere near a probability across the millions of candidate pairs.
<!-- cite: artifacts/eval_rules_v1.json#metrics.calibration.decision_level.ece; artifacts/eval_rules_v1.json#metrics.calibration.pair_level.ece -->
Calibrating on decisions rather than pairs is on the roadmap.

## What a review budget buys

<!-- generated:review_floor start -->
| method | review floor | queue (floor) | queue (ambiguity) | queue (total) | share of test A | recall with review |
|---|---|---|---|---|---|---|
| `exact_v1` | 0.5 | 0 | 207 | 207 | 0.002144 | 0.765062 |
| `exact_v1` | 0.7 | 0 | 207 | 207 | 0.002144 | 0.765062 |
| `exact_v1` | 0.9 | 0 | 207 | 207 | 0.002144 | 0.765062 |
| `rules_v1` | 0.5 | 11,125 | 7,260 | 18,385 | 0.190406 | 0.997962 |
| `learned_v1` | 0.5 | 5,666 | 350 | 6,016 | 0.062305 | 0.963239 |
| `learned_v1` | 0.7 | 3,815 | 350 | 4,165 | 0.043135 | 0.931668 |
| `learned_v1` | 0.9 | 1,688 | 350 | 2,038 | 0.021107 | 0.890166 |

Keys: `artifacts/review_sensitivity.json#methods.<method_version>.review_floor_sweep.points[i]` with `floor`, `queue_floor`, `queue_ambiguity`, `queue_total`, `queue_share_of_test_a`, `recall_with_review`; floors at or above the method's accept threshold are omitted (`floors_omitted_at_or_above_accept_min`). The auto-accept threshold stays at `accept_min`; only the floor moves.
<!-- generated:review_floor end -->

## Blocking

The five blocking keys recover 96.3% of the sampled truth pairs before the per-A cap and 96.2%
after it. <!-- cite: artifacts/blocking_report.json#pair_completeness.union; artifacts/blocking_report.json#pair_completeness.after_cap -->
The cap keeps, for each A record, the 200 candidates with the most block keys (ties broken by
B id); it dropped 6,035,571 of the 13,631,048 union pairs and lost 240 truth pairs, so the
ordering costs almost nothing in pair completeness and removes most of the pairs from generic
title blocks that the feature stage would otherwise score. <!-- cite: artifacts/blocking_report.json#cap_overflow.pairs_dropped; artifacts/blocking_report.json#union_pairs; artifacts/blocking_report.json#pair_completeness.truth_pairs_lost_to_cap; artifacts/blocking_report.json#candidate_cap_per_a -->

## Worked examples from the review tier

Identifiers only; look them up on the public sites. The pattern code is the name-convention
class from the Phase 1 profiler applied to the pair.

- Release group `03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2`: `learned_v1` scores two Discogs
  masters, `683263` and `82406`, at the same calibrated probability (pattern `identical`
  for the top one); the truth link is to `82406`. Discogs holds two masters that are the same
  work after normalisation, the top-2 gap is zero, and the ambiguity rule sends the record to
  review instead of auto-accepting the wrong one.
- Release group `ac8ca6a0-b24b-314c-ba05-c6b22c564ac9`: `rules_v1` gives masters
  `120663` and `82443` the same score (pattern `title_token_subset`); the truth link is to
  `82443`. Same mechanism: a tie the rule cannot break is a review, not an accept.
- Release group `41cb566c-8384-4a00-b944-e72280c673df`: `learned_v1` puts master
  `1214912` (pattern `title_token_subset`, a subtitle on one side) in the review tier and it is
  the truth link; a reviewer confirms it in one look.

## Limitations

Numbered; the mandatory entries first.

1. **Unlinked is not non-match.** An A record without a MusicBrainz link to Discogs may still
   have a matching master; the sample's unlinked records are unlabelled, not negative, and
   the truth is incomplete in the direction nobody can measure from these sources.
2. **Recall is against labelled pairs only.** `recall_labelled` and `recall_overall` count
   correct accepts over labelled A records; nothing is known about the rest.
3. **Scope exclusion.** Release groups that are not of primary type Album are out of scope:
   105,485 truth links, of which 71,669 Single, 31,249 EP, 1,243 with no type at all, 1,216
   Other and 108 Broadcast. <!-- cite: artifacts/truth_audit.json#truth_out_of_scope; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Single; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.EP; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.none; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Other; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Broadcast -->
4. **Dead and unsampled truth.** 2,272 links point at a master absent from the current Discogs
   dump and are excluded; no in-scope link was excluded by the hash sample.
   <!-- cite: artifacts/truth_audit.json#truth_dead; artifacts/truth_audit.json#truth_unsampled -->
5. **First-release year is derived, not MusicBrainz's own.** The year is the earliest release
   event of the group computed from core tables; its equality with `release_group_meta` is
   asserted, not verified (ADR-0002).
6. **Blocking loss.** After the cap, 96.2% of sampled truth pairs are reachable; the rest,
   including the 240 lost to the per-A cap, are unreachable by every method.
   <!-- cite: artifacts/blocking_report.json#pair_completeness.after_cap; artifacts/blocking_report.json#pair_completeness.truth_pairs_lost_to_cap -->
7. **Decision-level overconfidence.** `learned_v1` is calibrated on pairs; its top-candidate
   probabilities are overconfident by the selection effect described above, ECE 0.047858
   against 0.000147 at pair level. <!-- cite: artifacts/eval_learned_v1.json#metrics.calibration.decision_level.ece; artifacts/eval_learned_v1.json#metrics.calibration.pair_level.ece -->
8. **Cap ordering is a choice.** The per-A cap keeps the 200 candidates with the most block
   keys; another ordering would keep a different 6,035,571 pairs out.
   <!-- cite: artifacts/blocking_report.json#candidate_cap_per_a; artifacts/blocking_report.json#cap_overflow.pairs_dropped -->
   It is documented in the blocking module and measured above, not tested against alternatives.
9. **Rules review queue.** Under the ruling that sets the review floor where cumulative
   precision drops under one half, `rules_v1` queues 25,076 test-fold records; the floor sweep
   shows what smaller queues buy. <!-- cite: artifacts/eval_rules_v1.json#metrics.ambiguity_rule.review_queue -->
10. **Test-fold-only mapping exhibit.** The committed mapping covers the test fold; the fit and
    calibrate folds are counted in the evaluation artifacts and the full mapping is a
    `make full` output (ADR-0005).
11. **Owner-run full build.** The measured peak of `data/` and the resident set do not fit a
    hosted runner (docs/REPRODUCIBILITY.md); the artifacts were produced on one machine and
    verified by a second run there, not by an independent machine.
