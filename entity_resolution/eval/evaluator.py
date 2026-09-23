"""The evaluation artifact: ``artifacts/eval_<method_version>.json`` (docs/BRIEF.md 2.9 as
amended by ADR 0001, ADR 0003 and the Phase 4 rulings).

Everything reported is on the test fold. The unit of evaluation is the A record: one decision
per A (its top candidate and tier). Labelled A records (those with an in-sample truth link)
carry the accuracy metrics; an accept is correct when the accepted B is in the A record's truth
set. Unlabelled A records are counted by coverage and by ``unverified_accepts`` only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pandas as pd

from entity_resolution.config import ARTIFACTS_DIR, FOLDS, SCHEMAS_DIR
from entity_resolution.features import FEATURE_VERSION
from entity_resolution.models.labels import Labels

ARTIFACT_VERSION = "1.0"
N_BINS = 10

METRIC_DEFINITIONS: dict[str, str] = {
    "labelled_a": "Labelled A records in the test fold: those with an in-sample truth link.",
    "labelled_a_reachable": (
        "Labelled test-fold A records whose truth survived blocking: at least one candidate "
        "pair is a truth pair."
    ),
    "pair_completeness_test": (
        "labelled_a_reachable divided by labelled_a: the share of labelled test A records whose "
        "truth blocking made reachable (A-level pair completeness)."
    ),
    "precision": (
        "Among test-fold A records the method accepted, the share whose accepted B is in the "
        "A record's truth set. Over labelled A records only."
    ),
    "recall_labelled": (
        "Correct accepts divided by labelled_a_reachable. Recall against labelled pairs whose "
        "truth blocking made reachable; unlinked is not non-match."
    ),
    "recall_overall": (
        "Correct accepts divided by labelled_a: recall with the blocking loss included; equals "
        "recall_labelled times pair_completeness_test exactly."
    ),
    "f1": "Harmonic mean of precision and recall_labelled at the same tier boundary.",
    "at_auto_accept_or_review": (
        "The same figures if every review were resolved correctly: a review row counts as "
        "correct when any of its candidates is in the truth set. An upper bound."
    ),
    "coverage": (
        "Auto-accepted A records divided by all A records in the test fold, labelled or not. "
        "A volume measure, not an accuracy measure."
    ),
    "coverage_all_folds": (
        "Auto-accepted A records divided by all sampled A records across every fold. Not an "
        "accuracy measure."
    ),
    "unverified_accepts": (
        "Auto-accepts on unlabelled test-fold A records: counted by coverage, not by the "
        "accuracy metrics. share_of_accepts is their share of all test-fold auto-accepts."
    ),
    "tier_shares": (
        "Share of all test-fold A records in each tier; an A record with no candidate is "
        "reject. The three shares sum to one."
    ),
    "ambiguity_rule": (
        "Test-fold decisions the ambiguity rule moved from auto_accept to review because the "
        "top-2 probability gap was below the gap threshold."
    ),
    "calibration": (
        "decision_level: ten equal-width bins over the top candidate's probability of labelled "
        "test A records, with the observed rate of correct top candidates; pair_level: the same "
        "over every labelled test-fold pair. ECE is the count-weighted mean absolute gap; Brier "
        "the mean squared error of the probability against the label."
    ),
    "confusion": (
        "Pair-level counts over labelled test-fold pairs at each tier boundary: tp and fp are "
        "pairs at or above the boundary, fn and tn below."
    ),
}


def schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "eval_artifact.schema.json").read_text(encoding="utf-8"))


def artifact_path(method_version: str, artifacts: Path = ARTIFACTS_DIR) -> Path:
    return artifacts / f"eval_{method_version}.json"


def _rate(n: float, d: float) -> float | None:
    return round(float(n) / float(d), 6) if d else None


def _prf(correct: int, accepted: int, base: int) -> dict[str, Any]:
    p = _rate(correct, accepted)
    r = _rate(correct, base)
    f1 = (
        round(2 * p * r / (p + r), 6)
        if p and r and (p + r)
        else (0.0 if accepted or base else None)
    )
    return {
        "accepted": int(accepted),
        "correct": int(correct),
        "precision": p,
        "recall_labelled": r,
        "f1": f1,
    }


def reliability(prob: np.ndarray, label: np.ndarray) -> dict[str, Any]:
    prob = np.asarray(prob, dtype="float64")
    label = np.asarray(label, dtype="float64")
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    idx = np.clip(np.digitize(prob, edges[1:-1], right=False), 0, N_BINS - 1)
    bins = []
    ece = 0.0
    n = len(prob)
    for i in range(N_BINS):
        m = idx == i
        k = int(m.sum())
        mean_p = float(prob[m].mean()) if k else None
        rate = float(label[m].mean()) if k else None
        if k:
            ece += k / n * abs(mean_p - rate)
        bins.append(
            {
                "lower": round(float(edges[i]), 6),
                "upper": round(float(edges[i + 1]), 6),
                "n": k,
                "mean_probability": None if mean_p is None else round(mean_p, 6),
                "observed_rate": None if rate is None else round(rate, 6),
            }
        )
    brier = float(np.mean((prob - label) ** 2)) if n else None
    return {
        "n": int(n),
        "bins": bins,
        "ece": round(ece, 6) if n else None,
        "brier": None if brier is None else round(brier, 6),
    }


def confusion_at(prob: np.ndarray, label: np.ndarray, threshold: float) -> dict[str, int]:
    above = prob >= threshold
    pos = label == 1
    return {
        "tp": int((above & pos).sum()),
        "fp": int((above & ~pos).sum()),
        "fn": int((~above & pos).sum()),
        "tn": int((~above & ~pos).sum()),
    }


def evaluate(
    *,
    method_version: str,
    decisions: pd.DataFrame,
    pairs: pd.DataFrame,
    labels: Labels,
    a_folds: pd.Series,
    thresholds: dict[str, float],
    manifest_sha256: str,
    code_commit: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """``decisions``: one row per A record with a candidate (``a_id``, ``b_id``, ``score``,
    ``probability``, ``tier``, ``fold``, ``ambiguity_review``). ``pairs``: every candidate pair
    with ``a_id``, ``b_id``, ``fold``, ``probability``. ``a_folds``: fold per sampled A id
    (index = a_id) over every sampled A record, so records without candidates count as reject."""
    labelled = labels.labelled_a
    test_a = a_folds[a_folds == "test"].index
    n_test_a = int(len(test_a))
    dec = decisions.set_index("a_id")
    dec_test = dec[dec["fold"] == "test"]
    lab_test = pd.Index([a for a in test_a if a in labelled])
    n_lab = int(len(lab_test))
    # reachable: labelled test A with a truth pair among its candidates
    test_pairs = pairs[pairs["fold"] == "test"]
    pair_correct = np.array(
        [
            labels.is_correct(a, b)
            for a, b in zip(test_pairs["a_id"], test_pairs["b_id"], strict=True)
        ],
        dtype=bool,
    )
    reachable = set(test_pairs["a_id"][pair_correct])
    n_reach = int(sum(1 for a in lab_test if a in reachable))
    # decisions of labelled test A
    d_lab = dec_test[dec_test.index.isin(lab_test)]
    d_correct = np.array(
        [labels.is_correct(a, b) for a, b in zip(d_lab.index, d_lab["b_id"], strict=True)],
        dtype=bool,
    )
    accepted = (d_lab["tier"] == "auto_accept").to_numpy()
    review = (d_lab["tier"] == "review").to_numpy()
    at_accept = _prf(int((accepted & d_correct).sum()), int(accepted.sum()), n_reach)
    # upper bound: a review row is correct when any candidate of that A is in the truth set
    review_ok = d_lab.index.isin(reachable)
    at_either = _prf(
        int((accepted & d_correct).sum() + (review & review_ok).sum()),
        int(accepted.sum() + review.sum()),
        n_reach,
    )
    correct_accepts = int((accepted & d_correct).sum())
    pc_test = _rate(n_reach, n_lab)
    recall_overall = _rate(correct_accepts, n_lab)
    # coverage, unverified accepts, tier shares over every test A (no candidate = reject)
    tiers_all = dec_test["tier"].reindex(test_a).fillna("reject")
    n_accept_test = int((tiers_all == "auto_accept").sum())
    unverified = int(((tiers_all == "auto_accept") & ~tiers_all.index.isin(labelled)).sum())
    n_all_a = int(len(a_folds))
    n_accept_all = int((dec["tier"] == "auto_accept").sum())
    tier_shares = {
        t: _rate(int((tiers_all == t).sum()), n_test_a) for t in ("auto_accept", "review", "reject")
    }
    # calibration: decision level (labelled test A top candidates) and pair level
    decision_level = reliability(d_lab["probability"].to_numpy(dtype="float64"), d_correct)
    lab_pairs = test_pairs[test_pairs["a_id"].isin(labelled)]
    lab_pair_label = pair_correct[test_pairs["a_id"].isin(labelled).to_numpy()]
    pair_prob = lab_pairs["probability"].to_numpy(dtype="float64")
    pair_level = reliability(pair_prob, lab_pair_label)
    fold_counts = {}
    for f in FOLDS:
        a_in = a_folds[a_folds == f].index
        fold_counts[f] = {
            "a_records": int(len(a_in)),
            "labelled_a_records": int(sum(1 for a in a_in if a in labelled)),
            "candidate_pairs": int((pairs["fold"] == f).sum()),
            "decisions": int((dec["fold"] == f).sum()),
        }
    return {
        "artifact_version": ARTIFACT_VERSION,
        "method_version": method_version,
        "generated_at_utc": generated_at_utc,
        "input": {
            "manifest_sha256": manifest_sha256,
            "feature_version": FEATURE_VERSION,
            "code_commit": code_commit,
        },
        "fold_counts": fold_counts,
        "thresholds": {
            "auto_accept_min": thresholds["auto_accept_min"],
            "review_min": thresholds["review_min"],
            "ambiguity_gap": thresholds["ambiguity_gap"],
        },
        "metric_definitions": dict(METRIC_DEFINITIONS),
        "metrics": {
            "test_a": n_test_a,
            "labelled_a": n_lab,
            "labelled_a_reachable": n_reach,
            "pair_completeness_test": pc_test,
            "at_auto_accept": at_accept,
            "at_auto_accept_or_review": at_either,
            "recall_overall": recall_overall,
            "coverage": _rate(n_accept_test, n_test_a),
            "coverage_all_folds": _rate(n_accept_all, n_all_a),
            "unverified_accepts": {
                "count": unverified,
                "share_of_accepts": _rate(unverified, n_accept_test),
            },
            "tier_shares": tier_shares,
            "ambiguity_rule": {
                "decisions_moved_to_review": int(
                    dec_test["ambiguity_review"].fillna(False).astype(bool).sum()
                ),
                "review_queue": int((tiers_all == "review").sum()),
            },
            "calibration": {"decision_level": decision_level, "pair_level": pair_level},
            "confusion": {
                "auto_accept": confusion_at(
                    pair_prob, lab_pair_label.astype(int), thresholds["auto_accept_min"]
                ),
                "review": confusion_at(
                    pair_prob, lab_pair_label.astype(int), thresholds["review_min"]
                ),
            },
        },
    }


def validate(artifact: dict[str, Any]) -> None:
    jsonschema.validate(artifact, schema())


def write(artifact: dict[str, Any], artifacts: Path = ARTIFACTS_DIR) -> Path:
    validate(artifact)
    path = artifact_path(artifact["method_version"], artifacts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_all(artifacts: Path = ARTIFACTS_DIR) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(artifacts.glob("eval_*.json"))
    ]
