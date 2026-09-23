"""The truth table and its audit (docs/BRIEF.md 2.2, ADR 0001).

Truth links live in their own frame and are never joined to the matcher's input. Each link is
classified once, in this precedence: ``truth_dead`` (the master is absent from the current
dump), ``truth_out_of_scope`` (the release group is not of the scope primary type),
``truth_unsampled`` (an in-scope alive link whose A or B record the hash sample excluded;
zero by construction, still counted), ``truth_in_sample``. The audit carries counts, rates and
hashed pair ids only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from entity_resolution.config import A_SCOPE_PRIMARY_TYPE

STATUSES: tuple[str, ...] = (
    "truth_dead",
    "truth_out_of_scope",
    "truth_unsampled",
    "truth_in_sample",
)
ANOMALY_SAMPLE_SIZE = 20


def pair_hash(a_id: str, b_id: str) -> str:
    return hashlib.sha256(f"{a_id}|{b_id}".encode()).hexdigest()


@dataclass(frozen=True)
class Truth:
    """Every link with its status; ``links`` columns: a_id, b_id, status, a_primary_type."""

    links: pd.DataFrame

    def in_sample(self) -> pd.DataFrame:
        return self.links[self.links["status"] == "truth_in_sample"]

    def labelled_a_ids(self) -> set[str]:
        return set(self.in_sample()["a_id"])

    def alive_in_scope(self) -> pd.DataFrame:
        return self.links[self.links["status"].isin(("truth_unsampled", "truth_in_sample"))]


def classify(
    links: pd.DataFrame,
    a_frame: pd.DataFrame,
    b_ids: set[str],
    *,
    scope_primary_type: str = A_SCOPE_PRIMARY_TYPE,
) -> Truth:
    """Classify links (``a_id``, ``b_id``) as dead or out of scope; the rest are provisionally
    ``truth_in_sample`` until :func:`apply_sample` sees the sampled ids."""
    df = links[["a_id", "b_id"]].astype("string").drop_duplicates().copy()
    types = a_frame.set_index("native_id")["primary_type"]
    df["a_primary_type"] = df["a_id"].map(types).astype("string")
    dead = ~df["b_id"].isin(b_ids)
    out_of_scope = ~dead & (df["a_primary_type"].fillna("none") != scope_primary_type)
    df["status"] = "truth_in_sample"
    df.loc[out_of_scope, "status"] = "truth_out_of_scope"
    df.loc[dead, "status"] = "truth_dead"
    df["status"] = df["status"].astype("string")
    return Truth(df.sort_values(["a_id", "b_id"]).reset_index(drop=True))


def apply_sample(truth: Truth, sampled_a: set[str], sampled_b: set[str]) -> Truth:
    df = truth.links.copy()
    alive = df["status"] == "truth_in_sample"
    unsampled = alive & ~(df["a_id"].isin(sampled_a) & df["b_id"].isin(sampled_b))
    df.loc[unsampled, "status"] = "truth_unsampled"
    return Truth(df)


def _hashed_sample(df: pd.DataFrame) -> list[str]:
    hashes = sorted(pair_hash(a, b) for a, b in df[["a_id", "b_id"]].itertuples(index=False))
    return hashes[:ANOMALY_SAMPLE_SIZE]


def audit(
    truth: Truth, raw_links: pd.DataFrame, *, scope_primary_type: str = A_SCOPE_PRIMARY_TYPE
) -> dict[str, Any]:
    """The truth audit block: link counts, the four statuses, one-to-many rates on each side,
    duplicate links, and up to twenty hashed pair ids per anomaly class."""
    df = truth.links
    n_raw = int(len(raw_links))
    n = int(len(df))
    counts = {s: int((df["status"] == s).sum()) for s in STATUSES}
    in_sample = truth.in_sample()
    per_a = in_sample.groupby("a_id")["b_id"].nunique()
    per_b = in_sample.groupby("b_id")["a_id"].nunique()
    many_a = set(per_a[per_a > 1].index)
    many_b = set(per_b[per_b > 1].index)
    duplicates = raw_links[["a_id", "b_id"]].astype("string")
    dup_mask = duplicates.duplicated(keep="first")
    by_type = {
        str(k): int(v)
        for k, v in df[df["status"] == "truth_out_of_scope"]["a_primary_type"]
        .fillna("none")
        .value_counts()
        .items()
    }
    return {
        "links_raw": n_raw,
        "links_distinct": n,
        "duplicate_links": int(dup_mask.sum()),
        "scope_primary_type": scope_primary_type,
        **counts,
        "truth_dead_rate": round(counts["truth_dead"] / n, 6) if n else None,
        "truth_out_of_scope_by_primary_type": by_type,
        "in_sample": {
            "pairs": int(len(in_sample)),
            "a_records": int(per_a.size),
            "b_records": int(per_b.size),
            "one_to_many_a": len(many_a),
            "one_to_many_a_rate": round(len(many_a) / per_a.size, 6) if per_a.size else None,
            "one_to_many_b": len(many_b),
            "one_to_many_b_rate": round(len(many_b) / per_b.size, 6) if per_b.size else None,
        },
        "anomaly_samples": {
            "truth_dead": _hashed_sample(df[df["status"] == "truth_dead"]),
            "truth_out_of_scope": _hashed_sample(df[df["status"] == "truth_out_of_scope"]),
            "truth_unsampled": _hashed_sample(df[df["status"] == "truth_unsampled"]),
            "one_to_many_a": _hashed_sample(in_sample[in_sample["a_id"].isin(many_a)]),
            "one_to_many_b": _hashed_sample(in_sample[in_sample["b_id"].isin(many_b)]),
            "duplicate_links": _hashed_sample(duplicates[dup_mask]),
        },
    }
