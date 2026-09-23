"""The evaluation artifact: ``artifacts/eval_<method_version>.json`` (docs/BRIEF.md 2.9).

Phase 0 ships the artifact writer and the metric definitions only; the metric computation on
the ``test`` fold arrives in Phase 4 and fills ``metrics``. Every artifact is validated against
``artifacts/schemas/eval_artifact.schema.json`` before it is written, so a half-filled artifact
never reaches the tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from entity_resolution.config import ARTIFACTS_DIR, FOLDS, SCHEMAS_DIR
from entity_resolution.features import FEATURE_VERSION

ARTIFACT_VERSION = "1.0"

METRIC_DEFINITIONS: dict[str, str] = {
    "pair_completeness": (
        "Share of sampled truth pairs in the test fold that blocking produced as a candidate "
        "pair; reported for the union of keys and per key."
    ),
    "precision": (
        "Among test-fold pairs the method accepted, the share that are truth pairs. Reported at "
        "auto_accept and at auto_accept plus review (the upper bound if every review were "
        "resolved correctly)."
    ),
    "recall_labelled": (
        "Among sampled truth pairs in the test fold that blocking produced, the share the method "
        "accepted. Recall against labelled pairs only: unlinked is not non-match."
    ),
    "f1": "Harmonic mean of precision and recall_labelled at the same tier boundary.",
    "recall_overall": (
        "recall_labelled multiplied by pair_completeness: recall with the blocking loss included."
    ),
    "coverage": (
        "Accepted A records divided by all A records in the test fold. A volume measure, not an "
        "accuracy measure."
    ),
    "coverage_all_folds": (
        "Accepted A records divided by all A records across every fold. Not an accuracy measure; "
        "reported so the size of the mapping is visible."
    ),
    "tier_shares": "Share of test-fold A records in each tier; the three shares sum to one.",
    "calibration": (
        "Ten equal-width probability bins with the mean predicted probability and the observed "
        "truth rate in each; ECE is the count-weighted mean absolute gap, Brier the mean squared "
        "error of the probability against the label."
    ),
    "confusion": "True and false accepts and rejects at each tier boundary on the test fold.",
}


def schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "eval_artifact.schema.json").read_text(encoding="utf-8"))


def artifact_path(method_version: str, artifacts: Path = ARTIFACTS_DIR) -> Path:
    return artifacts / f"eval_{method_version}.json"


def new_artifact(
    method_version: str,
    *,
    manifest_sha256: str,
    code_commit: str,
    fold_counts: dict[str, dict[str, int]],
    generated_at_utc: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble an artifact. ``metrics`` is ``None`` until Phase 4 computes it."""
    missing = [f for f in FOLDS if f not in fold_counts]
    if missing:
        raise ValueError(f"fold_counts is missing folds {missing}")
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
        "metric_definitions": dict(METRIC_DEFINITIONS),
        "metrics": metrics,
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
