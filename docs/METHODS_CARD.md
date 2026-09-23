# Methods card

_Generated from committed artifacts by `scripts/check_model_card.py --write`; do not edit by hand. The block below is validated against the artifacts by that script, which is why the number checker skips it._

<!-- generated:methods_card start -->
## Run

| Field | Value | Source key |
|---|---|---|
| Feature version | `0.2.0` | `artifacts/manifest.json#feature_version` |
| Code commit | `6b3124b176ea8ffaf198c3ee6aa966cd6a2eccb4` | `artifacts/manifest.json#code_commit` |
| Side A | musicbrainz | `artifacts/manifest.json#side_a` |
| Side B | discogs | fixed by `docs/BRIEF.md` (section `2.1`) |
| Run id | `20260923T140606+0000` | `artifacts/manifest.json#run_id` |

## Decision summary

At the selected tiers, the fixed weighted rules have the higher test-fold F1 (`0.961712` versus `0.918614`). The learned classifier is the precision-first alternative: its auto-accept precision is `0.999344` versus `0.994615`, and its review queue is `6,016` rather than `25,076`, at the cost of lower labelled recall (`0.849952` versus `0.930917`). These are different tier policies, not an equal-recall queue comparison. All accuracy metrics are over labelled test-fold A records; unlinked records are unlabelled and appear only in coverage and unverified-accept counts.

## Evaluation population and blocking

The manifest contains `482,514` sampled MusicBrainz release groups. Blocking is evaluated over `241,752` in-scope truth pairs: completeness is `0.963355` before the per-record candidate cap and `0.962362` after it, leaving `7,595,477` candidate pairs. Sources: `artifacts/manifest.json#counts.musicbrainz.sampled`, `artifacts/blocking_report.json#pair_completeness.truth_pairs`, `#pair_completeness.union`, `#pair_completeness.after_cap`, and `#candidate_pairs_after_cap`.

## Methods

| Method version | Definition | Fitted on | Source |
|---|---|---|---|
| `exact_v1` | accept iff title_exact_norm and artist_full_exact and year_diff in {0, missing}; score in {0, 1} used as the probability; nothing fitted | nothing | `artifacts/methods/exact_v1.json` |
| `learned_v1` | HistGradientBoostingClassifier on PAIR_FEATURES (class_weight balanced, fixed hyperparameters) trained on fit-fold pairs of labelled A records; isotonic calibration (out_of_bounds clip) fitted on calibrate-fold labelled pairs; calibrated probability drives the tiers | {'calibrator': 'calibrate', 'model': 'fit'} | `artifacts/methods/learned_v1.json` |
| `rules_v1` | score = 0.45*title_token_set + 0.35*artist_token_set + 0.20*year_agreement, year_agreement = 1 if year_diff == 0, 0.5 if 1, 0.25 if missing, else 0; weights fixed a priori; t_accept maximises F1 over labelled fit-fold A-record decisions, t_review is the score below which their cumulative precision falls under 0.50; raw score used as the probability (uncalibrated) | {'thresholds': 'fit'} | `artifacts/methods/rules_v1.json` |

## Results (test fold only)

| Method | Pair completeness (test) | Precision | Recall (labelled) | Recall (overall) | F1 | Coverage | Unverified accepts | Review queue | ECE (decisions) |
|---|---|---|---|---|---|---|---|---|---|
| `exact_v1` | 0.963884 | 0.998733 | 0.760858 | 0.733379 | 0.863717 | 0.378315 | 1009 (0.027622 of accepts) | 207 | 0.093735 |
| `learned_v1` | 0.963884 | 0.999344 | 0.849952 | 0.819255 | 0.918614 | 0.422113 | 1103 (0.027062 of accepts) | 6016 | 0.047858 |
| `rules_v1` | 0.963884 | 0.994615 | 0.930917 | 0.897296 | 0.961712 | 0.498566 | 4501 (0.093498 of accepts) | 25076 | 0.012978 |

Keys per method: `artifacts/eval_<method_version>.json#metrics.pair_completeness_test`, `#metrics.at_auto_accept.precision`, `#metrics.at_auto_accept.recall_labelled`, `#metrics.recall_overall`, `#metrics.at_auto_accept.f1`, `#metrics.coverage`, `#metrics.unverified_accepts.count`, `#metrics.unverified_accepts.share_of_accepts`, `#metrics.ambiguity_rule.review_queue`, `#metrics.calibration.decision_level.ece`.

