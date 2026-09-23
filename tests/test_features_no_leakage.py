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


def test_candidates_carry_no_truth_column_and_inherit_the_a_fold(frames) -> None:
    from entity_resolution.config import PAIRS_DIR
    from entity_resolution.eval import split

    if not (PAIRS_DIR / "candidates.parquet").exists():
        pytest.skip("candidates absent: the full build has not reached blocking")
    cands = pd.read_parquet(PAIRS_DIR / "candidates.parquet")
    assert not set(cands.columns) & {"status", "is_truth", "label", "truth"}
    head = cands.head(5000)
    assert (head["fold"] == head["a_id"].map(split.fold_for)).all()


def test_stored_pair_features_recompute_from_raw_fields(frames) -> None:
    """Two hundred random real pairs, recomputed from the raw fields through the one normaliser
    and the one feature function, match the stored features exactly."""
    from entity_resolution.config import PAIRS_DIR
    from entity_resolution.features import normalize, pairs

    if not (PAIRS_DIR / "features.parquet").exists():
        pytest.skip("features absent: the full build has not reached pair features")
    feats = pd.read_parquet(PAIRS_DIR / "features.parquet")
    picked = feats.sample(n=200, random_state=0)
    raw_cols = ["source", "native_id", "title", "artist_credit", "year"]
    a_raw = frames["a"][raw_cols][frames["a"]["native_id"].isin(picked["a_id"])]
    b_raw = frames["b"][raw_cols][frames["b"]["native_id"].isin(picked["b_id"])]
    a_norm = normalize.normalize_frame(a_raw)
    b_norm = normalize.normalize_frame(b_raw)
    recomputed = pairs.pair_features(
        picked[["a_id", "b_id", "fold", "block_keys"]].assign(
            n_block_keys=picked["n_block_keys"].to_numpy()
        ),
        a_norm,
        b_norm,
    )
    for col in pairs.PAIR_FEATURES:
        left = recomputed[col].astype("float64").to_numpy()
        right = picked[col].astype("float64").to_numpy()
        assert (pd.isna(left) == pd.isna(right)).all(), col
        assert (left[~pd.isna(left)] == right[~pd.isna(right)]).all(), col
