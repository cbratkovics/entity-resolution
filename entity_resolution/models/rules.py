"""``rules_v1`` (docs/BRIEF.md 2.7, thresholds as amended in the Phase 4 rulings).

``score = 0.45 * title_token_set + 0.35 * artist_token_set + 0.20 * year_agreement`` with the
weights fixed a priori. Thresholds are searched on fit-fold A-record decisions (top candidate
per A, then a sweep), not on raw pairs: ``t_accept`` maximises F1 over labelled fit-fold A
records; ``t_review`` is the score below which the cumulative precision of those decisions
falls under 0.50. The raw score is used as the probability, uncalibrated, so the calibration
table shows why calibration matters.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

METHOD_VERSION = "rules_v1"
WEIGHTS: dict[str, float] = {
    "title_token_set": 0.45,
    "artist_token_set": 0.35,
    "year_agreement": 0.20,
}
REVIEW_PRECISION_FLOOR = 0.50
DEFINITION = (
    "score = 0.45*title_token_set + 0.35*artist_token_set + 0.20*year_agreement, "
    "year_agreement = 1 if year_diff == 0, 0.5 if 1, 0.25 if missing, else 0; weights fixed a "
    "priori; t_accept maximises F1 over labelled fit-fold A-record decisions, t_review is the "
    "score below which their cumulative precision falls under 0.50; raw score used as the "
    "probability (uncalibrated)"
)


def year_agreement(year_diff: pd.Series) -> np.ndarray:
    d = year_diff.astype("float64").to_numpy(na_value=np.nan)
    out = np.where(np.isnan(d), 0.25, np.where(d == 0, 1.0, np.where(d == 1, 0.5, 0.0)))
    return out.astype("float64")


def score(features: pd.DataFrame) -> np.ndarray:
    return (
        WEIGHTS["title_token_set"] * features["title_token_set"].to_numpy(dtype="float64")
        + WEIGHTS["artist_token_set"] * features["artist_token_set"].to_numpy(dtype="float64")
        + WEIGHTS["year_agreement"] * year_agreement(features["year_diff"])
    )


def fit_thresholds(decisions: pd.DataFrame, n_recall_base: int) -> dict[str, Any]:
    """``decisions``: one row per labelled fit-fold A record with ``score`` (of its top
    candidate) and ``correct`` (the top candidate is in the truth set). ``n_recall_base`` is the
    number of labelled fit-fold A records whose truth survived blocking (the recall
    denominator). Returns the thresholds and the sweep summary."""
    d = decisions.sort_values(["score", "correct"], ascending=[False, True]).reset_index(drop=True)
    correct = d["correct"].to_numpy(dtype="float64")
    scores = d["score"].to_numpy(dtype="float64")
    k = np.arange(1, len(d) + 1, dtype="float64")
    cum_correct = np.cumsum(correct)
    precision = cum_correct / k
    recall = cum_correct / max(n_recall_base, 1)
    f1 = np.where(precision + recall > 0, 2 * precision * recall / (precision + recall), 0.0)
    # the cut is placed at the last row of each distinct score, so a threshold is a score value
    last_of_score = np.r_[scores[1:] != scores[:-1], True]
    candidates = np.where(last_of_score)[0]
    best = candidates[np.argmax(f1[candidates])]
    t_accept = float(scores[best])
    below = np.where(last_of_score & (precision < REVIEW_PRECISION_FLOOR))[0]
    t_review = float(scores[below[0]]) if below.size else float(scores[-1])
    t_review = min(t_review, t_accept)
    return {
        "t_accept": t_accept,
        "t_review": t_review,
        "f1_at_t_accept": float(f1[best]),
        "precision_at_t_accept": float(precision[best]),
        "recall_at_t_accept": float(recall[best]),
        "decisions_searched": int(len(d)),
        "recall_base": int(n_recall_base),
        "review_precision_floor": REVIEW_PRECISION_FLOOR,
    }
