"""The evaluation artifact writer: assembly, schema validation, round trip. Metric arithmetic
is tested in Phase 4 on the hand-built pair fixture."""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from entity_resolution.eval import evaluator
from entity_resolution.features import FEATURE_VERSION

FOLDS = {
    f: {"a_records": 0, "b_records": 0, "candidate_pairs": 0, "truth_pairs": 0}
    for f in ("fit", "calibrate", "test")
}


def _artifact(**kw):
    return evaluator.new_artifact(
        "exact_v1",
        manifest_sha256="0" * 64,
        code_commit="abc",
        fold_counts=FOLDS,
        generated_at_utc="2026-09-22T00:00:00+00:00",
        **kw,
    )


def test_artifact_without_metrics_validates_and_round_trips(tmp_path: Path) -> None:
    art = _artifact()
    assert art["input"]["feature_version"] == FEATURE_VERSION
    assert set(art["metric_definitions"]) == set(evaluator.METRIC_DEFINITIONS)
    path = evaluator.write(art, tmp_path)
    assert path.name == "eval_exact_v1.json"
    assert evaluator.read_all(tmp_path) == [art]


def test_missing_fold_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing folds"):
        evaluator.new_artifact(
            "exact_v1",
            manifest_sha256="x",
            code_commit="c",
            fold_counts={"fit": FOLDS["fit"]},
            generated_at_utc="t",
        )


def test_partial_metrics_block_fails_validation() -> None:
    art = _artifact(metrics={"coverage": 0.5})
    with pytest.raises(jsonschema.ValidationError):
        evaluator.validate(art)


def test_every_metric_has_a_definition() -> None:
    for key in (
        "pair_completeness",
        "precision",
        "recall_labelled",
        "recall_overall",
        "coverage",
        "coverage_all_folds",
        "tier_shares",
        "calibration",
        "confusion",
    ):
        assert evaluator.METRIC_DEFINITIONS[key].strip()
