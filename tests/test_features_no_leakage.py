"""Leakage discipline on the real sample (docs/BRIEF.md 2.11, rule 6). Skipped with a stated
reason when data/ is absent; the assertions on fitted objects arrive with them in Phases 3
and 4."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from entity_resolution.config import MANIFEST_PATH, SAMPLE_DIR
from entity_resolution.data import sample

pytestmark = pytest.mark.skipif(
    not (SAMPLE_DIR / "a.parquet").exists(),
    reason="real sample absent: data/ is git-ignored and only `make full` creates it",
)


@pytest.fixture(scope="module")
def frames() -> dict[str, pd.DataFrame]:
    return {n: pd.read_parquet(SAMPLE_DIR / f"{n}.parquet") for n in ("a", "b", "truth")}


def test_sample_frames_carry_no_truth_identifier(frames) -> None:
    """The matcher's input never carries the other side's id or a label: truth lives only in
    truth.parquet (rule 6, ADR 0001)."""
    for side in ("a", "b"):
        cols = set(frames[side].columns)
        assert not cols & {"a_id", "b_id", "status", "is_labelled", "a_labelled", "truth"}
    assert set(frames["truth"].columns) == {"a_id", "b_id", "a_primary_type", "status"}


def test_manifest_hashes_match_the_files_on_disk(frames) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for name, rec in manifest["sample"]["files"].items():
        assert rec["rows"] == len(frames[name])
        assert sample.content_sha256(frames[name]) == rec["content_sha256"]


def test_sample_membership_recomputes_from_the_manifest_thresholds(frames) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for name, source in (("a", manifest["side_a"]), ("b", "discogs")):
        df = frames[name]
        thr = manifest["sample"]["thresholds"][name]
        hashes = sample.hash_column(source, df["native_id"])
        assert (hashes == df["membership_hash"]).all()
        unlinked = df[~df["is_linked"]]
        assert (unlinked["membership_hash"] <= thr["threshold_hex"]).all()
        assert len(unlinked) == thr["selected"] and int(df["is_linked"].sum()) == thr["linked"]


def test_every_labelled_a_and_its_b_are_in_the_sample(frames) -> None:
    in_sample = frames["truth"][frames["truth"]["status"] == "truth_in_sample"]
    assert set(in_sample["a_id"]) <= set(frames["a"]["native_id"])
    assert set(in_sample["b_id"]) <= set(frames["b"]["native_id"])
    assert (frames["truth"]["status"] == "truth_unsampled").sum() == 0


def test_no_test_b_id_in_any_fitted_index() -> None:
    pytest.skip("fitted objects arrive in Phase 4")


def test_rules_thresholds_recompute_from_fit_alone() -> None:
    pytest.skip("rules_v1 arrives in Phase 4")


def test_calibrator_fit_index_within_calibrate_fold() -> None:
    pytest.skip("learned_v1 arrives in Phase 4")


def test_stored_pair_features_recompute_from_raw_fields() -> None:
    pytest.skip("pair features arrive in Phase 3")
