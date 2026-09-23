"""Blocking keys and candidate pairs (docs/BRIEF.md 2.4).

Five independent keys, emitted from the normalised columns of a record; the candidate set is
the union of every block, and every pair records which keys produced it. Various-artists
records get title keys only. A per-A candidate cap keeps the 200 candidates with the most keys
(ties by B id) and counts what it dropped: overflow is a number in ``blocking_report.json``,
never a silent truncation. Pair generation and aggregation run in DuckDB so a million records a
side stay tractable; the key functions are pure Python and unit-tested.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd

KEY_TYPES: tuple[str, ...] = (
    "k_title3",
    "k_artist_year",
    "k_title_sorted",
    "k_phonetic",
    "k_self_titled",
)
TITLE_KEYS: frozenset[str] = frozenset({"k_title3", "k_title_sorted"})
"""Keys that do not involve the artist credit; the only keys a various-artists record emits."""
CANDIDATE_CAP = 200


def _hash16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def keys_for(
    *,
    title_norm: str,
    title_tokens: Iterable[str],
    artist_norm: str,
    year: int | None,
    is_various_artists: bool,
    is_self_titled: bool,
    title_metaphone: str,
    artist_metaphone: str,
) -> list[tuple[str, str]]:
    """``(key_type, key)`` pairs for one record. Pure."""
    out: list[tuple[str, str]] = []
    words = title_norm.split()
    if words:
        out.append(("k_title3", " ".join(words[:3])))
        out.append(("k_title_sorted", _hash16(" ".join(sorted(set(title_tokens))))))
    if is_various_artists or not artist_norm:
        return out
    if year is not None:
        for y in (year - 1, year, year + 1):
            out.append(("k_artist_year", f"{artist_norm}|{y}"))
    if title_metaphone and artist_metaphone:
        out.append(("k_phonetic", f"{title_metaphone}|{artist_metaphone}"))
    if is_self_titled:
        out.append(("k_self_titled", artist_norm))
    return out


def key_frame(records: pd.DataFrame) -> pd.DataFrame:
    """One row per (native_id, key_type, key) over a normalised frame."""
    rows: list[tuple[str, str, str]] = []
    cols = [
        "native_id",
        "title_norm",
        "title_tokens",
        "artist_norm",
        "year",
        "is_various_artists",
        "is_self_titled",
        "title_metaphone",
        "artist_metaphone",
    ]
    for nid, title_norm, title_tokens, artist_norm, year, va, self_titled, tm, am in records[
        cols
    ].itertuples(index=False):
        y = None if pd.isna(year) else int(year)
        for kt, k in keys_for(
            title_norm=title_norm or "",
            title_tokens=list(title_tokens) if title_tokens is not None else [],
            artist_norm=artist_norm or "",
            year=y,
            is_various_artists=bool(va),
            is_self_titled=bool(self_titled),
            title_metaphone=tm or "",
            artist_metaphone=am or "",
        ):
            rows.append((str(nid), kt, k))
    return pd.DataFrame(rows, columns=["native_id", "key_type", "key"]).astype("string")


def build_candidates(
    a: pd.DataFrame,
    b: pd.DataFrame,
    truth_pairs: pd.DataFrame | None = None,
    *,
    cap: int = CANDIDATE_CAP,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Candidate pairs from the union of blocks, capped per A record, and the blocking report.
    ``truth_pairs`` (``a_id``, ``b_id``) gives pair completeness per key and for the union, before
    and after the cap; it is used for counting only and never enters the candidate table."""
    con = con or duckdb.connect()
    a_keys = key_frame(a)
    b_keys = key_frame(b)
    con.register("a_keys", a_keys)
    con.register("b_keys", b_keys)
    con.execute(
        """
        create or replace table pair_keys as
        select a.native_id as a_id, b.native_id as b_id, a.key_type
        from a_keys a join b_keys b on a.key_type = b.key_type and a.key = b.key
        group by 1, 2, 3
        """
    )
    con.execute(
        """
        create or replace table union_pairs as
        select a_id, b_id, list_sort(list(key_type)) as block_keys, count(*) as n_block_keys
        from pair_keys group by 1, 2
        """
    )
    n_union = con.execute("select count(*) from union_pairs").fetchone()[0]
    per_key_pairs = dict(
        con.execute("select key_type, count(*) from pair_keys group by 1").fetchall()
    )
    largest = {
        kt: [
            int(n)
            for (n,) in con.execute(
                "select cnt from (select key, count(*) as cnt from a_keys where key_type = ? group by key) order by cnt desc limit 5",
                [kt],
            ).fetchall()
        ]
        for kt in KEY_TYPES
    }
    per_a = con.execute(
        "select count(*) as n_a, max(n) as max_candidates, sum(case when n > ? then n - ? else 0 end) as dropped, "
        "sum(case when n > ? then 1 else 0 end) as a_over_cap from (select a_id, count(*) as n from union_pairs group by a_id)",
        [cap, cap, cap],
    ).fetchone()
    con.execute(
        f"""
        create or replace table candidates as
        select a_id, b_id, block_keys, n_block_keys
        from (select *, row_number() over (partition by a_id order by n_block_keys desc, b_id) as rn from union_pairs)
        where rn <= {int(cap)}
        """
    )
    n_capped = con.execute("select count(*) from candidates").fetchone()[0]
    report: dict[str, Any] = {
        "keys": list(KEY_TYPES),
        "candidate_cap_per_a": cap,
        "a_records": int(len(a)),
        "b_records": int(len(b)),
        "cross_product": int(len(a)) * int(len(b)),
        "union_pairs": int(n_union),
        "candidate_pairs_after_cap": int(n_capped),
        "reduction_ratio": round(1 - n_capped / (len(a) * len(b)), 9)
        if len(a) and len(b)
        else None,
        "per_key_pairs": {kt: int(per_key_pairs.get(kt, 0)) for kt in KEY_TYPES},
        "keys_emitted": {
            "a": {
                kt: int(v)
                for kt, v in con.execute(
                    "select key_type, count(*) from a_keys group by 1"
                ).fetchall()
            },
            "b": {
                kt: int(v)
                for kt, v in con.execute(
                    "select key_type, count(*) from b_keys group by 1"
                ).fetchall()
            },
        },
        "largest_blocks_a": largest,
        "cap_overflow": {
            "a_records_over_cap": int(per_a[3] or 0),
            "pairs_dropped": int(per_a[2] or 0),
            "max_candidates_per_a": int(per_a[1] or 0),
            "a_records_with_candidates": int(per_a[0] or 0),
        },
    }
    if truth_pairs is not None:
        con.register("truth_pairs", truth_pairs[["a_id", "b_id"]].astype("string"))
        n_truth = con.execute("select count(*) from truth_pairs").fetchone()[0]
        per_key = dict(
            con.execute(
                "select p.key_type, count(distinct (t.a_id, t.b_id)) from truth_pairs t join pair_keys p on p.a_id = t.a_id and p.b_id = t.b_id group by 1"
            ).fetchall()
        )
        in_union = con.execute(
            "select count(*) from truth_pairs t join union_pairs u on u.a_id = t.a_id and u.b_id = t.b_id"
        ).fetchone()[0]
        in_capped = con.execute(
            "select count(*) from truth_pairs t join candidates c on c.a_id = t.a_id and c.b_id = t.b_id"
        ).fetchone()[0]
        report["pair_completeness"] = {
            "truth_pairs": int(n_truth),
            "per_key": {
                kt: (round(per_key.get(kt, 0) / n_truth, 6) if n_truth else None)
                for kt in KEY_TYPES
            },
            "union": round(in_union / n_truth, 6) if n_truth else None,
            "after_cap": round(in_capped / n_truth, 6) if n_truth else None,
            "truth_pairs_lost_to_cap": int(in_union - in_capped),
        }
    candidates = con.execute(
        "select a_id, b_id, block_keys, n_block_keys from candidates order by a_id, b_id"
    ).df()
    candidates["a_id"] = candidates["a_id"].astype("string")
    candidates["b_id"] = candidates["b_id"].astype("string")
    candidates["n_block_keys"] = candidates["n_block_keys"].astype("int32")
    return candidates, report
