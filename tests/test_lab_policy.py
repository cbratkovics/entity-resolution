"""The pure policy engine of the decision lab reproduces its canonical fixtures, agrees with
``tiering.decide`` on random pandas inputs, and honours the boundary semantics the lab
documents (docs/DECISION_LAB.md section 3)."""

from __future__ import annotations

import dataclasses
import json
import math
import random

import pandas as pd
import pytest

from entity_resolution.decision_lab import fixtures
from entity_resolution.decision_lab.policy import (
    Policy,
    PolicyError,
    ReplayRow,
    accept_sweep,
    decide_row,
    evaluate,
    floor_sweep,
    legacy_accept_sweep,
    rank_candidates,
    row_from_candidates,
)
from entity_resolution.models import tiering

NATIVE = Policy(0.95, 0.50, 0.10)


def _rows(spec):  # type: ignore[no-untyped-def]
    return [ReplayRow(**r) for r in spec]


def test_fixture_file_is_current() -> None:
    assert fixtures.FIXTURES_PATH.exists(), "run python -m entity_resolution.decision_lab.fixtures"
    assert fixtures.check(), "policy_fixtures.json is stale"


def test_fixture_file_parses_to_the_render() -> None:
    on_disk = json.loads(fixtures.FIXTURES_PATH.read_text(encoding="utf-8"))
    assert on_disk == json.loads(fixtures.dumps(fixtures.render()))


@pytest.mark.parametrize("case", fixtures.render()["cases"], ids=lambda c: c["id"])
def test_every_fixture_case_reproduces(case) -> None:  # type: ignore[no-untyped-def]
    rows = _rows(case["rows"])
    policy = Policy(**case["policy"])
    assert [dataclasses.asdict(decide_row(r, policy)) for r in rows] == case["expected_decisions"]
    assert evaluate(rows, policy) == case["expected_metrics"]
    if "baseline_policy" in case:
        base = Policy(**case["baseline_policy"])
        assert [dataclasses.asdict(decide_row(r, base)) for r in rows] == case[
            "expected_baseline_decisions"
        ]
        thresholds = [p["threshold"] for p in case["expected_legacy_sweep"]]
        assert (
            legacy_accept_sweep(rows, baseline=base, thresholds=thresholds)
            == case["expected_legacy_sweep"]
        )
        assert (
            accept_sweep(
                rows,
                review_min=base.review_min,
                ambiguity_gap=base.ambiguity_gap,
                thresholds=[p["threshold"] for p in case["expected_corrected_sweep"]],
            )
            == case["expected_corrected_sweep"]
        )
    if "floors" in case:
        assert (
            floor_sweep(
                rows,
                accept_min=case["floor_accept_min"],
                ambiguity_gap=policy.ambiguity_gap,
                floors=case["floors"],
            )
            == case["expected_floor_sweep"]
        )


def test_mandatory_regression_legacy_accepts_corrected_reviews() -> None:
    row = ReplayRow(0.80, 0.76, 2, True, True, True)
    lowered = Policy(0.75, 0.50, 0.10)
    assert decide_row(row, NATIVE).tier == "review"
    assert decide_row(row, NATIVE).demoted is False
    corrected = decide_row(row, lowered)
    assert corrected.tier == "review" and corrected.ambiguous and corrected.demoted
    legacy = legacy_accept_sweep([row], baseline=NATIVE, thresholds=[0.75])[0]
    fixed = accept_sweep([row], review_min=0.50, ambiguity_gap=0.10, thresholds=[0.75])[0]
    assert legacy["accepts"] == 1 and legacy["review_queue"] == 0
    assert fixed["accepts"] == 0 and fixed["review_queue"] == 1
    at_native = legacy_accept_sweep([row], baseline=NATIVE, thresholds=[0.95])[0]
    fixed_native = accept_sweep([row], review_min=0.50, ambiguity_gap=0.10, thresholds=[0.95])[0]
    assert (at_native["accepts"], at_native["review_queue"]) == (
        fixed_native["accepts"],
        fixed_native["review_queue"],
    )


def test_boundaries_are_inclusive_and_gap_is_strict() -> None:
    assert decide_row(ReplayRow(0.95, 0.5, 2, False, None, None), NATIVE).tier == "auto_accept"
    assert (
        decide_row(ReplayRow(0.9499999999999999, 0.5, 2, False, None, None), NATIVE).tier
        == "review"
    )
    assert decide_row(ReplayRow(0.50, 0.1, 2, False, None, None), NATIVE).tier == "review"
    assert (
        decide_row(ReplayRow(0.49999999999999994, 0.1, 2, False, None, None), NATIVE).tier
        == "reject"
    )
    wide = Policy(0.95, 0.50, 0.25)
    assert decide_row(ReplayRow(1.0, 0.75, 2, False, None, None), wide).ambiguous is False
    assert decide_row(ReplayRow(1.0, 0.7500000000000001, 2, False, None, None), wide).ambiguous
    assert decide_row(ReplayRow(0.40, 0.39, 2, False, None, None), NATIVE).tier == "reject"


