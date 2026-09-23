"""Blocking keys as specified in docs/BRIEF.md 2.4; VA records skip artist keys; the cap counts
overflow instead of dropping it silently; pair completeness is measured per key and for the
union."""

from __future__ import annotations

import pandas as pd

from entity_resolution.data import sample
from entity_resolution.features import blocking


def _rec(**kw):
    base = dict(
        title_norm="abbey road",
        title_tokens=["abbey", "road"],
        artist_norm="beatles",
        year=1969,
        is_various_artists=False,
        is_self_titled=False,
        title_metaphone="APK",
        artist_metaphone="PTLS",
    )
    base.update(kw)
    return blocking.keys_for(**base)


def test_keys_emitted_as_specified() -> None:
    keys = dict(_rec())
    assert keys["k_title3"] == "abbey road"
    assert len(keys["k_title_sorted"]) == 16
    assert keys["k_phonetic"] == "APK|PTLS"
    assert [k for t, k in _rec() if t == "k_artist_year"] == [
        "beatles|1968",
        "beatles|1969",
        "beatles|1970",
    ]
    assert "k_self_titled" not in keys
    assert dict(_rec(is_self_titled=True))["k_self_titled"] == "beatles"
    assert dict(_rec(title_norm="a b c d e"))["k_title3"] == "a b c"


def test_missing_year_and_empty_title_and_va() -> None:
    types = {t for t, _ in _rec(year=None)}
    assert "k_artist_year" not in types and "k_phonetic" in types
    assert _rec(title_norm="", title_tokens=[], title_metaphone="") == [
        ("k_artist_year", "beatles|1968"),
        ("k_artist_year", "beatles|1969"),
        ("k_artist_year", "beatles|1970"),
    ]
    va = {t for t, _ in _rec(is_various_artists=True, is_self_titled=True, artist_norm="various")}
    assert va == blocking.TITLE_KEYS


def _frames():
    a = pd.DataFrame(
        {
            "source": "musicbrainz",
            "native_id": [f"a{i}" for i in range(6)],
            "title": ["Abbey Road", "Help", "Help", "Greatest Hits", "Greatest Hits", "Zzz"],
            "artist_credit": [
                "The Beatles",
                "The Beatles",
                "Various Artists",
                "Various",
                "Prince (2)",
                "Prince",
            ],
            "year": [1969, 1965, None, 1990, 1991, 1980],
        }
    )
    b = pd.DataFrame(
        {
            "source": "discogs",
            "native_id": [f"{i}" for i in range(1, 8)],
            "title": [
                "Abbey Road",
                "Help!",
                "Help",
                "Greatest Hits",
                "Greatest Hits",
                "Greatest Hits",
                "Nothing",
            ],
            "artist_credit": [
                "Beatles, The",
                "The Beatles",
                "Various",
                "Various",
                "Prince (2)",
                "Prince",
                "Nobody",
            ],
            "year": [1969, 1965, 1999, 1990, 1990, 1991, 2000],
        }
    )
    return sample.normalize_sample(a), sample.normalize_sample(b)


def test_union_candidates_record_keys_and_completeness() -> None:
    a, b = _frames()
    truth = pd.DataFrame({"a_id": ["a0", "a1", "a3"], "b_id": ["1", "2", "4"]})
    cands, rep = blocking.build_candidates(a, b, truth)
    got = {(r.a_id, r.b_id): list(r.block_keys) for r in cands.itertuples()}
    assert "k_artist_year" in got[("a0", "1")] and "k_title3" in got[("a0", "1")]
    assert ("a2", "3") in got and set(
        got[("a2", "3")]
    ) <= blocking.TITLE_KEYS  # VA: title keys only
    assert rep["pair_completeness"]["union"] == 1.0 and rep["pair_completeness"]["truth_pairs"] == 3
    assert rep["pair_completeness"]["per_key"]["k_title3"] == 1.0
    assert rep["union_pairs"] == len(cands) and rep["cap_overflow"]["pairs_dropped"] == 0
    assert rep["reduction_ratio"] is not None and 0 < rep["reduction_ratio"] < 1
    assert list(cands.columns) == ["a_id", "b_id", "block_keys", "n_block_keys"]


def test_cap_counts_overflow_instead_of_dropping_silently() -> None:
    a, b = _frames()
    cands, rep = blocking.build_candidates(a, b, cap=1)
    assert rep["cap_overflow"]["a_records_over_cap"] >= 1
    assert (
        rep["cap_overflow"]["pairs_dropped"]
        == rep["union_pairs"] - rep["candidate_pairs_after_cap"]
    )
    assert cands.groupby("a_id").size().max() == 1
    kept = cands.set_index("a_id").loc["a3"]  # the kept candidate has the most keys
    assert kept["n_block_keys"] == cands[cands["a_id"] == "a3"]["n_block_keys"].max()
