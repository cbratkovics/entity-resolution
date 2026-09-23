"""Pair features (docs/BRIEF.md 2.6): one function over the candidate pairs, returning the
fixed column list ``PAIR_FEATURES`` in this order. String similarities come from rapidfuzz on
the normalised forms; ``year_diff`` is nullable; everything else is a number in [0, 1] or a
count. Symmetric in A and B except where the definition is not (nothing here is).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler

PAIR_FEATURES: tuple[str, ...] = (
    "title_ratio",
    "title_partial",
    "title_token_sort",
    "title_token_set",
    "title_jw",
    "artist_ratio",
    "artist_token_set",
    "artist_jw",
    "artist_full_exact",
    "title_exact_norm",
    "year_diff",
    "year_either_missing",
    "both_va",
    "title_len_diff",
    "n_block_keys",
    "qualifier_mismatch",
)
PAIR_COLUMNS: tuple[str, ...] = ("a_id", "b_id", "fold", "block_keys", *PAIR_FEATURES)


def _sim(scorer, left: list[str], right: list[str], workers: int = -1) -> np.ndarray:
    if not left:
        return np.zeros(0, dtype="float64")
    return np.asarray(process.cpdist(left, right, scorer=scorer, workers=workers), dtype="float64")


def _tuple(v) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return (v,)
    return tuple(str(x) for x in v)


def pair_features(pairs: pd.DataFrame, a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """``pairs`` has ``a_id``, ``b_id``, ``block_keys``, ``n_block_keys`` and optionally ``fold``;
    ``a`` and ``b`` are normalised frames indexed by ``native_id``. Returns ``PAIR_COLUMNS``."""
    ai = a.set_index("native_id")
    bi = b.set_index("native_id")
    la = ai.loc[pairs["a_id"].to_numpy()]
    lb = bi.loc[pairs["b_id"].to_numpy()]
    ta, tb = la["title_norm"].fillna("").tolist(), lb["title_norm"].fillna("").tolist()
    aa, ab = la["artist_norm"].fillna("").tolist(), lb["artist_norm"].fillna("").tolist()
    out = pd.DataFrame(index=pairs.index)
    out["a_id"] = pairs["a_id"].astype("string").to_numpy()
    out["b_id"] = pairs["b_id"].astype("string").to_numpy()
    out["fold"] = pairs["fold"].astype("string").to_numpy() if "fold" in pairs else pd.NA
    out["block_keys"] = pairs["block_keys"].map(lambda v: list(_tuple(v))).to_numpy()
    out["title_ratio"] = _sim(fuzz.ratio, ta, tb) / 100.0
    out["title_partial"] = _sim(fuzz.partial_ratio, ta, tb) / 100.0
    out["title_token_sort"] = _sim(fuzz.token_sort_ratio, ta, tb) / 100.0
    out["title_token_set"] = _sim(fuzz.token_set_ratio, ta, tb) / 100.0
    out["title_jw"] = _sim(JaroWinkler.normalized_similarity, ta, tb)
    out["artist_ratio"] = _sim(fuzz.ratio, aa, ab) / 100.0
    out["artist_token_set"] = _sim(fuzz.token_set_ratio, aa, ab) / 100.0
    out["artist_jw"] = _sim(JaroWinkler.normalized_similarity, aa, ab)
    out["artist_full_exact"] = (
        la["artist_norm_full"].fillna("").to_numpy() == lb["artist_norm_full"].fillna("").to_numpy()
    ).astype("int8")
    out["title_exact_norm"] = (np.asarray(ta) == np.asarray(tb)).astype("int8")
    ya = pd.to_numeric(la["year"], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    yb = pd.to_numeric(lb["year"], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    diff = np.abs(ya - yb)
    out["year_diff"] = (
        pd.array(np.where(np.isnan(diff), np.nan, diff), dtype="Int64")
        if len(diff)
        else pd.array([], dtype="Int64")
    )
    out["year_either_missing"] = (np.isnan(ya) | np.isnan(yb)).astype("int8")
    out["both_va"] = (
        la["is_various_artists"].to_numpy().astype(bool)
        & lb["is_various_artists"].to_numpy().astype(bool)
    ).astype("int8")
    out["title_len_diff"] = (
        np.abs(np.array([len(s) for s in ta]) - np.array([len(s) for s in tb])).astype("int32")
        if ta
        else pd.array([], dtype="int32")
    )
    out["n_block_keys"] = pairs["n_block_keys"].to_numpy().astype("int32")
    qa = la["title_qualifiers"].map(lambda v: frozenset(_tuple(v))).to_numpy()
    qb = lb["title_qualifiers"].map(lambda v: frozenset(_tuple(v))).to_numpy()
    out["qualifier_mismatch"] = (
        np.array([int(x != y) for x, y in zip(qa, qb, strict=True)], dtype="int8")
        if len(qa)
        else pd.array([], dtype="int8")
    )
    return out[list(PAIR_COLUMNS)]
