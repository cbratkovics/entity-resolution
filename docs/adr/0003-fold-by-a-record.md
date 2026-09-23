# ADR-0003 — Folds are assigned by the A record, not by the B record (2026-09-23)

**Context.** `docs/BRIEF.md` section `2.5` assigns folds by `sha256(master_id) mod 100`, the
side-B identifier. Every decision and metric in sections `2.8` and `2.9` is per A record: one
accepted B per A, the tier partition of A records, coverage over A records, and (ADR-0001)
unverified accepts on unlabelled A records. Under B folds an A record's candidate pairs and its
accepted link can sit in different folds, so "A records in the test fold" is not defined and a
record's own candidates would leak across the fit and test folds.

**Decision.** `fold = sha256(a native id) mod 100`: `fit` for 0 to 59, `calibrate` for 60 to
79, `test` for 80 to 99. Every candidate pair and every truth pair inherits the fold of its A
record. B is the reference side and may appear in any fold. The leakage test becomes: no
test-fold `a_id` appears in any fitted object's training index; fit-fold pairs are the only
input to the classifier and the threshold search; calibrate-fold pairs are the only input to
the calibrator. `artifacts/split.json` records the rule and the counts per fold.
Alternative: fold by B as written, rejected for the reason in the context.

**Consequences.** `eval/split.py` hashes `a_id`; `tests/test_split.py` asserts the fold is a
pure function of the A id and that pairs inherit it. A B record shared by A records in
different folds is not leakage: nothing is fitted on B records. Section `2.5` is amended in
the amendments log.