def test_rounded_gap_equal_to_threshold_is_still_ambiguous() -> None:
    row = ReplayRow(1.0, 0.9, 2, True, True, True)
    d = decide_row(row, NATIVE)
    assert d.gap is not None and d.gap < 0.10 and d.ambiguous and d.tier == "review"
    assert round(d.gap, 6) == 0.1


def test_ties_lexical_order_and_no_candidate() -> None:
    assert [b for b, _ in rank_candidates([("9", 1.0), ("10", 1.0), ("2", 0.5)])] == [
        "10",
        "9",
        "2",
    ]
    chosen, row = row_from_candidates(
        [("9", 1.0), ("10", 1.0)], labelled=True, truth_b_ids=frozenset({"9"})
    )
    assert chosen == "10" and row.top1_correct is False and row.truth_reachable is True
    tie = decide_row(row, NATIVE)
    assert tie.gap == 0.0 and tie.ambiguous and tie.demoted and tie.tier == "review"
    _, none = row_from_candidates([], labelled=True, truth_b_ids=frozenset({"1"}))
    d = decide_row(none, NATIVE)
    assert d.tier == "reject" and d.reason == "no_candidate" and d.gap is None
    m = evaluate([none], NATIVE)
    assert m["tier_counts"]["reject"] == 1 and m["labelled_a_reachable"] == 0
    single = decide_row(ReplayRow(0.99, None, 1, False, None, None), NATIVE)
    assert single.gap is None and single.ambiguous is False


@pytest.mark.parametrize(
    "policy",
    [
        {"accept_min": 0.5, "review_min": 0.6, "ambiguity_gap": 0.1},
        {"accept_min": 1.5, "review_min": 0.5, "ambiguity_gap": 0.1},
        {"accept_min": 0.9, "review_min": -0.1, "ambiguity_gap": 0.1},
        {"accept_min": math.nan, "review_min": 0.5, "ambiguity_gap": 0.1},
        {"accept_min": 0.9, "review_min": 0.5, "ambiguity_gap": math.inf},
        {"accept_min": 0.9, "review_min": 0.5, "ambiguity_gap": 1.5},
        {"accept_min": "0.9", "review_min": 0.5, "ambiguity_gap": 0.1},
        {"accept_min": True, "review_min": 0.5, "ambiguity_gap": 0.1},
    ],
)
def test_invalid_policies_raise(policy) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PolicyError):
        Policy(**policy)


def test_replay_row_invariants() -> None:
    with pytest.raises(ValueError):
        ReplayRow(None, None, 1, False, None, None)
    with pytest.raises(ValueError):
        ReplayRow(0.5, 0.6, 2, False, None, None)
    with pytest.raises(ValueError):
        ReplayRow(0.5, None, 2, False, None, None)
    with pytest.raises(ValueError):
        ReplayRow(0.5, 0.4, 2, False, True, None)
    with pytest.raises(ValueError):
        ReplayRow(math.nan, None, 1, False, None, None)


def test_decide_row_agrees_with_tiering_decide_on_random_pairs() -> None:
    rng = random.Random(20260926)
    records = []
    a_ids = [f"a{i:03d}" for i in range(120)]
    for a in a_ids:
        n = rng.choice([1, 1, 2, 2, 3, 5, 8])
        values = [rng.choice([0.0, 0.5, 0.95, 0.96, 1.0, round(rng.random(), 3)]) for _ in range(n)]
        if n >= 2 and rng.random() < 0.3:
            values[1] = values[0]  # force ties
        b_ids = rng.sample([str(x) for x in range(1, 40)], n)
        for b, v in zip(b_ids, values, strict=True):
            records.append({"a_id": a, "b_id": b, "score": v, "probability": v, "fold": "test"})
    pairs = pd.DataFrame(records)
    pairs["b_id"] = pairs["b_id"].astype("string")
    for accept_min, review_min, gap in ((0.95, 0.5, 0.1), (0.75, 0.5, 0.1), (0.95, 0.5, 0.25)):
        ref = tiering.decide(pairs, accept_min=accept_min, review_min=review_min, ambiguity_gap=gap)
        ref = ref.set_index("a_id")
        policy = Policy(accept_min, review_min, gap)
        for a, grp in pairs.groupby("a_id"):
            cands = [
                (str(b), float(v)) for b, v in zip(grp["b_id"], grp["probability"], strict=True)
            ]
            chosen, row = row_from_candidates(cands, labelled=False)
            d = decide_row(row, policy)
            assert chosen == str(ref.loc[a, "b_id"]), a
            assert d.tier == ref.loc[a, "tier"], a
            assert d.demoted == bool(ref.loc[a, "ambiguity_review"]), a
            ref_gap = ref.loc[a, "top2_gap"]
            if pd.isna(ref_gap):
                assert d.gap is None
            else:
                assert d.gap == float(ref_gap)
