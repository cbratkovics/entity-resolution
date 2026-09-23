"""Decision constants shared by every method (docs/BRIEF.md section 2.8).

Only constants and the tier boundaries live here until Phase 4 adds the decision step itself.
They are fixed a priori and written into every method version record, so the record documents
the policy the mapping was produced under.
"""

from __future__ import annotations

AMBIGUITY_GAP = 0.10
"""If the top two candidates for an A record differ by less than this, the pair is reviewed
regardless of probability."""

AUTO_ACCEPT_MIN = 0.95
"""Calibrated probability at or above which a pair is auto-accepted."""
REVIEW_MIN = 0.50
"""Calibrated probability at or above which (and below ``AUTO_ACCEPT_MIN``) a pair is reviewed;
below it the pair is rejected."""

TIER_THRESHOLDS: dict[str, float] = {"auto_accept": AUTO_ACCEPT_MIN, "review": REVIEW_MIN}
"""Lower bound of each non-reject tier; ``reject`` is everything below ``review``."""

REVIEW_COST_UNITS = 1.0
"""Cost of one human review row, the unit every other cost is expressed in."""
FALSE_ACCEPT_COST_RATIOS: tuple[int, ...] = (1, 5, 20)
"""Cost of one false accept relative to one review, swept in review_sensitivity.json."""
SWEEP_THRESHOLDS: tuple[float, ...] = tuple(round(0.50 + 0.01 * i, 2) for i in range(50))
"""Accept thresholds swept by the review-cost curve: 0.50 to 0.99 in steps of 0.01."""


def tier_for(probability: float) -> str:
    """The tier a calibrated probability falls in, before the ambiguity rule is applied."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {probability}")
    if probability >= AUTO_ACCEPT_MIN:
        return "auto_accept"
    if probability >= REVIEW_MIN:
        return "review"
    return "reject"


def decide(
    pairs,  # type: ignore[no-untyped-def]
    *,
    accept_min: float = AUTO_ACCEPT_MIN,
    review_min: float = REVIEW_MIN,
    ambiguity_gap: float = AMBIGUITY_GAP,
):
    """One decision per A record (docs/BRIEF.md 2.8): the top-probability candidate, its
    top-2 gap, and a tier from ``accept_min`` / ``review_min``; a non-reject decision whose gap
    is below ``ambiguity_gap`` goes to review regardless of probability.

    ``pairs`` has ``a_id``, ``b_id``, ``score``, ``probability`` and optionally ``fold`` and
    ``block_keys``. Ties on probability are broken by ``b_id`` so the decision is deterministic.
    Returns one row per A record present in ``pairs`` with ``ambiguity_review`` marking the
    rows the gap rule moved."""
    import numpy as np
    import pandas as pd

    ordered = pairs.sort_values(["a_id", "probability", "b_id"], ascending=[True, False, True])
    top = ordered.groupby("a_id", sort=False).head(2)
    first = top.groupby("a_id", sort=False).nth(0).set_index("a_id")
    second = top.groupby("a_id", sort=False).nth(1).set_index("a_id")["probability"]
    out = first.copy()
    out["top2_gap"] = (out["probability"] - second.reindex(out.index)).astype("float64")
    p = out["probability"].to_numpy(dtype="float64")
    tier = np.where(p >= accept_min, "auto_accept", np.where(p >= review_min, "review", "reject"))
    gap = out["top2_gap"].to_numpy(dtype="float64")
    ambiguous = (tier != "reject") & ~np.isnan(gap) & (gap < ambiguity_gap)
    tier = np.where(ambiguous, "review", tier)
    out["tier"] = pd.Series(tier, index=out.index, dtype="string")
    out["ambiguity_review"] = ambiguous & (np.where(p >= accept_min, True, False))
    out["top2_gap"] = out["top2_gap"].where(~np.isnan(gap), pd.NA)
    return out.reset_index()
