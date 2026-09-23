"""The review-cost curve (docs/BRIEF.md 2.8): for each method, sweep the accept threshold from
0.50 to 0.99 and report the review queue size, the expected false accepts (accepts times one
minus the precision measured on labelled test-fold decisions at that threshold) and the total
cost per false-accept cost ratio. The chosen thresholds are reported next to the curve."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from entity_resolution.models.tiering import (
    FALSE_ACCEPT_COST_RATIOS,
    REVIEW_COST_UNITS,
    SWEEP_THRESHOLDS,
)

REVIEW_FLOORS: tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(1, 20))
"""Review floors swept for the queue-budget analysis: 0.05 to 0.95 in steps of 0.05."""


def sweep(
    test_decisions: pd.DataFrame,
    correct: np.ndarray,
    is_labelled: np.ndarray,
    *,
    review_min: float,
    chosen_accept: float,
    reachable: np.ndarray,
    n_test_a: int,
    n_labelled_reachable: int,
) -> dict[str, Any]:
    """``test_decisions`` has one row per test-fold A record with a candidate (``probability``);
    ``correct``, ``is_labelled`` and ``reachable`` (the A record's truth is among its
    candidates) are aligned boolean arrays; ``n_test_a`` counts every test-fold A record and
    ``n_labelled_reachable`` the labelled ones whose truth survived blocking."""
    p = test_decisions["probability"].to_numpy(dtype="float64")
    points = []
    for t in SWEEP_THRESHOLDS:
        accept = p >= t
        queue = int(((p >= review_min) & ~accept).sum())
        lab_acc = accept & is_labelled
        precision = float(correct[lab_acc].mean()) if lab_acc.any() else None
        n_accept = int(accept.sum())
        expected_fa = None if precision is None else round(n_accept * (1 - precision), 3)
        costs = {
            str(r): (
                None
                if expected_fa is None
                else round(queue * REVIEW_COST_UNITS + expected_fa * r, 3)
            )
            for r in FALSE_ACCEPT_COST_RATIOS
        }
        points.append(
            {
                "threshold": t,
                "accepts": n_accept,
                "review_queue": queue,
                "precision_labelled": None if precision is None else round(precision, 6),
                "expected_false_accepts": expected_fa,
                "total_cost": costs,
            }
        )
    return {
        "review_cost_units": REVIEW_COST_UNITS,
        "review_floor_sweep": floor_sweep(
            test_decisions,
            correct,
            is_labelled,
            reachable=reachable,
            accept_min=chosen_accept,
            n_test_a=n_test_a,
            n_labelled_reachable=n_labelled_reachable,
        ),
        "false_accept_cost_ratios": list(FALSE_ACCEPT_COST_RATIOS),
        "review_min": review_min,
        "chosen_accept_threshold": chosen_accept,
        "points": points,
    }


def floor_sweep(
    test_decisions: pd.DataFrame,
    correct: np.ndarray,
    is_labelled: np.ndarray,
    *,
    reachable: np.ndarray,
    accept_min: float,
    n_test_a: int,
    n_labelled_reachable: int,
) -> dict[str, Any]:
    """For each review floor, the review queue (test A records with floor <= p < accept_min),
    its share of the test fold, and recall with review: correct auto-accepts plus reviews whose
    truth is among the candidates, over labelled reachable A records (the upper bound of
    ``at_auto_accept_or_review``, as a function of the floor)."""
    p = test_decisions["probability"].to_numpy(dtype="float64")
    accept = p >= accept_min
    correct_accepts = int((accept & is_labelled & correct).sum())
    points = []
    for floor in REVIEW_FLOORS:
        review = (p >= floor) & ~accept
        queue = int(review.sum())
        resolved = int((review & is_labelled & reachable).sum())
        points.append(
            {
                "floor": floor,
                "review_queue": queue,
                "queue_share_of_test_a": round(queue / n_test_a, 6) if n_test_a else None,
                "recall_with_review": round((correct_accepts + resolved) / n_labelled_reachable, 6)
                if n_labelled_reachable
                else None,
            }
        )
    return {
        "accept_min": accept_min,
        "n_test_a": n_test_a,
        "n_labelled_reachable": n_labelled_reachable,
        "points": points,
    }
