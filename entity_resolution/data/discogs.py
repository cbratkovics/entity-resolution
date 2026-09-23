"""Side B: Discogs masters (``discogs_YYYYMMDD_masters.xml.gz``), streamed with iterparse and
cached as parquet under data/cache/. Loaded fields (docs/DATA_SOURCES.md): title, the artist
credit as printed, year, the count of genres, main_release; native id master_id.

Quirks handled here and nowhere else: ``<year>0</year>`` means unknown; every artist carries a
``<join>`` element, including the last one, so a join is appended only when another artist
follows.
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from entity_resolution.config import CACHE_DIR
from entity_resolution.data import acquire
from entity_resolution.interfaces import Record, TruthLink

FRAME_COLUMNS: tuple[str, ...] = (
    "source",
    "native_id",
    "title",
    "artist_credit",
    "year",
    "n_artists",
    "n_genres",
    "main_release",
)


def master_from_element(elem: ET.Element) -> dict[str, Any]:
    """One master element to a row; pure, so the parser is testable on inline XML."""
    artists = elem.findall("./artists/artist")
    parts: list[str] = []
    for i, a in enumerate(artists):
        parts.append(a.findtext("name") or "")
        if i < len(artists) - 1:
            parts.append(a.findtext("join") or "")
    year_text = (elem.findtext("year") or "").strip()
    year = int(year_text) if year_text.isdigit() and int(year_text) > 0 else None
    main_release = (elem.findtext("main_release") or "").strip()
    return {
        "source": DiscogsAdapter.NAME,
        "native_id": str(elem.get("id")),
        "title": elem.findtext("title") or "",
        "artist_credit": "".join(parts).strip(),
        "year": year,
        "n_artists": len(artists),
        "n_genres": len(elem.findall("./genres/genre")),
        "main_release": int(main_release) if main_release.isdigit() else None,
    }


def iter_master_rows(stream: Any) -> Iterator[dict[str, Any]]:
    """Stream ``<master>`` elements from an open XML byte stream, clearing each after use."""
    for _event, elem in ET.iterparse(stream, events=("end",)):
        if elem.tag != "master":
            continue
        yield master_from_element(elem)
        elem.clear()


def row_to_record(row: dict[str, Any]) -> Record:
    return Record(
        source=row["source"],
        native_id=str(row["native_id"]),
        title=row["title"],
        artist_credit=row["artist_credit"],
        year=None if pd.isna(row["year"]) else int(row["year"]),
    )


class DiscogsAdapter:
    """``interfaces.SourceAdapter`` for Discogs masters."""

    NAME = "discogs"
    SIDE = "B"
    LICENCE_URL = acquire.DISCOGS.licence_url
    SPEC = acquire.DISCOGS

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir

    def cache_path(self, data_dir: Path | None = None) -> Path:
        base = data_dir / "cache" if data_dir else self.cache_dir
        return base / "discogs_masters.parquet"

    def iter_records(self, dump_path: Path) -> Iterator[Record]:
        with gzip.open(dump_path, "rb") as fh:
            for row in iter_master_rows(fh):
                yield row_to_record(row)

    def truth_links(self, dump_path: Path) -> Iterator[TruthLink]:
        yield from ()

    def load_frame(self, dump_path: Path, cache: Path | None = None) -> pd.DataFrame:
        """All masters as a frame (``FRAME_COLUMNS``), sorted by native_id, cached as parquet."""
        cache = cache or self.cache_path()
        if cache.exists():
            return pd.read_parquet(cache)
        with gzip.open(dump_path, "rb") as fh:
            df = pd.DataFrame(list(iter_master_rows(fh)), columns=list(FRAME_COLUMNS))
        df = _typed(df)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False, compression="zstd")
        return df


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    df["native_id"] = df["native_id"].astype("string")
    df["year"] = df["year"].astype("Int64")
    df["main_release"] = df["main_release"].astype("Int64")
    df["n_artists"] = df["n_artists"].astype("int32")
    df["n_genres"] = df["n_genres"].astype("int32")
    return df.sort_values("native_id", key=lambda s: s.astype("int64")).reset_index(drop=True)
