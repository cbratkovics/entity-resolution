"""Fold assignment (docs/BRIEF.md 2.5 as amended by ADR 0003): folds are a pure function of
the A record's native id, ``sha256(a_id) mod 100``, with ``fit`` for 0 to 59, ``calibrate`` for
60 to 79 and ``test`` for 80 to 99. Every candidate pair and every truth pair inherits the fold
of its A record; B is the reference side and may appear in any fold. Seed-free by construction.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from entity_resolution.config import FOLDS

FOLD_BOUNDS: tuple[tuple[str, int, int], ...] = (
    ("fit", 0, 60),
    ("calibrate", 60, 80),
    ("test", 80, 100),
)
RULE = "fold = sha256(a native id) mod 100: fit [0, 60), calibrate [60, 80), test [80, 100)"


def bucket(a_id: str) -> int:
    return int(hashlib.sha256(str(a_id).encode("utf-8")).hexdigest(), 16) % 100


def fold_for(a_id: str) -> str:
    b = bucket(a_id)
    for name, lo, hi in FOLD_BOUNDS:
        if lo <= b < hi:
            return name
    raise AssertionError("unreachable")  # pragma: no cover


def assign(ids: pd.Series) -> pd.Series:
    """Fold per id, aligned to the input index."""
    return pd.Series([fold_for(i) for i in ids], index=ids.index, dtype="string")


def report(
    a_ids: pd.Series, labelled_a_ids: set[str], truth_pairs: pd.DataFrame, candidates: pd.DataFrame
) -> dict[str, Any]:
    """Counts per fold: A records, labelled A records, truth pairs and candidate pairs, plus the
    rule. ``truth_pairs`` and ``candidates`` carry an ``a_id`` column."""
    a_folds = assign(a_ids)
    labelled = a_ids.isin(labelled_a_ids)
    truth_folds = assign(truth_pairs["a_id"])
    cand_folds = candidates["fold"] if "fold" in candidates else assign(candidates["a_id"])
    folds = {}
    for name in FOLDS:
        folds[name] = {
            "a_records": int((a_folds == name).sum()),
            "labelled_a_records": int(((a_folds == name) & labelled).sum()),
            "truth_pairs": int((truth_folds == name).sum()),
            "candidate_pairs": int((cand_folds == name).sum()),
        }
    return {"rule": RULE, "bounds": {n: [lo, hi] for n, lo, hi in FOLD_BOUNDS}, "folds": folds}
