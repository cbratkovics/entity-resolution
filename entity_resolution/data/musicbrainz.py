"""Side A: MusicBrainz release groups from the core dump ``mbdump.tar.bz2`` (ADR 0001).

Ten core tables are stream-extracted (ADR 0002) and read positionally through DuckDB. Only
the columns in ``PROJECTIONS`` are materialised: ``release`` is projected to
``(id, release_group)`` and the release events to ``(release, date_year)``; no release name,
barcode or any other column is read into a table or written to a cache
(docs/DATA_SOURCES.md; ``tests/test_musicbrainz_adapter.py`` asserts it).

Loaded fields: ``release_group.name``, ``artist_credit.name``, the earliest ``date_year`` over
the group's release events (year 0 ignored), ``release_group_primary_type.name``; native id
``release_group.gid``. Truth links: ``l_release_group_url`` to ``url`` where the URL matches
``MASTER_URL_RE``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pandas as pd

from entity_resolution.config import CACHE_DIR, RAW_DIR
from entity_resolution.data import acquire
from entity_resolution.interfaces import Record, TruthLink

MASTER_URL_RE = re.compile(r"^https?://(www\.)?discogs\.com/master/(\d+)")

# Column names in file order, from the MusicBrainz schema (CreateTables.sql); the dump files
# carry no header, so the positions matter and nothing else about the columns is used.
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "release_group": (
        "id",
        "gid",
        "name",
        "artist_credit",
        "type",
        "comment",
        "edits_pending",
        "last_updated",
    ),
    "artist_credit": ("id", "name", "artist_count", "ref_count", "created", "edits_pending", "gid"),
    "release_group_primary_type": ("id", "name", "parent", "child_order", "description", "gid"),
    "l_release_group_url": (
        "id",
        "link",
        "entity0",
        "entity1",
        "edits_pending",
        "last_updated",
        "link_order",
        "entity0_credit",
        "entity1_credit",
    ),
    "url": ("id", "gid", "url", "edits_pending", "last_updated"),
    "link": (
        "id",
        "link_type",
        "begin_date_year",
        "begin_date_month",
        "begin_date_day",
        "end_date_year",
        "end_date_month",
        "end_date_day",
        "attribute_count",
        "created",
        "ended",
    ),
    "link_type": (
        "id",
        "parent",
        "child_order",
        "gid",
        "entity_type0",
        "entity_type1",
        "name",
        "description",
        "link_phrase",
        "reverse_link_phrase",
        "long_link_phrase",
        "last_updated",
        "is_deprecated",
        "has_dates",
        "entity0_cardinality",
        "entity1_cardinality",
    ),
    "release": (
        "id",
        "gid",
        "name",
        "artist_credit",
        "release_group",
        "status",
        "packaging",
        "language",
        "script",
        "barcode",
        "comment",
        "edits_pending",
        "quality",
        "last_updated",
    ),
    "release_country": ("release", "country", "date_year", "date_month", "date_day"),
    "release_unknown_country": ("release", "date_year", "date_month", "date_day"),
}
PROJECTIONS: dict[str, tuple[str, ...]] = {
    "release_group": ("id", "gid", "name", "artist_credit", "type"),
    "artist_credit": ("id", "name"),
    "release_group_primary_type": ("id", "name"),
    "l_release_group_url": ("link", "entity0", "entity1"),
    "url": ("id", "url"),
    "link": ("id", "link_type"),
    "link_type": ("id", "name"),
    "release": ("id", "release_group"),
    "release_country": ("release", "date_year"),
    "release_unknown_country": ("release", "date_year"),
}
TABLES: tuple[str, ...] = tuple(TABLE_COLUMNS)
FRAME_COLUMNS: tuple[str, ...] = (
    "source",
    "native_id",
    "title",
    "artist_credit",
    "year",
    "primary_type",
    "n_links",
)


def load_tables(con: duckdb.DuckDBPyConnection, mbdump_dir: Path) -> None:
    """Create one DuckDB table per dump file holding only its projection."""
    for table, columns in TABLE_COLUMNS.items():
        path = (mbdump_dir / table).as_posix()
        spec = ", ".join(f"'{c}': 'VARCHAR'" for c in columns)
        keep = ", ".join(PROJECTIONS[table])
        con.execute(
            f"create or replace table {table} as select {keep} from read_csv('{path}', "
            f"delim='\\t', header=false, quote='', escape='', null_padding=true, "
            f"nullstr='\\N', columns={{{spec}}})"
        )


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [r[0] for r in con.execute(f"describe {table}").fetchall()]


RELEASE_GROUP_SQL = """
with first_year as (
    select r.release_group as id, min(try_cast(e.date_year as integer)) as year
    from (
        select release, date_year from release_country
        union all
        select release, date_year from release_unknown_country
    ) e
    join release r on r.id = e.release
    where try_cast(e.date_year as integer) > 0
    group by r.release_group
),
links as (
    select l.entity0 as rg_id, count(*) as n
    from l_release_group_url l
    join url u on u.id = l.entity1
    where regexp_matches(u.url, '^https?://(www\\.)?discogs\\.com/master/[0-9]+')
    group by l.entity0
)
select
    'musicbrainz' as source,
    rg.gid as native_id,
    rg.name as title,
    coalesce(ac.name, '') as artist_credit,
    fy.year as year,
    coalesce(pt.name, 'none') as primary_type,
    coalesce(lk.n, 0) as n_links