### `exact_v1`

Source: `artifacts/eval_exact_v1.json`; feature version `0.2.0`, code commit `6b3124b176ea8ffaf198c3ee6aa966cd6a2eccb4`; thresholds auto_accept_min `0.95`, review_min `0.5`, ambiguity_gap `0.1`.

| Metric | Value | Key |
|---|---|---|
| test_a | 96557 | `artifacts/eval_exact_v1.json#metrics.test_a` |
| labelled_a | 48372 | `artifacts/eval_exact_v1.json#metrics.labelled_a` |
| labelled_a_reachable | 46625 | `artifacts/eval_exact_v1.json#metrics.labelled_a_reachable` |
| at_auto_accept.accepted | 35520 | `artifacts/eval_exact_v1.json#metrics.at_auto_accept.accepted` |
| at_auto_accept.correct | 35475 | `artifacts/eval_exact_v1.json#metrics.at_auto_accept.correct` |
| at_auto_accept_or_review.precision | 0.998712 | `artifacts/eval_exact_v1.json#metrics.at_auto_accept_or_review.precision` |
| at_auto_accept_or_review.recall_labelled | 0.765062 | `artifacts/eval_exact_v1.json#metrics.at_auto_accept_or_review.recall_labelled` |
| coverage_all_folds | 0.375917 | `artifacts/eval_exact_v1.json#metrics.coverage_all_folds` |
| tier_shares.auto_accept | 0.37831539919425833 | `artifacts/eval_exact_v1.json#metrics.tier_shares.auto_accept` |
| tier_shares.review | 0.0021438114274470003 | `artifacts/eval_exact_v1.json#metrics.tier_shares.review` |
| tier_shares.reject | 0.6195407893782947 | `artifacts/eval_exact_v1.json#metrics.tier_shares.reject` |
| ambiguity_rule.decisions_moved_to_review | 207 | `artifacts/eval_exact_v1.json#metrics.ambiguity_rule.decisions_moved_to_review` |
| calibration.decision_level.brier | 0.093735 | `artifacts/eval_exact_v1.json#metrics.calibration.decision_level.brier` |
| calibration.pair_level.ece | 0.012434 | `artifacts/eval_exact_v1.json#metrics.calibration.pair_level.ece` |

### `learned_v1`

Source: `artifacts/eval_learned_v1.json`; feature version `0.2.0`, code commit `6b3124b176ea8ffaf198c3ee6aa966cd6a2eccb4`; thresholds auto_accept_min `0.95`, review_min `0.5`, ambiguity_gap `0.1`.

| Metric | Value | Key |
|---|---|---|
| test_a | 96557 | `artifacts/eval_learned_v1.json#metrics.test_a` |
| labelled_a | 48372 | `artifacts/eval_learned_v1.json#metrics.labelled_a` |
| labelled_a_reachable | 46625 | `artifacts/eval_learned_v1.json#metrics.labelled_a_reachable` |
| at_auto_accept.accepted | 39655 | `artifacts/eval_learned_v1.json#metrics.at_auto_accept.accepted` |
| at_auto_accept.correct | 39629 | `artifacts/eval_learned_v1.json#metrics.at_auto_accept.correct` |
| at_auto_accept_or_review.precision | 0.998666 | `artifacts/eval_learned_v1.json#metrics.at_auto_accept_or_review.precision` |
| at_auto_accept_or_review.recall_labelled | 0.963239 | `artifacts/eval_learned_v1.json#metrics.at_auto_accept_or_review.recall_labelled` |
| coverage_all_folds | 0.421281 | `artifacts/eval_learned_v1.json#metrics.coverage_all_folds` |
| tier_shares.auto_accept | 0.4221133630912311 | `artifacts/eval_learned_v1.json#metrics.tier_shares.auto_accept` |
| tier_shares.review | 0.062305166896237454 | `artifacts/eval_learned_v1.json#metrics.tier_shares.review` |
| tier_shares.reject | 0.5155814700125314 | `artifacts/eval_learned_v1.json#metrics.tier_shares.reject` |
| ambiguity_rule.decisions_moved_to_review | 350 | `artifacts/eval_learned_v1.json#metrics.ambiguity_rule.decisions_moved_to_review` |
| calibration.decision_level.brier | 0.033224 | `artifacts/eval_learned_v1.json#metrics.calibration.decision_level.brier` |
| calibration.pair_level.ece | 0.000147 | `artifacts/eval_learned_v1.json#metrics.calibration.pair_level.ece` |

