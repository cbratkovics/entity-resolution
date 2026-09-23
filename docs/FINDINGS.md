# Findings

Written as the phases complete; every number cites the artifact it was read from. The
narrative and the results table arrive in Phase 6.

## Blocking

The five blocking keys recover 96.3% of the sampled truth pairs before the per-A cap and 96.2%
after it. <!-- cite: artifacts/blocking_report.json#pair_completeness.union; artifacts/blocking_report.json#pair_completeness.after_cap -->
The cap keeps, for each A record, the 200 candidates with the most block keys (ties broken by
B id); it dropped 6,035,571 of the 13,631,048 union pairs and lost 240 truth pairs, so the
ordering costs almost nothing in pair completeness and removes most of the pairs from generic
title blocks that the feature stage would otherwise score. <!-- cite: artifacts/blocking_report.json#cap_overflow.pairs_dropped; artifacts/blocking_report.json#union_pairs; artifacts/blocking_report.json#pair_completeness.truth_pairs_lost_to_cap; artifacts/blocking_report.json#candidate_cap_per_a -->

## Calibration note (for the Phase 6 narrative)

`learned_v1` is calibrated at pair level (isotonic on calibrate-fold pairs) and its pair-level
ECE on the test fold is 0.000147; the decision-level ECE, measured on each A record's top
candidate, is 0.047858. <!-- cite: artifacts/eval_learned_v1.json#metrics.calibration.pair_level.ece; artifacts/eval_learned_v1.json#metrics.calibration.decision_level.ece -->
The gap is a selection effect: taking the argmax over calibrated pair probabilities biases the
chosen probability upward, so the tiers act on numbers that are overconfident even though the
pair probabilities are not. Calibrating on decisions is on the roadmap.

## Limitations

Numbered; the mandatory entries first. Every phase adds what it found.

1. **Unlinked is not non-match.** An A record without a MusicBrainz link to Discogs may still
   have a matching master; the sample's unlinked records are unlabelled, not negative.
2. **Recall is against labelled pairs only.** `recall_labelled` and `recall_overall` count
   correct accepts over labelled A records; nothing is known about the rest.
3. **Scope exclusion.** Release groups that are not of primary type Album are out of scope:
   105,485 truth links, of which 71,669 Single, 31,249 EP, 1,243 with no type, 1,216 Other and
   108 Broadcast. <!-- cite: artifacts/truth_audit.json#truth_out_of_scope; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Single; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.EP; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.none; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Other; artifacts/truth_audit.json#truth_out_of_scope_by_primary_type.Broadcast -->
4. **Dead and unsampled truth.** 2,272 links point at a master absent from the current Discogs
   dump and are excluded; no in-scope link was excluded by the hash sample.
   <!-- cite: artifacts/truth_audit.json#truth_dead; artifacts/truth_audit.json#truth_unsampled -->
5. **First-release year is derived, not MusicBrainz's own.** The year is the earliest release
   event of the group computed from core tables; its equality with `release_group_meta` is
   asserted, not verified (ADR-0002).
6. **Blocking loss.** After the cap, 96.2% of sampled truth pairs are reachable; the rest,
   including the 240 lost to the per-A cap, are unreachable by every method.
   <!-- cite: artifacts/blocking_report.json#pair_completeness.after_cap; artifacts/blocking_report.json#pair_completeness.truth_pairs_lost_to_cap -->
