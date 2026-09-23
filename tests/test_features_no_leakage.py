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


@pytest.fixture(scope="module")
def fitted():
    from entity_resolution.config import METHODS_DIR, PAIRS_DIR

    if (
        not (METHODS_DIR / "learned_v1.json").exists()
        or not (PAIRS_DIR / "features.parquet").exists()
    ):
        pytest.skip("fitted objects absent: the full build has not reached the methods stage")
    feats = pd.read_parquet(PAIRS_DIR / "features.parquet")
    records = {p.stem: json.loads(p.read_text()) for p in METHODS_DIR.glob("*.json")}
    return feats, records


def test_no_test_a_id_in_any_fitted_index(frames, fitted) -> None:
    """ADR 0003: fitted objects saw fit-fold (classifier, thresholds) and calibrate-fold
    (calibrator) pairs of labelled A records only; the index hashes recompute from the features
    and the truth table, and no test-fold A id is in them."""
    from entity_resolution.models import labels as labels_mod
    from entity_resolution.models import learned, tiering

    feats, records = fitted
    truth = frames["truth"]
    lab = labels_mod.from_truth(truth[truth["status"] == "truth_in_sample"][["a_id", "b_id"]])
    labelled = feats["a_id"].isin(lab.labelled_a)
    fit_pairs = feats[(feats["fold"] == "fit") & labelled]
    cal_pairs = feats[(feats["fold"] == "calibrate") & labelled]
    assert not set(fit_pairs["a_id"]) & set(feats[feats["fold"] == "test"]["a_id"])
    p = records["learned_v1"]["parameters"]
    assert p["fit_index_sha256"] == learned.index_sha256(fit_pairs)
    assert p["calibrate_index_sha256"] == learned.index_sha256(cal_pairs)
    assert p["fit_pairs"] == len(fit_pairs) and p["calibrate_pairs"] == len(cal_pairs)
    assert set(records["learned_v1"]["fitted_on"].values()) == {"fit", "calibrate"}
    assert records["exact_v1"]["fitted_on"] is None
    # rules: the searched decisions are fit-fold labelled A records
    from entity_resolution.models import rules

    s = rules.score(feats)
    fit_frame = pd.DataFrame(
        {"a_id": feats["a_id"], "b_id": feats["b_id"], "score": s, "probability": s}
    )[(feats["fold"] == "fit").to_numpy() & labelled.to_numpy()]
    dec = tiering.decide(fit_frame, accept_min=1.1, review_min=1.1)
    assert records["rules_v1"]["parameters"]["fit_decision_index_sha256"] == learned.index_sha256(
        dec
    )


def test_rules_thresholds_recompute_from_fit_alone(frames, fitted) -> None:
    from entity_resolution.models import labels as labels_mod
    from entity_resolution.models import rules, tiering

    feats, records = fitted
    truth = frames["truth"]
    lab = labels_mod.from_truth(truth[truth["status"] == "truth_in_sample"][["a_id", "b_id"]])
    labelled = feats["a_id"].isin(lab.labelled_a).to_numpy()
    fit_mask = (feats["fold"] == "fit").to_numpy() & labelled
    s = rules.score(feats)
    fit_frame = pd.DataFrame(
        {"a_id": feats["a_id"], "b_id": feats["b_id"], "score": s, "probability": s}
    )[fit_mask]
    dec = tiering.decide(fit_frame, accept_min=1.1, review_min=1.1)
    dec["correct"] = [lab.is_correct(a, b) for a, b in zip(dec["a_id"], dec["b_id"], strict=True)]
    reachable = {
        a for a, b in zip(fit_frame["a_id"], fit_frame["b_id"], strict=True) if lab.is_correct(a, b)
    }
    fitted_thr = rules.fit_thresholds(dec[["score", "correct"]], len(reachable))
    stored = records["rules_v1"]["parameters"]["thresholds"]
    assert (
        fitted_thr["t_accept"] == stored["t_accept"]
        and fitted_thr["t_review"] == stored["t_review"]
    )
    assert records["rules_v1"]["tier_policy"]["auto_accept_min"] == stored["t_accept"]


def test_no_truth_column_reaches_the_methods(fitted) -> None:
    """The features frame the methods score carries ids, fold, block keys and PAIR_FEATURES;
    no label, status or truth column (ruling e: the exact_v1 audit)."""
    from entity_resolution.features.pairs import PAIR_COLUMNS

    feats, _ = fitted
    assert list(feats.columns) == list(PAIR_COLUMNS)


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
