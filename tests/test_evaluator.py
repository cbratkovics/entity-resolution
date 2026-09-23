"""Metrics on a hand-built fixture match hand-computed values, the recall identity holds
exactly, and the artifact validates."""

from __future__ import annotations

import pandas as pd
import pytest

from entity_resolution.eval import evaluator
from entity_resolution.models import labels as labels_mod


def _fixture():
    # 6 test A records: a1..a4 labelled, a5, a6 unlabelled; a7 in fit fold
    truth = pd.DataFrame({"a_id": ["a1", "a2", "a3", "a4"], "b_id": ["1", "2", "3", "4"]})
    lab = labels_mod.from_truth(truth)
    pairs = pd.DataFrame(
        {
            "a_id": ["a1", "a1", "a2", "a3", "a3", "a4", "a5", "a6", "a7"],
            "b_id": ["1", "9", "8", "3", "7", "6", "5", "0", "7"],
            "fold": ["test"] * 8 + ["fit"],
            "probability": [0.99, 0.30, 0.97, 0.70, 0.60, 0.98, 0.99, 0.20, 0.99],
        }
    )
    # decisions: a1 accept correct; a2 accept wrong (truth 2 not a candidate); a3 review, truth
    # reachable; a4 accept wrong; a5 accept unlabelled; a6 reject; a7 fit accept
    decisions = pd.DataFrame(
        {
            "a_id": ["a1", "a2", "a3", "a4", "a5", "a6", "a7"],
            "b_id": ["1", "8", "3", "6", "5", "0", "7"],
            "score": [0.99, 0.97, 0.70, 0.98, 0.99, 0.20, 0.99],
            "probability": [0.99, 0.97, 0.70, 0.98, 0.99, 0.20, 0.99],
            "tier": [
                "auto_accept",
                "auto_accept",
                "review",
                "auto_accept",
                "auto_accept",
                "reject",
                "auto_accept",
            ],
            "fold": ["test"] * 6 + ["fit"],
            "ambiguity_review": [False] * 7,
        }
    )
    a_folds = pd.Series(
        ["test"] * 6 + ["fit", "test"], index=["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"]
    )
    return lab, pairs, decisions, a_folds


def test_hand_computed_metrics() -> None:
    lab, pairs, decisions, a_folds = _fixture()
    art = evaluator.evaluate(
        method_version="rules_v1",
        decisions=decisions,
        pairs=pairs,
        labels=lab,
        a_folds=a_folds,
        thresholds={"auto_accept_min": 0.95, "review_min": 0.5, "ambiguity_gap": 0.1},
        manifest_sha256="0" * 64,
        code_commit="x",
        generated_at_utc="2026-09-23T00:00:00+00:00",
    )
    m = art["metrics"]
    assert m["test_a"] == 7 and m["labelled_a"] == 4  # a8 has no candidate
    assert m["labelled_a_reachable"] == 2  # a1 and a3 have their truth among candidates
    assert m["pair_completeness_test"] == 0.5
    acc = m["at_auto_accept"]
    assert acc["accepted"] == 3 and acc["correct"] == 1  # a1 correct, a2 and a4 wrong
    assert acc["precision"] == pytest.approx(1 / 3) and acc["recall_labelled"] == 0.5
    assert acc["f1"] == pytest.approx(2 * (1 / 3) * 0.5 / (1 / 3 + 0.5), abs=1e-6)
    either = m["at_auto_accept_or_review"]
    assert either["accepted"] == 4 and either["correct"] == 2  # a3's review resolves correctly
    assert (
        m["recall_overall"]
        == 0.25
        == pytest.approx(acc["recall_labelled"] * m["pair_completeness_test"])
    )
    assert m["coverage"] == pytest.approx(4 / 7)  # a1, a2, a4, a5 of 7 test A
    assert m["unverified_accepts"] == {"count": 1, "share_of_accepts": 0.25}
    assert m["tier_shares"]["auto_accept"] + m["tier_shares"]["review"] + m["tier_shares"][
        "reject"
    ] == pytest.approx(1.0)
    assert m["tier_shares"]["reject"] == pytest.approx(2 / 7)  # a6 and a8 (no candidate)
    assert m["coverage_all_folds"] == pytest.approx(5 / 8)
    cal = m["calibration"]["decision_level"]
    assert cal["n"] == 4 and sum(b["n"] for b in cal["bins"]) == 4
    assert m["confusion"]["auto_accept"] == {"tp": 1, "fp": 2, "fn": 1, "tn": 2}
    assert art["fold_counts"]["test"]["labelled_a_records"] == 4
    evaluator.validate(art)


def test_recall_identity_is_exact_on_random_fixtures() -> None:
    lab, pairs, decisions, a_folds = _fixture()
    art = evaluator.evaluate(
        method_version="exact_v1",
        decisions=decisions,
        pairs=pairs,
        labels=lab,
        a_folds=a_folds,
        thresholds={"auto_accept_min": 0.95, "review_min": 0.5, "ambiguity_gap": 0.1},
        manifest_sha256="0" * 64,
        code_commit="x",
        generated_at_utc="t",
    )
    m = art["metrics"]
    assert m["recall_overall"] == pytest.approx(
        m["at_auto_accept"]["recall_labelled"] * m["pair_completeness_test"], abs=1e-6
    )


def test_reliability_bins_and_ece() -> None:
    import numpy as np

    r = evaluator.reliability(np.array([0.05, 0.95, 0.95, 0.55]), np.array([0, 1, 0, 1]))
    assert (
        r["n"] == 4 and r["bins"][0]["n"] == 1 and r["bins"][9]["n"] == 2 and r["bins"][5]["n"] == 1
    )
    # ECE = 1/4*|0.05-0| + 2/4*|0.95-0.5| + 1/4*|0.55-1|
    assert r["ece"] == pytest.approx(0.25 * 0.05 + 0.5 * 0.45 + 0.25 * 0.45, abs=1e-6)
    assert r["brier"] == pytest.approx(np.mean([0.05**2, 0.05**2, 0.95**2, 0.45**2]), abs=1e-6)


def test_every_metric_has_a_definition() -> None:
    for key in (
        "pair_completeness_test",
        "precision",
        "recall_labelled",
        "recall_overall",
        "coverage",
        "coverage_all_folds",
        "unverified_accepts",
        "tier_shares",
        "calibration",
        "confusion",
        "ambiguity_rule",
    ):
        assert evaluator.METRIC_DEFINITIONS[key].strip()
