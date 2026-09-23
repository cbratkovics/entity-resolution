"""Tier boundaries partition [0, 1] and are monotone; the decision step takes one candidate per
A, applies the ambiguity rule, and is deterministic (docs/BRIEF.md 2.8)."""

from __future__ import annotations

import pandas as pd
import pytest

from entity_resolution.config import PROJECT
from entity_resolution.models import tiering


def test_constants_match_the_brief() -> None:
    assert tiering.AMBIGUITY_GAP == 0.10
    assert tiering.AUTO_ACCEPT_MIN == 0.95 and tiering.REVIEW_MIN == 0.50
    assert tiering.REVIEW_COST_UNITS == 1.0
    assert tiering.FALSE_ACCEPT_COST_RATIOS == (1, 5, 20)
    assert tiering.SWEEP_THRESHOLDS[0] == 0.50 and tiering.SWEEP_THRESHOLDS[-1] == 0.99
    assert len(tiering.SWEEP_THRESHOLDS) == 50


def test_tiers_partition_the_unit_interval_and_are_monotone() -> None:
    grid = [i / 1000 for i in range(1001)]
    tiers = [tiering.tier_for(p) for p in grid]
    assert set(tiers) == set(PROJECT.tiers)
    order = {"reject": 0, "review": 1, "auto_accept": 2}
    ranks = [order[t] for t in tiers]
    assert ranks == sorted(ranks)
    assert tiering.tier_for(0.95) == "auto_accept" and tiering.tier_for(0.9499) == "review"
    assert tiering.tier_for(0.50) == "review" and tiering.tier_for(0.4999) == "reject"


def test_probability_outside_unit_interval_is_rejected() -> None:
    with pytest.raises(ValueError):
        tiering.tier_for(1.01)


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a_id": ["a1", "a1", "a1", "a2", "a2", "a3", "a4", "a4"],
            "b_id": ["1", "2", "3", "4", "5", "6", "7", "8"],
            "score": [0.9, 0.5, 0.1, 0.99, 0.96, 0.6, 0.4, 0.4],
            "probability": [0.98, 0.50, 0.10, 0.99, 0.96, 0.60, 0.40, 0.40],
            "fold": ["test"] * 8,
            "block_keys": [["k_title3"]] * 8,
        }
    )


def test_decide_one_per_a_with_ambiguity_rule() -> None:
    d = tiering.decide(_pairs()).set_index("a_id")
    assert list(d.index) == ["a1", "a2", "a3", "a4"]
    assert d.loc["a1", "b_id"] == "1" and d.loc["a1", "tier"] == "auto_accept"
    assert d.loc["a1", "top2_gap"] == pytest.approx(0.48)
    # a2: top 0.99 but the runner-up is 0.96, gap 0.03 < 0.10 -> review, flagged
    assert d.loc["a2", "tier"] == "review" and bool(d.loc["a2", "ambiguity_review"])
    assert d.loc["a3", "tier"] == "review" and pd.isna(d.loc["a3", "top2_gap"])
    assert d.loc["a4", "tier"] == "reject" and d.loc["a4", "b_id"] == "7"  # tie broken by b_id
    assert not bool(d.loc["a4", "ambiguity_review"])  # the gap rule never lifts a reject


def test_decide_is_deterministic_under_row_order() -> None:
    p = _pairs()
    d1 = tiering.decide(p)
    d2 = tiering.decide(p.iloc[::-1].reset_index(drop=True))
    pd.testing.assert_frame_equal(d1.reset_index(drop=True), d2.reset_index(drop=True))


def test_custom_thresholds_for_rules() -> None:
    d = tiering.decide(_pairs(), accept_min=0.55, review_min=0.15).set_index("a_id")
    assert d.loc["a3", "tier"] == "auto_accept" and d.loc["a4", "tier"] == "review"
