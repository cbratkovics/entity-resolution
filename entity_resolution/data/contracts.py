"""Data contracts as pure functions returning reports (docs/BRIEF.md Phase 2).

Each check takes a ``pandas.DataFrame`` and returns a :class:`Check`; :func:`run_contracts`
bundles them into a report ``{"ok", "checks", "summary"}`` with only counts and rates inside, so
the report can be committed without carrying a single row. The real adapters call these in
Phase 2; ``tests/test_contracts.py`` proves they detect injected violations.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

YEAR_MIN = 1900
ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "discogs": re.compile(r"^\d+$"),
    "musicbrainz": re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    "wikidata": re.compile(r"^Q\d+$"),
    "fixture": re.compile(r"^\d+$"),
}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


def year_max(today: dt.date | None = None) -> int:
    return (today or dt.date.today()).year + 1


def grain_unique(df: pd.DataFrame, keys: Iterable[str]) -> Check:
    keys = list(keys)
    dup = int(df.duplicated(keys).sum()) if len(df) else 0
    return Check("grain_unique", dup == 0, {"keys": keys, "duplicate_rows": dup, "rows": len(df)})


def id_format(df: pd.DataFrame, source: str, column: str = "native_id") -> Check:
    pattern = ID_PATTERNS[source]
    ids = df[column].astype("string")
    bad = int((~ids.fillna("").str.fullmatch(pattern.pattern)).sum())
    return Check(
        "id_format", bad == 0, {"source": source, "pattern": pattern.pattern, "bad_ids": bad}
    )


def year_range(df: pd.DataFrame, column: str = "year", *, today: dt.date | None = None) -> Check:
    hi = year_max(today)
    years = pd.to_numeric(df[column], errors="coerce")
    present = years.dropna()
    out_of_range = int(((present < YEAR_MIN) | (present > hi)).sum())
    return Check(
        "year_range",
        out_of_range == 0,
        {
            "min": YEAR_MIN,
            "max": hi,
            "out_of_range": out_of_range,
            "missing": int(years.isna().sum()),
        },
    )


def null_rates(df: pd.DataFrame, max_rates: Mapping[str, float]) -> Check:
    rates = {
        c: (float(df[c].isna().mean()) if len(df) else 0.0) for c in max_rates if c in df.columns
    }
    missing_cols = [c for c in max_rates if c not in df.columns]
    over = {c: r for c, r in rates.items() if r > max_rates[c]}
    return Check(
        "null_rates",
        not over and not missing_cols,
        {
            "rates": rates,
            "max_rates": dict(max_rates),
            "over": over,
            "missing_columns": missing_cols,
        },
    )


def run_contracts(
    df: pd.DataFrame,
    *,
    source: str,
    keys: Iterable[str] = ("source", "native_id"),
    max_null_rates: Mapping[str, float] | None = None,
    today: dt.date | None = None,
) -> dict[str, Any]:
    max_null_rates = dict(max_null_rates or {"title": 0.0, "artist_credit": 0.0, "year": 1.0})
    checks = [
        grain_unique(df, keys),
        id_format(df, source),
        year_range(df, today=today),
        null_rates(df, max_null_rates),
    ]
    return {
        "ok": all(c.ok for c in checks),
        "checks": [asdict(c) for c in checks],
        "summary": {"source": source, "rows": int(len(df)), "n_checks": len(checks)},
    }