### `rules_v1`

Source: `artifacts/eval_rules_v1.json`; feature version `0.2.0`, code commit `6b3124b176ea8ffaf198c3ee6aa966cd6a2eccb4`; thresholds auto_accept_min `0.65`, review_min `0.0756756772994995`, ambiguity_gap `0.1`.

| Metric | Value | Key |
|---|---|---|
| test_a | 96557 | `artifacts/eval_rules_v1.json#metrics.test_a` |
| labelled_a | 48372 | `artifacts/eval_rules_v1.json#metrics.labelled_a` |
| labelled_a_reachable | 46625 | `artifacts/eval_rules_v1.json#metrics.labelled_a_reachable` |
| at_auto_accept.accepted | 43639 | `artifacts/eval_rules_v1.json#metrics.at_auto_accept.accepted` |
| at_auto_accept.correct | 43404 | `artifacts/eval_rules_v1.json#metrics.at_auto_accept.correct` |
| at_auto_accept_or_review.precision | 0.981717 | `artifacts/eval_rules_v1.json#metrics.at_auto_accept_or_review.precision` |
| at_auto_accept_or_review.recall_labelled | 0.998477 | `artifacts/eval_rules_v1.json#metrics.at_auto_accept_or_review.recall_labelled` |
| coverage_all_folds | 0.497063 | `artifacts/eval_rules_v1.json#metrics.coverage_all_folds` |
| tier_shares.auto_accept | 0.4985656140932299 | `artifacts/eval_rules_v1.json#metrics.tier_shares.auto_accept` |
| tier_shares.review | 0.2597015234524685 | `artifacts/eval_rules_v1.json#metrics.tier_shares.review` |
| tier_shares.reject | 0.24173286245430162 | `artifacts/eval_rules_v1.json#metrics.tier_shares.reject` |
| ambiguity_rule.decisions_moved_to_review | 7260 | `artifacts/eval_rules_v1.json#metrics.ambiguity_rule.decisions_moved_to_review` |
| calibration.decision_level.brier | 0.027255 | `artifacts/eval_rules_v1.json#metrics.calibration.decision_level.brier` |
| calibration.pair_level.ece | 0.40204 | `artifacts/eval_rules_v1.json#metrics.calibration.pair_level.ece` |

## Metric definitions

- `ambiguity_rule`: Test-fold decisions the ambiguity rule moved from auto_accept to review because the top-2 probability gap was below the gap threshold.
- `at_auto_accept_or_review`: The same figures if every review were resolved correctly: a review row counts as correct when any of its candidates is in the truth set. An upper bound.
- `calibration`: decision_level: ten equal-width bins over the top candidate's probability of labelled test A records, with the observed rate of correct top candidates; pair_level: the same over every labelled test-fold pair. ECE is the count-weighted mean absolute gap; Brier the mean squared error of the probability against the label.
- `confusion`: Pair-level counts over labelled test-fold pairs at each tier boundary: tp and fp are pairs at or above the boundary, fn and tn below.
- `coverage`: Auto-accepted A records divided by all A records in the test fold, labelled or not. A volume measure, not an accuracy measure.
- `coverage_all_folds`: Auto-accepted A records divided by all sampled A records across every fold. Not an accuracy measure.
- `f1`: Harmonic mean of precision and recall_labelled at the same tier boundary.
- `labelled_a`: Labelled A records in the test fold: those with an in-sample truth link.
- `labelled_a_reachable`: Labelled test-fold A records whose truth survived blocking: at least one candidate pair is a truth pair.
- `pair_completeness_test`: labelled_a_reachable divided by labelled_a: the share of labelled test A records whose truth blocking made reachable (A-level pair completeness).
- `precision`: Among test-fold A records the method accepted, the share whose accepted B is in the A record's truth set. Over labelled A records only.
- `recall_labelled`: Correct accepts divided by labelled_a_reachable. Recall against labelled pairs whose truth blocking made reachable; unlinked is not non-match.
- `recall_overall`: Correct accepts divided by labelled_a: recall with the blocking loss included; equals recall_labelled times pair_completeness_test exactly.
- `tier_shares`: Share of all test-fold A records in each tier; an A record with no candidate is reject. The three shares sum to one.
- `unverified_accepts`: Auto-accepts on unlabelled test-fold A records: counted by coverage, not by the accuracy metrics. share_of_accepts is their share of all test-fold auto-accepts.

<!-- generated:methods_card end -->
