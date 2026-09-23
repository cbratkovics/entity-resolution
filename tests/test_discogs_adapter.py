"""The Discogs parser on inline XML: join handling, year 0, ids as strings, record shape."""

from __future__ import annotations

import io

from entity_resolution.data import discogs
from entity_resolution.interfaces import Record, SourceAdapter

XML = b"""<masters>
<master id="10"><main_release>5</main_release><artists><artist><id>1</id><name>Solo Person</name><join>,</join></artist></artists><genres><genre>Rock</genre></genres><year>0</year><title>First</title></master>
<master id="11"><main_release>6</main_release><artists><artist><id>1</id><name>One</name><join> &amp; </join></artist><artist><id>2</id><name>Two</name><join>,</join></artist></artists><year>1999</year><title>Second</title></master>
<master id="12"><artists><artist><id>3</id><name>Various</name><join></join></artist></artists><genres><genre>Pop</genre><genre>Jazz</genre></genres><year>2001</year><title>Third</title></master>
</masters>"""


def test_rows_from_inline_xml() -> None:
    rows = list(discogs.iter_master_rows(io.BytesIO(XML)))
    assert [r["native_id"] for r in rows] == ["10", "11", "12"]
    assert rows[0]["artist_credit"] == "Solo Person"  # trailing join dropped
    assert rows[0]["year"] is None  # year 0 means unknown
    assert rows[1]["artist_credit"] == "One & Two"  # join kept between artists
    assert rows[1]["year"] == 1999 and rows[1]["main_release"] == 6
    assert rows[2]["n_genres"] == 2 and rows[2]["main_release"] is None
    assert set(rows[0]) == set(discogs.FRAME_COLUMNS)


def test_adapter_satisfies_protocol_and_records(tmp_path) -> None:
    import gzip

    dump = tmp_path / "discogs_test_masters.xml.gz"
    with gzip.open(dump, "wb") as fh:
        fh.write(XML)
    adapter = discogs.DiscogsAdapter(cache_dir=tmp_path / "cache")
    assert isinstance(adapter, SourceAdapter) and adapter.SIDE == "B"
    records = list(adapter.iter_records(dump))
    assert all(isinstance(r, Record) and r.source == "discogs" for r in records)
    assert list(adapter.truth_links(dump)) == []
    frame = adapter.load_frame(dump, tmp_path / "cache.parquet")
    assert list(frame.columns) == list(discogs.FRAME_COLUMNS)
    assert list(frame["native_id"]) == ["10", "11", "12"]
    again = adapter.load_frame(dump, tmp_path / "cache.parquet")
    assert again.equals(frame)
