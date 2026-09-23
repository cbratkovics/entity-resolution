"""The deterministic sample (docs/BRIEF.md 2.2, ADR 0001).

Membership of an unlinked record is decided by ``sha256(source || "|" || native_id)`` compared,
as a 64-character hex string, with a per-side threshold. The threshold is *solved*: it is the
hash of the n-th smallest record in the unlinked pool, where n makes the unlinked count equal
the linked count (unlinked share 0.50), so a reader with the pool can recompute it exactly. The
manifest records the threshold, the fraction it corresponds to and the pool sizes.

Side A pool: release groups of the scope primary type with no link at all (release groups whose
only links are dead are excluded: they are linked, to a master that is gone). Side B pool:
every master not in an alive in-scope link; masters linked only from out-of-scope release
groups are in the pool and carry ``b_linked_out_of_scope``.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from entity_resolution.config import UNLINKED_SHARE
from entity_resolution.features import normalize

HEX_MAX = 2**256


def membership_hash(source: str, native_id: str) -> str:
    return hashlib.sha256(f"{source}|{native_id}".encode()).hexdigest()


def hash_column(source: str, ids: pd.Series) -> pd.Series:
    return pd.Series(
        [membership_hash(source, str(i)) for i in ids], index=ids.index, dtype="string"
    )


def solve_threshold(pool_hashes: pd.Series, n_select: int) -> dict[str, Any]:
    """The largest hash admitted when the ``n_select`` smallest hashes of the pool are taken;
    ``"00"*32`` when nothing is selected. Ties are impossible for distinct ids."""
    pool = pool_hashes.sort_values().reset_index(drop=True)
    n_select = max(0, min(int(n_select), len(pool)))
    threshold = str(pool.iloc[n_select - 1]) if n_select else "0" * 64
    return {
        "threshold_hex": threshold,
        "threshold_fraction": int(threshold, 16) / HEX_MAX,
        "pool_size": int(len(pool)),
        "selected": n_select,
    }


def select(pool_hashes: pd.Series, threshold_hex: str) -> pd.Series:
    """Boolean membership: hash <= threshold (as hex strings of equal length)."""
    return pool_hashes <= threshold_hex


def n_unlinked_for(n_linked: int, unlinked_share: float = UNLINKED_SHARE) -> int:
    """Unlinked records so that unlinked / (linked + unlinked) == unlinked_share."""
    if not 0 <= unlinked_share < 1:
        raise ValueError("unlinked_share must be in [0, 1)")
    return int(round(n_linked * unlinked_share / (1 - unlinked_share)))


def build_side(
    frame: pd.DataFrame,
    *,
    source: str,
    linked_ids: set[str],
    pool_mask: pd.Series,
    unlinked_share: float = UNLINKED_SHARE,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Every linked record plus hash-selected records from ``pool_mask``. Returns the sampled
    frame (with ``membership_hash`` and ``is_linked``) and the threshold record."""
    hashes = hash_column(source, frame["native_id"])
    linked = frame["native_id"].isin(linked_ids)
    pool = pool_mask & ~linked
    n_linked = int(linked.sum())
    solved = solve_threshold(hashes[pool], n_unlinked_for(n_linked, unlinked_share))
    chosen = pool & select(hashes, solved["threshold_hex"])
    out = frame[linked | chosen].copy()
    out["membership_hash"] = hashes[linked | chosen]
    out["is_linked"] = linked[linked | chosen].astype(bool)
    out = out.sort_values("native_id").reset_index(drop=True)
    record = {
        **solved,
        "linked": n_linked,
        "unlinked_share_target": unlinked_share,
        "sampled": int(len(out)),
        "unlinked_share_actual": round(solved["selected"] / len(out), 6) if len(out) else None,
    }
    return out, record


def normalize_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Add the normalised columns through the one normaliser, fixed column order."""
    out = normalize.normalize_frame(df)
    ordered = [c for c in df.columns] + list(normalize.NORMALIZED_COLUMNS)
    return out[ordered]


def content_sha256(df: pd.DataFrame) -> str:
    """Hash of the frame's content independent of row order and file encoding: rows sorted by
    every column, list columns joined, values hashed with pandas' stable row hasher."""
    import numpy as np

    def is_seq(v: object) -> bool:
        return isinstance(v, list | tuple | np.ndarray)

    flat = df.copy()
    for c in flat.columns:
        if flat[c].dtype == object and flat[c].map(is_seq).any():
            flat[c] = flat[c].map(lambda v: "\x1f".join(map(str, v)) if is_seq(v) else v)
    flat = flat.astype("string").fillna("\x00")
    flat = flat.sort_values(list(flat.columns), kind="mergesort").reset_index(drop=True)
    row_hashes = pd.util.hash_pandas_object(flat, index=False).to_numpy()
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()
