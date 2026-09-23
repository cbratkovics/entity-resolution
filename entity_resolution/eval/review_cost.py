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


def sweep(
    test_decisions: pd.DataFrame,
    correct: np.ndarray,
    is_labelled: np.ndarray,
    *,
    review_min: float,
    chosen_accept: float,
) -> dict[str, Any]:
    """``test_decisions`` has one row per test-fold A record with a candidate (``probability``);
    ``correct`` and ``is_labelled`` are aligned boolean arrays."""
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
        "false_accept_cost_ratios": list(FALSE_ACCEPT_COST_RATIOS),
        "review_min": review_min,
        "chosen_accept_threshold": chosen_accept,
        "points": points,
    }
