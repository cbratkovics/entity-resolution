"""Phase 4 stages of the full build: fit the three methods on their folds, decide one tier per
A record, write the mapping tables, evaluate on the test fold, sweep the review cost, and
apply the too-good-to-be-true rule (docs/BRIEF.md 2.7 to 2.9 as amended).

Fit order and inputs (rule 6): rules thresholds on fit-fold labelled decisions; the classifier
on fit-fold pairs of labelled A records; the calibrator on calibrate-fold labelled pairs;
everything reported on test. The truth table reaches only ``labels`` and the evaluator.
"""

from __future__ import annotations

import gzip
import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from entity_resolution.config import (
    MAPPING_ARTIFACT_DIR,
    MAPPING_DIR,
    METHODS_DIR,
    REVIEW_SENSITIVITY_PATH,
)
from entity_resolution.eval import evaluator, review_cost, split
from entity_resolution.features import FEATURE_VERSION
from entity_resolution.models import exact, learned, registry, rules, tiering
from entity_resolution.models import labels as labels_mod

TOO_GOOD_F1_GAP = 0.15
TOO_GOOD_PRECISION = 0.995
TOO_GOOD_MIN_PAIRS = 1000
MAPPING_COLUMNS = (
    "a_id",
    "b_id",
    "method_version",
    "feature_version",
    "score",
    "probability",
    "tier",
    "block_keys",
    "top2_gap",
    "fold",
    "run_id",
    "decided_at_utc",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mapping_frame(
    decisions: pd.DataFrame, method_version: str, run_id: str, decided_at: str
) -> pd.DataFrame:
    non_reject = decisions[decisions["tier"] != "reject"].copy()
    out = pd.DataFrame(
        {
            "a_id": non_reject["a_id"].astype("string"),
            "b_id": non_reject["b_id"].astype("string"),
            "method_version": method_version,
            "feature_version": FEATURE_VERSION,
            "score": non_reject["score"].astype("float64").round(6),
            "probability": non_reject["probability"].astype("float64").round(6),
            "tier": non_reject["tier"].astype("string"),
            "block_keys": non_reject["block_keys"].map(
                lambda v: "|".join(map(str, v)) if v is not None else ""
            ),
            "top2_gap": non_reject["top2_gap"].astype("Float64").round(6),
            "fold": non_reject["fold"].astype("string"),
            "run_id": run_id,
            "decided_at_utc": decided_at,
        }
    )
    return out[list(MAPPING_COLUMNS)].sort_values(["a_id"]).reset_index(drop=True)


def write_mapping(frame: pd.DataFrame, method_version: str) -> dict[str, Any]:
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    MAPPING_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    full = MAPPING_DIR / f"mapping_{method_version}.parquet"
    frame.to_parquet(full, index=False, engine="pyarrow", compression="zstd")
    test = frame[frame["fold"] == "test"]
    exhibit = MAPPING_ARTIFACT_DIR / f"mapping_{method_version}.test.csv.gz"
    with gzip.open(exhibit, "wt", encoding="utf-8", newline="", compresslevel=9) as fh:
        test.to_csv(fh, index=False, lineterminator="\n")
    return {
        "full_rows": int(len(frame)),
        "full_path": full.relative_to(full.parents[2]).as_posix(),
        "test_rows": int(len(test)),
        "test_exhibit": exhibit.relative_to(exhibit.parents[2]).as_posix(),
        "test_exhibit_sha256": _sha256_file(exhibit),
    }


def run_methods(
    *,
    features: pd.DataFrame,
    in_sample: pd.DataFrame,
    a_ids: pd.Series,
    manifest_sha256: str,
    code_commit: str,
    run_id: str,
    now: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
    """Returns (eval artifacts by method, review sensitivity artifact, too-good-to-be-true
    findings). Writes method records, eval artifacts, mappings and the sensitivity artifact."""
    labels = labels_mod.from_truth(in_sample)
    a_folds = pd.Series(split.assign(a_ids).to_numpy(), index=a_ids.to_numpy())
    pair_label = labels.pair_labels(features)
    labelled_mask = pair_label.notna().to_numpy()
    fit_mask = (features["fold"] == "fit").to_numpy() & labelled_mask
    cal_mask = (features["fold"] == "calibrate").to_numpy() & labelled_mask
    evals: dict[str, dict[str, Any]] = {}
    sensitivity: dict[str, Any] = {}
    findings: list[str] = []
    records: dict[str, dict[str, Any]] = {}

    def base_pairs(score: np.ndarray, probability: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "a_id": features["a_id"].astype("string").to_numpy(),
                "b_id": features["b_id"].astype("string").to_numpy(),
                "fold": features["fold"].astype("string").to_numpy(),
                "block_keys": features["block_keys"].to_numpy(),
                "score": score,
                "probability": probability,
            }
        )

    # ---- exact_v1 -----------------------------------------------------------------------------
    s = exact.score(features)
    pairs_exact = base_pairs(s, s)
    thr = {
        "auto_accept_min": tiering.AUTO_ACCEPT_MIN,
        "review_min": tiering.REVIEW_MIN,
        "ambiguity_gap": tiering.AMBIGUITY_GAP,
    }
    records["exact_v1"] = {
        "method_version": "exact_v1",
        "definition": exact.DEFINITION,
        "fitted_on": None,
        "feature_version": FEATURE_VERSION,
        "parameters": {"score_values": [0, 1]},
        "tier_policy": thr,
        "code_commit": code_commit,
        "created_at_utc": now,
    }
    _finish(
        "exact_v1",
        pairs_exact,
        thr,
        records,
        labels,
        a_folds,
        evals,
        sensitivity,
        manifest_sha256,
        code_commit,
        now,
        run_id,
    )

    # ---- rules_v1 -----------------------------------------------------------------------------
    s = rules.score(features)
    pairs_rules = base_pairs(s, s)
    fit_dec = tiering.decide(
        pairs_rules[fit_mask], accept_min=1.1, review_min=1.1
    )  # tiers unused here
    fit_dec = fit_dec[fit_dec["a_id"].isin(labels.labelled_a)]
    fit_dec["correct"] = [
        labels.is_correct(a, b) for a, b in zip(fit_dec["a_id"], fit_dec["b_id"], strict=True)
    ]
    fit_pairs_rules = pairs_rules[fit_mask]
    reachable_fit = {
        a
        for a, b in zip(fit_pairs_rules["a_id"], fit_pairs_rules["b_id"], strict=True)
        if labels.is_correct(a, b)
    }
    fitted = rules.fit_thresholds(fit_dec[["score", "correct"]], len(reachable_fit))
    thr = {
        "auto_accept_min": fitted["t_accept"],
        "review_min": fitted["t_review"],
        "ambiguity_gap": tiering.AMBIGUITY_GAP,
    }
    records["rules_v1"] = {
        "method_version": "rules_v1",
        "definition": rules.DEFINITION,
        "fitted_on": {"thresholds": "fit"},
        "feature_version": FEATURE_VERSION,
        "parameters": {
            "weights": rules.WEIGHTS,
            "thresholds": fitted,
            "fit_decision_index_sha256": learned.index_sha256(fit_dec),
        },
        "tier_policy": thr,
        "code_commit": code_commit,
        "created_at_utc": now,
    }
    _finish(
        "rules_v1",
        pairs_rules,
        thr,
        records,
        labels,
        a_folds,
        evals,
        sensitivity,
        manifest_sha256,
        code_commit,
        now,
        run_id,
    )

    # ---- learned_v1 ---------------------------------------------------------------------------
    fit_pairs = features[fit_mask]
    cal_pairs = features[cal_mask]
    model = learned.fit(
        fit_pairs,
        pair_label[fit_mask].to_numpy(dtype="int64"),
        cal_pairs,
        pair_label[cal_mask].to_numpy(dtype="int64"),
    )
    raw = model.raw(features)
    pairs_learned = base_pairs(raw, model.probability(raw))
    thr = {
        "auto_accept_min": tiering.AUTO_ACCEPT_MIN,
        "review_min": tiering.REVIEW_MIN,
        "ambiguity_gap": tiering.AMBIGUITY_GAP,
    }
    records["learned_v1"] = {
        "method_version": "learned_v1",
        "definition": learned.DEFINITION,
        "fitted_on": {"model": "fit", "calibrator": "calibrate"},
        "feature_version": FEATURE_VERSION,
        "parameters": model.record(),
        "tier_policy": thr,
        "code_commit": code_commit,
        "created_at_utc": now,
    }
    _finish(
        "learned_v1",
        pairs_learned,
        thr,
        records,
        labels,
        a_folds,
        evals,
        sensitivity,
        manifest_sha256,
        code_commit,
        now,
        run_id,
    )

    # ---- too-good-to-be-true ------------------------------------------------------------------
    f1 = {m: (evals[m]["metrics"]["at_auto_accept"]["f1"] or 0.0) for m in evals}
    if f1["learned_v1"] - f1["rules_v1"] > TOO_GOOD_F1_GAP:
        findings.append(
            f"learned_v1 F1 {f1['learned_v1']} exceeds rules_v1 F1 {f1['rules_v1']} by more than {TOO_GOOD_F1_GAP}"
        )
    for m in ("rules_v1", "learned_v1"):
        acc = evals[m]["metrics"]["at_auto_accept"]
        if (
            acc["precision"] is not None
            and acc["precision"] >= TOO_GOOD_PRECISION
            and acc["accepted"] > TOO_GOOD_MIN_PAIRS
        ):
            findings.append(f"{m} precision {acc['precision']} on {acc['accepted']} accepts")
    sensitivity_artifact = {
        "sensitivity_version": "1.0",
        "generated_at_utc": now,
        "feature_version": FEATURE_VERSION,
        "code_commit": code_commit,
        "methods": sensitivity,
    }
    registry.validate_and_write(sensitivity_artifact, "review_sensitivity", REVIEW_SENSITIVITY_PATH)
    return evals, sensitivity_artifact, findings


def _finish(
    method_version: str,
    pairs: pd.DataFrame,
    thr: dict[str, float],
    records: dict[str, dict[str, Any]],
    labels: labels_mod.Labels,
    a_folds: pd.Series,
    evals: dict[str, dict[str, Any]],
    sensitivity: dict[str, Any],
    manifest_sha256: str,
    code_commit: str,
    now: str,
    run_id: str,
) -> None:
    decisions = tiering.decide(
        pairs,
        accept_min=thr["auto_accept_min"],
        review_min=thr["review_min"],
        ambiguity_gap=thr["ambiguity_gap"],
    )
    mapping = write_mapping(mapping_frame(decisions, method_version, run_id, now), method_version)
    records[method_version]["parameters"]["mapping"] = mapping
    registry.write_method_record(records[method_version], METHODS_DIR)
    art = evaluator.evaluate(
        method_version=method_version,
        decisions=decisions,
        pairs=pairs,
        labels=labels,
        a_folds=a_folds,
        thresholds=thr,
        manifest_sha256=manifest_sha256,
        code_commit=code_commit,
        generated_at_utc=now,
    )
    evaluator.write(art)
    evals[method_version] = art
    test_dec = decisions[decisions["fold"] == "test"]
    correct = np.array(
        [labels.is_correct(a, b) for a, b in zip(test_dec["a_id"], test_dec["b_id"], strict=True)],
        dtype=bool,
    )
    is_labelled = test_dec["a_id"].isin(labels.labelled_a).to_numpy()
    sensitivity[method_version] = review_cost.sweep(
        test_dec,
        correct,
        is_labelled,
        review_min=thr["review_min"],
        chosen_accept=thr["auto_accept_min"],
    )
    m = art["metrics"]
    print(
        f"   {method_version}: precision {m['at_auto_accept']['precision']} recall_labelled "
        f"{m['at_auto_accept']['recall_labelled']} f1 {m['at_auto_accept']['f1']} coverage {m['coverage']} "
        f"unverified {m['unverified_accepts']} tiers {m['tier_shares']} ece {m['calibration']['decision_level']['ece']}",
        file=sys.stderr,
    )
