"""The MusicBrainz loader on inline TSV fixtures: the ten-table list of ADR 0002, the
projections (release is (id, release_group) only), the derived first-release year, the
master-URL truth links and the record shape."""

from __future__ import annotations

from pathlib import Path

import duckdb

from entity_resolution.data import musicbrainz as mb
from entity_resolution.interfaces import Record, SourceAdapter, TruthLink

A_GID = "11111111-1111-4111-8111-111111111111"
B_GID = "22222222-2222-4222-8222-222222222222"
FIXTURE = {
    "release_group": [
        ["1", A_GID, "Album One", "10", "1", "", "0", "2020-01-01 00:00:00+00"],
        ["2", B_GID, "Single Two", "11", "2", "", "0", "2020-01-01 00:00:00+00"],
    ],
    "artist_credit": [
        ["10", "Artist A", "1", "1", "2020-01-01", "0", "aaaaaaaa-0000-4000-8000-000000000001"],
        ["11", "Artist B", "1", "1", "2020-01-01", "0", "aaaaaaaa-0000-4000-8000-000000000002"],
    ],
    "release_group_primary_type": [
        ["1", "Album", "\\N", "1", "\\N", "bbbbbbbb-0000-4000-8000-000000000001"],
        ["2", "Single", "\\N", "2", "\\N", "bbbbbbbb-0000-4000-8000-000000000002"],
    ],
    "l_release_group_url": [
        ["100", "500", "1", "900", "0", "2020-01-01 00:00:00+00", "0", "", ""],
        ["101", "500", "2", "901", "0", "2020-01-01 00:00:00+00", "0", "", ""],
        ["102", "500", "1", "902", "0", "2020-01-01 00:00:00+00", "0", "", ""],
    ],
    "url": [
        [
            "900",
            "cccccccc-0000-4000-8000-000000000001",
            "https://www.discogs.com/master/12345",
            "0",
            "2020-01-01 00:00:00+00",
        ],
        [
            "901",
            "cccccccc-0000-4000-8000-000000000002",
            "http://discogs.com/master/777",
            "0",
            "2020-01-01 00:00:00+00",
        ],
        [
            "902",
            "cccccccc-0000-4000-8000-000000000003",
            "https://www.discogs.com/release/999",
            "0",
            "2020-01-01 00:00:00+00",
        ],
    ],
    "link": [
        ["500", "600", "\\N", "\\N", "\\N", "\\N", "\\N", "\\N", "0", "2020-01-01 00:00:00+00", "f"]
    ],
    "link_type": [
        [
            "600",
            "\\N",
            "0",
            "dddddddd-0000-4000-8000-000000000001",
            "release_group",
            "url",
            "discogs",
            "",
            "d",
            "d",
            "d",
            "2020-01-01 00:00:00+00",
            "f",
            "f",
            "0",
            "0",
        ]
    ],
    "release": [
        [
            "1000",
            "eeeeeeee-0000-4000-8000-000000000001",
            "Secret Release Name",
            "10",
            "1",
            "1",
            "\\N",
            "120",
            "28",
            "SECRETBARCODE",
            "",
            "0",
            "-1",
            "2020-01-01 00:00:00+00",
        ],
        [
            "1001",
            "eeeeeeee-0000-4000-8000-000000000002",
            "Secret Release Name Two",
            "10",
            "1",
            "1",
            "\\N",
            "120",
            "28",
            "\\N",
            "",
            "0",
            "-1",
            "2020-01-01 00:00:00+00",
        ],
    ],
    "release_country": [["1000", "81", "1997", "1", "24"], ["1001", "81", "1995", "\\N", "\\N"]],
    "release_unknown_country": [["1001", "0", "\\N", "\\N"]],
}


def write_fixture(mbdump_dir: Path) -> None:
    mbdump_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in FIXTURE.items():
        assert all(len(r) == len(mb.TABLE_COLUMNS[table]) for r in rows), table
        (mbdump_dir / table).write_text("\n".join("\t".join(r) for r in rows) + "\n")


def test_table_list_matches_adr_0002() -> None:
    assert set(mb.TABLES) == {
        "release_group",
        "artist_credit",
        "release_group_primary_type",
        "l_release_group_url",
        "url",
        "link",
        "link_type",
        "release",
        "release_country",
        "release_unknown_country",
    }
    assert "release_group_meta" not in mb.TABLES


def test_projections_never_read_release_names_or_barcodes(tmp_path) -> None:
    assert mb.PROJECTIONS["release"] == ("id", "release_group")
    assert mb.PROJECTIONS["release_country"] == ("release", "date_year")
    assert mb.PROJECTIONS["release_unknown_country"] == ("release", "date_year")
    for table, keep in mb.PROJECTIONS.items():
        assert set(keep) <= set(mb.TABLE_COLUMNS[table])
    write_fixture(tmp_path / "mbdump")
    con = duckdb.connect()
    mb.load_tables(con, tmp_path / "mbdump")
    for table, keep in mb.PROJECTIONS.items():
        assert mb.table_columns(con, table) == list(keep), table
    assert "name" not in mb.table_columns(con, "release")
    assert "barcode" not in mb.table_columns(con, "release")


def test_frame_truth_and_records(tmp_path) -> None:
    write_fixture(tmp_path / "mbdump")
    adapter = mb.MusicBrainzAdapter(cache_dir=tmp_path / "cache")
    assert isinstance(adapter, SourceAdapter) and adapter.SIDE == "A"
    frame = adapter.load_frame(tmp_path / "mbdump", tmp_path / "rg.parquet")
    assert list(frame.columns) == list(mb.FRAME_COLUMNS)
    by_id = frame.set_index("native_id")
    assert by_id.loc[A_GID, "title"] == "Album One"
    assert by_id.loc[A_GID, "artist_credit"] == "Artist A"
    assert by_id.loc[A_GID, "year"] == 1995  # earliest dated event; year 0 ignored
    assert by_id.loc[A_GID, "primary_type"] == "Album"
    assert by_id.loc[A_GID, "n_links"] == 1  # the release URL is not a master link
    assert by_id.loc[B_GID, "year"] is None or str(by_id.loc[B_GID, "year"]) == "<NA>"
    truth = adapter.load_truth(tmp_path / "mbdump", tmp_path / "truth.parquet")
    assert sorted(zip(truth["a_id"], truth["b_id"], strict=True)) == [
        (A_GID, "12345"),
        (B_GID, "777"),
    ]
    assert set(truth["link_type_name"]) == {"discogs"}
    # the cache must not carry release names either
    import pyarrow.parquet as pq

    for p in (tmp_path / "rg.parquet", tmp_path / "truth.parquet"):
        text = pq.read_table(p).to_pandas().to_string()
        assert "Secret Release" not in text and "SECRETBARCODE" not in text
    links = list(adapter.truth_links(tmp_path / "mbdump"))
    assert all(isinstance(t, TruthLink) for t in links)
    records = list(adapter.iter_records(tmp_path / "mbdump"))
    assert all(isinstance(r, Record) and r.source == "musicbrainz" for r in records)
    assert {r.extra["primary_type"] for r in records} == {"Album", "Single"}
