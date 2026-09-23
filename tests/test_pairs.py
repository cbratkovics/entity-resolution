"""PAIR_FEATURES order is stable, the nullable year is handled, and symmetric features are
symmetric."""

from __future__ import annotations

import pandas as pd

from entity_resolution.data import sample
from entity_resolution.features import blocking, pairs


def _sides():
    a = sample.normalize_sample(
        pd.DataFrame(
            {
                "source": "musicbrainz",
                "native_id": ["a0", "a1", "a2"],
                "title": ["Abbey Road (2019 Remaster)", "Help", "Now That's Music"],
                "artist_credit": ["The Beatles", "The Beatles", "Various Artists"],
                "year": [1969, None, 2001],
            }
        )
    )
    b = sample.normalize_sample(
        pd.DataFrame(
            {
                "source": "discogs",
                "native_id": ["1", "2", "3"],
                "title": ["Abbey Road", "Help!", "Now That's Music Vol. 2"],
                "artist_credit": ["Beatles, The", "The Beatles", "Various"],
                "year": [1969, 1965, 2002],
            }
        )
    )
    return a, b


def test_feature_order_and_values() -> None:
    a, b = _sides()
    cands, _ = blocking.build_candidates(a, b)
    cands["fold"] = "fit"
    feats = pairs.pair_features(cands, a, b)
    assert list(feats.columns) == list(pairs.PAIR_COLUMNS)
    row = feats.set_index(["a_id", "b_id"]).loc[("a0", "1")]
    assert row["title_exact_norm"] == 1 and row["artist_full_exact"] == 1
    assert (
        row["qualifier_mismatch"] == 1 and row["year_diff"] == 0 and row["year_either_missing"] == 0
    )
    assert row["title_ratio"] == 1.0 and row["artist_jw"] == 1.0
    va = feats.set_index(["a_id", "b_id"]).loc[("a2", "3")]
    assert va["both_va"] == 1 and va["year_diff"] == 1 and va["artist_ratio"] == 1.0
    assert 0.0 <= va["title_ratio"] < 1.0


def test_nullable_year_and_symmetry() -> None:
    a, b = _sides()
    cands, _ = blocking.build_candidates(a, b)
    feats = pairs.pair_features(cands, a, b)
    row = feats.set_index(["a_id", "b_id"]).loc[("a1", "2")]
    assert pd.isna(row["year_diff"]) and row["year_either_missing"] == 1
    swapped = pairs.pair_features(cands.rename(columns={"a_id": "b_id", "b_id": "a_id"}), b, a)
    for col in (
        "title_ratio",
        "title_token_set",
        "title_jw",
        "artist_ratio",
        "artist_jw",
        "title_len_diff",
    ):
        assert list(feats[col].round(9)) == list(swapped[col].round(9)), col