from release_group rg
left join artist_credit ac on ac.id = rg.artist_credit
left join first_year fy on fy.id = rg.id
left join release_group_primary_type pt on pt.id = rg.type
left join links lk on lk.rg_id = rg.id
order by rg.gid
"""

TRUTH_SQL = """
select rg.gid as a_id, regexp_extract(u.url, 'discogs\\.com/master/([0-9]+)', 1) as b_id,
       coalesce(lt.name, '') as link_type_name
from l_release_group_url l
join release_group rg on rg.id = l.entity0
join url u on u.id = l.entity1
left join link lk on lk.id = l.link
left join link_type lt on lt.id = lk.link_type
where regexp_matches(u.url, '^https?://(www\\.)?discogs\\.com/master/[0-9]+')
order by rg.gid, b_id
"""


def row_to_record(row: dict) -> Record:
    return Record(
        source="musicbrainz",
        native_id=str(row["native_id"]),
        title=row["title"] or "",
        artist_credit=row["artist_credit"] or "",
        year=None if pd.isna(row["year"]) else int(row["year"]),
        extra={"primary_type": str(row["primary_type"])},
    )


class MusicBrainzAdapter:
    """``interfaces.SourceAdapter`` for MusicBrainz release groups."""

    NAME = "musicbrainz"
    SIDE = "A"
    LICENCE_URL = acquire.MUSICBRAINZ.licence_url
    SPEC = acquire.MUSICBRAINZ
    TABLES = TABLES

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        """``cache_dir`` holds the parquet caches; tests pass a temporary directory so they can
        never touch data/cache while a real run is in progress."""
        self.cache_dir = cache_dir

    def cache_path(self, data_dir: Path | None = None) -> Path:
        base = data_dir / "cache" if data_dir else self.cache_dir
        return base / "musicbrainz_release_groups.parquet"

    def truth_cache_path(self, data_dir: Path | None = None) -> Path:
        base = data_dir / "cache" if data_dir else self.cache_dir
        return base / "musicbrainz_truth_links.parquet"

    def mbdump_dir(self, raw_dir: Path = RAW_DIR) -> Path:
        return raw_dir / "mbdump"

    def extract(self, archive: Path, mbdump_dir: Path) -> dict:
        return acquire.extract_tables(archive, TABLES, mbdump_dir)

    def _connect(self, mbdump_dir: Path) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        load_tables(con, mbdump_dir)
        return con

    def load_frame(self, mbdump_dir: Path, cache: Path | None = None) -> pd.DataFrame:
        """Every release group as a frame (``FRAME_COLUMNS``), sorted by gid, cached as parquet."""
        cache = cache or self.cache_path()
        if cache.exists():
            return pd.read_parquet(cache)
        con = self._connect(mbdump_dir)
        df = con.execute(RELEASE_GROUP_SQL).df()
        con.close()
        df["native_id"] = df["native_id"].astype("string")
        df["year"] = df["year"].astype("Int64")
        df["n_links"] = df["n_links"].astype("int32")
        df = df[list(FRAME_COLUMNS)].reset_index(drop=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False, compression="zstd")
        return df

    def load_truth(self, mbdump_dir: Path, cache: Path | None = None) -> pd.DataFrame:
        """Every release-group-to-master link as ``(a_id, b_id, link_type_name)``, cached."""
        cache = cache or self.truth_cache_path()
        if cache.exists():
            return pd.read_parquet(cache)
        con = self._connect(mbdump_dir)
        df = con.execute(TRUTH_SQL).df()
        con.close()
        for c in df.columns:
            df[c] = df[c].astype("string")
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False, compression="zstd")
        return df

    def iter_records(self, dump_path: Path) -> Iterator[Record]:
        """``dump_path`` is the extracted mbdump directory."""
        for row in self.load_frame(dump_path).to_dict("records"):
            yield row_to_record(row)

    def truth_links(self, dump_path: Path) -> Iterator[TruthLink]:
        for a_id, b_id in self.load_truth(dump_path)[["a_id", "b_id"]].itertuples(index=False):
            yield TruthLink(str(a_id), str(b_id))
