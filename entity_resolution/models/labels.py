"""Labels for the methods (docs/BRIEF.md 2.7 as amended by ADR 0001): a candidate pair is
positive when it is an in-sample truth pair, negative when its A record is labelled and the
pair is not in the truth set, and unlabelled (excluded from fitting and calibration) when its
A record has no truth link. Truth sets per A record allow one-to-many A records: an accept is
correct when the accepted B is in the set.

The truth frame enters only here and in the evaluator; the methods see ``label`` values, never
a B identifier from the truth table.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Labels:
    truth_sets: dict[str, frozenset[str]]
    """Labelled A id -> the set of truth B ids."""

    @property
    def labelled_a(self) -> frozenset[str]:
        return frozenset(self.truth_sets)

    def is_correct(self, a_id: str, b_id: str) -> bool:
        return b_id in self.truth_sets.get(a_id, frozenset())

    def pair_labels(self, pairs: pd.DataFrame) -> pd.Series:
        """1 for a truth pair, 0 for another pair of a labelled A, <NA> for an unlabelled A."""
        labelled = pairs["a_id"].isin(self.labelled_a)
        correct = [
            b in self.truth_sets.get(a, frozenset())
            for a, b in zip(pairs["a_id"], pairs["b_id"], strict=True)
        ]
        out = pd.Series(pd.array(correct, dtype="boolean"), index=pairs.index).astype("Int8")
        out[~labelled.to_numpy()] = pd.NA
        return out


def from_truth(in_sample: pd.DataFrame) -> Labels:
    """``in_sample`` has ``a_id`` and ``b_id`` (status truth_in_sample)."""
    sets: dict[str, set[str]] = {}
    for a, b in zip(in_sample["a_id"].astype(str), in_sample["b_id"].astype(str), strict=True):
        sets.setdefault(a, set()).add(b)
    return Labels({a: frozenset(v) for a, v in sets.items()})
