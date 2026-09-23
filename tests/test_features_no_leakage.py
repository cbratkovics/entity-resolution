"""Leakage discipline on the real sample (docs/BRIEF.md 2.11). The assertions arrive with the
fitted objects in Phases 3 and 4; until then the module skips with the same reason it will use
when data/ is absent, so the gate exists before anything can leak through it."""

from __future__ import annotations

import pytest

from entity_resolution.config import DATA_DIR

pytestmark = pytest.mark.skipif(
    not (DATA_DIR.exists() and any(DATA_DIR.iterdir())),
    reason="real sample absent: data/ is git-ignored and only the full build creates it",
)


def test_no_test_b_id_in_any_fitted_index() -> None:
    pytest.skip("fitted objects arrive in Phase 4")


def test_rules_thresholds_recompute_from_fit_alone() -> None:
    pytest.skip("rules_v1 arrives in Phase 4")


def test_calibrator_fit_index_within_calibrate_fold() -> None:
    pytest.skip("learned_v1 arrives in Phase 4")


def test_stored_pair_features_recompute_from_raw_fields() -> None:
    pytest.skip("pair features arrive in Phase 3")
