"""Fold assignment is a pure function of the A id (ADR 0003); pairs inherit it; the report
partitions the counts."""

from __future__ import annotations

import pandas as pd

from entity_resolution.eval import split


def test_fold_is_pure_and_bucketed() -> None:
    ids = [f"a{i}" for i in range(2000)]
    folds = [split.fold_for(i) for i in ids]
    assert folds == [split.fold_for(i) for i in ids]
    shares = pd.Series(folds).value_counts(normalize=True)
    assert (
        0.55 < shares["fit"] < 0.65
        and 0.15 < shares["calibrate"] < 0.25
        and 0.15 < shares["test"] < 0.25
    )
    for i in ids[:200]:
        b = split.bucket(i)
        assert split.fold_for(i) == ("fit" if b < 60 else "calibrate" if b < 80 else "test")


def test_pairs_inherit_the_a_fold_and_report_partitions() -> None:
    a_ids = pd.Series([f"a{i}" for i in range(300)])
    truth = pd.DataFrame({"a_id": a_ids[:100], "b_id": [f"b{i}" for i in range(100)]})
    cands = pd.DataFrame({"a_id": a_ids.repeat(2).reset_index(drop=True), "b_id": "x"})
    cands["fold"] = split.assign(cands["a_id"])
    assert (cands["fold"] == cands["a_id"].map(split.fold_for)).all()
    rep = split.report(a_ids, set(a_ids[:100]), truth, cands)
    assert sum(f["a_records"] for f in rep["folds"].values()) == 300
    assert sum(f["labelled_a_records"] for f in rep["folds"].values()) == 100
    assert sum(f["truth_pairs"] for f in rep["folds"].values()) == 100
    assert sum(f["candidate_pairs"] for f in rep["folds"].values()) == 600
    assert rep["rule"].startswith("fold = sha256(a native id)")
