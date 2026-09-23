"""``learned_v1`` (docs/BRIEF.md 2.7, Phase 4 rulings): a ``HistGradientBoostingClassifier`` on
``PAIR_FEATURES`` with balanced class weight and fixed hyperparameters, trained on fit-fold
pairs of labelled A records only; isotonic calibration on calibrate-fold labelled pairs. The
raw model probability is the score; the isotonic output is the probability the tiers act on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from entity_resolution.features.pairs import PAIR_FEATURES

METHOD_VERSION = "learned_v1"
HYPERPARAMETERS: dict[str, Any] = {
    "max_iter": 300,
    "learning_rate": 0.1,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 50,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "class_weight": "balanced",
    "random_state": 0,
}
DEFINITION = (
    "HistGradientBoostingClassifier on PAIR_FEATURES (class_weight balanced, fixed "
    "hyperparameters) trained on fit-fold pairs of labelled A records; isotonic calibration "
    "(out_of_bounds clip) fitted on calibrate-fold labelled pairs; calibrated probability drives "
    "the tiers"
)


def index_sha256(pairs: pd.DataFrame) -> str:
    """Hash of the sorted (a_id, b_id) index a fitted object saw; the leakage test recomputes
    it from the features and the truth table."""
    keys = sorted(f"{a}|{b}" for a, b in zip(pairs["a_id"], pairs["b_id"], strict=True))
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def design(features: pd.DataFrame) -> np.ndarray:
    x = features[list(PAIR_FEATURES)].copy()
    x["year_diff"] = x["year_diff"].astype("float64")  # <NA> -> nan, native to HGB
    return x.to_numpy(dtype="float64")


@dataclass
class Learned:
    model: HistGradientBoostingClassifier
    calibrator: IsotonicRegression
    fit_index_sha256: str
    calibrate_index_sha256: str
    n_fit: int
    n_fit_positive: int
    n_calibrate: int
    n_calibrate_positive: int

    def raw(self, features: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(design(features))[:, 1]

    def probability(self, raw: np.ndarray) -> np.ndarray:
        return np.clip(self.calibrator.predict(raw), 0.0, 1.0)

    def record(self) -> dict[str, Any]:
        return {
            "hyperparameters": HYPERPARAMETERS,
            "features": list(PAIR_FEATURES),
            "sklearn_version": sklearn.__version__,
            "fit_pairs": self.n_fit,
            "fit_positive": self.n_fit_positive,
            "calibrate_pairs": self.n_calibrate,
            "calibrate_positive": self.n_calibrate_positive,
            "fit_index_sha256": self.fit_index_sha256,
            "calibrate_index_sha256": self.calibrate_index_sha256,
            "calibration": "isotonic, out_of_bounds clip",
        }


def fit(
    fit_pairs: pd.DataFrame, fit_labels: np.ndarray, cal_pairs: pd.DataFrame, cal_labels: np.ndarray
) -> Learned:
    """``fit_pairs`` / ``cal_pairs`` carry ``a_id``, ``b_id`` and ``PAIR_FEATURES``; labels are
    0/1 arrays of the same length. Nothing from any other fold enters."""
    model = HistGradientBoostingClassifier(**HYPERPARAMETERS)
    model.fit(design(fit_pairs), fit_labels)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(model.predict_proba(design(cal_pairs))[:, 1], cal_labels)
    return Learned(
        model=model,
        calibrator=calibrator,
        fit_index_sha256=index_sha256(fit_pairs),
        calibrate_index_sha256=index_sha256(cal_pairs),
        n_fit=int(len(fit_pairs)),
        n_fit_positive=int(fit_labels.sum()),
        n_calibrate=int(len(cal_pairs)),
        n_calibrate_positive=int(cal_labels.sum()),
    )
