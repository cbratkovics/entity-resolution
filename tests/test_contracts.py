"""Every contract passes on clean rows and detects an injected violation."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from entity_resolution.data import contracts

TODAY = dt.date(2026, 9, 22)


def _clean() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["discogs"] * 3,
            "native_id": ["1", "2", "3"],
            "title": ["a", "b", "c"],
            "artist_credit": ["x", "y", "z"],
            "year": [1991, None, 2026],
        }
    )


def test_clean_rows_pass_every_check() -> None:
    report = contracts.run_contracts(_clean(), source="discogs", today=TODAY)
    assert report["ok"] and report["summary"]["rows"] == 3
    assert [c["name"] for c in report["checks"]] == [
        "grain_unique",
        "id_format",
        "year_range",
        "null_rates",
    ]


def test_duplicate_grain_is_detected() -> None:
    df = pd.concat([_clean(), _clean().iloc[[0]]])
    c = contracts.grain_unique(df, ["source", "native_id"])
    assert not c.ok and c.detail["duplicate_rows"] == 1


@pytest.mark.parametrize(
    ("source", "bad"),
    [("discogs", "12a"), ("musicbrainz", "not-a-uuid"), ("wikidata", "12345")],
)
def test_id_format_is_detected_per_source(source: str, bad: str) -> None:
    df = _clean()
    df.loc[0, "native_id"] = bad
    c = contracts.id_format(df, source)
    assert not c.ok and c.detail["bad_ids"] >= 1


def test_year_range_is_1900_to_next_year() -> None:
    df = _clean()
    assert contracts.year_range(df, today=TODAY).ok
    df.loc[0, "year"] = 1899
    df.loc[2, "year"] = 2028
    c = contracts.year_range(df, today=TODAY)
    assert not c.ok and c.detail["out_of_range"] == 2 and c.detail["max"] == 2027


def test_null_rates_detect_missing_titles_and_columns() -> None:
    df = _clean()
    df.loc[1, "title"] = None
    c = contracts.null_rates(df, {"title": 0.0, "year": 1.0})
    assert not c.ok and "title" in c.detail["over"]
    c = contracts.null_rates(df.drop(columns=["year"]), {"year": 1.0})
    assert not c.ok and c.detail["missing_columns"] == ["year"]


def test_report_carries_counts_only() -> None:
    report = contracts.run_contracts(_clean(), source="discogs", today=TODAY)
    text = str(report)
    for attribute in ("a", "x"):
        assert f"'{attribute}'" not in text  # no title or artist value leaks into the report
