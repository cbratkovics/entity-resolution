# ADR-0005 — The committed mapping is the test fold only (2026-09-23)

**Context.** `docs/BRIEF.md` section `2.9` commits `artifacts/mapping/mapping_<method_version>.csv`
with one row per A record with a non-reject decision. The sample holds 482,514 A records and
there are three methods, so the full mappings are of the order of half a million rows each and
do not belong in git. <!-- cite: artifacts/manifest.json#counts.musicbrainz.sampled -->
Every reported metric comes from the test fold (section `2.9`), which holds 96,557 A records.
<!-- cite: artifacts/split.json#folds.test.a_records -->

**Decision.** The committed, audited exhibit is
`artifacts/mapping/mapping_<method_version>.test.csv.gz`: test-fold A records with a
non-reject decision, columns `a_id, b_id, method_version, feature_version, score, probability,
tier, block_keys, top2_gap, fold, run_id, decided_at_utc`; identifiers and numbers only. The
fit and calibrate folds are counted in the evaluation artifact only. The full mapping over every
fold is a `make full` output under `data/mapping/` and is uploaded as a workflow artifact by the
full build. `fct_mapping` in the warehouse is at test-fold grain and its description says so.
Alternative: commit the full mapping, rejected for size; commit a hash-sampled slice, rejected
because a slice of the fit fold is not an auditable exhibit of anything reported.

**Consequences.** `tests/test_no_raw_rows.py` reads gzipped CSVs; `scripts/check_reproducibility.py`
compares the mapping files ignoring `run_id` and `decided_at_utc`. Readers who want the full
mapping run `make full`.
