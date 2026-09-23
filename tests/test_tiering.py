"""The tier boundaries partition [0, 1], are monotone, and match docs/BRIEF.md 2.8."""

from __future__ import annotations

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
