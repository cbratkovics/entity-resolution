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
