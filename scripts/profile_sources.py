#!/usr/bin/env python
"""Phase 1: acquire and profile both side-A candidates and the Discogs masters (docs/BRIEF.md
section 3, Phase 1). Writes aggregates only to artifacts/profile/<source>.json and renders
docs/PROFILE.md. Every intermediate row stays under data/ (git-ignored).

    python scripts/profile_sources.py download --source discogs|musicbrainz
    python scripts/profile_sources.py extract          # stream the listed tables out of mbdump.tar.bz2
    python scripts/profile_sources.py discogs          # stream-profile the masters dump
    python scripts/profile_sources.py musicbrainz      # profile release groups and Discogs links
    python scripts/profile_sources.py wikidata         # paged SPARQL over P1954, counted locally
    python scripts/profile_sources.py render           # docs/PROFILE.md from the artifacts

Free disk is checked and printed before any download. The MusicBrainz archive is never unpacked
whole: the eight listed tables are streamed out of the tar and nothing else touches disk.
Names are normalised by entity_resolution.features.normalize only (rule 5); the artifacts carry
counts, rates, hashes and enumerated pattern codes, never a title or an artist credit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run without installing

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

import duckdb
import jsonschema
import pandas as pd

from entity_resolution.config import ARTIFACTS_DIR, DATA_DIR, REPO_ROOT, SCHEMAS_DIR
from entity_resolution.data import acquire
from entity_resolution.data import musicbrainz as mb
from entity_resolution.features import FEATURE_VERSION
from entity_resolution.features import normalize as norm
from entity_resolution.models.registry import code_commit

USER_AGENT = acquire.USER_AGENT
RAW_DIR = acquire.RAW_DIR
PROFILE_CACHE = DATA_DIR / "profile"
PROFILE_DIR = ARTIFACTS_DIR / "profile"
PROFILE_VERSION = "1.0"

DISCOGS_DUMP = acquire.DISCOGS.filename
DISCOGS_LICENCE_URL = acquire.DISCOGS.licence_url
MB_DUMP = acquire.MUSICBRAINZ.filename
MB_LICENCE_URL = acquire.MUSICBRAINZ.licence_url
MB_TABLES = mb.TABLES
SOURCES = {"discogs": acquire.DISCOGS, "musicbrainz": acquire.MUSICBRAINZ}
WD_ENDPOINT = "https://query.wikidata.org/sparql"
WD_LICENCE_URL = "https://www.wikidata.org/wiki/Wikidata:Licensing"
WD_PAGE_SIZE = 2000
WD_MIN_PAGE_SIZE = 250
WD_BACKOFF_SECONDS = (5, 10, 20, 40, 80)
SOURCES = {"discogs": acquire.DISCOGS, "musicbrainz": acquire.MUSICBRAINZ}
_request = acquire.request
DISCOGS_MASTER_URL_RE = re.compile(r"^https?://(www\.)?discogs\.com/master/(\d+)")
N_EXAMPLES = 15
YEAR_MIN, YEAR_MAX = 1900, dt.date.today().year + 1

# Name-convention patterns between a truth-linked A record and its Discogs master. The artifact
# stores the code; the description is rendered from this table, so no example carries a string
# from either source.
PATTERNS: dict[str, str] = {
    "identical": "normalised title, artist and year all equal",
    "year_only": "normalised title and artist equal; the year differs or is missing on one side",
    "case_punct_diacritics": "raw strings differ only in case, punctuation or diacritics (equal after basic normalisation)",
    "ampersand_vs_and": "one side writes '&' where the other writes 'and'",
    "article_position": "the artist article is trailing on one side ('X, The') and leading on the other",
    "numeric_disambiguator": "the Discogs artist credit carries a numeric disambiguator such as '(2)'",
    "edition_qualifier": "one side carries a bracketed edition qualifier (remaster, deluxe, ...) that the other omits",
    "title_token_order": "same title tokens in a different order",
    "title_token_subset": "one title's tokens are a strict subset of the other's (subtitle or extra words)",
    "artist_credit_join": "one artist credit's tokens are a strict subset of the other's (joined credit vs single artist)",
    "various_artists_credit": "one side credits Various Artists and the other names artists",
    "self_titled_vs_named": "one side's title equals its artist (self-titled) and the other's does not",
    "other": "title or artist differ in a way none of the listed patterns explains",
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def gib(n: int) -> float:
    return round(n / 2**30, 2)


def write_json(obj: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rate(n: int, d: int) -> float | None:
    return round(n / d, 6) if d else None


# ----------------------------------------------------------------------------- acquisition


def download(source: str) -> Path:
    spec = SOURCES[source]
    acquire.download(spec, RAW_DIR)
    return RAW_DIR / spec.filename


def extract_musicbrainz() -> Path:
    out_dir = RAW_DIR / "mbdump"
    acquire.extract_tables(RAW_DIR / MB_DUMP, MB_TABLES, out_dir)
    return out_dir


# ----------------------------------------------------------------------------- shared profile


def normalized_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add the normalised columns (rule 5: through entity_resolution.features.normalize only)."""
    cols: dict[str, list[Any]] = {
        k: []
        for k in (
            "title_norm",
            "title_norm_full",
            "n_qualifiers",
            "artist_norm",
            "artist_norm_full",
            "is_va",
            "is_self_titled",
            "year_norm",
        )
    }
    for title, credit, year in zip(df["title"], df["artist_credit"], df["year"], strict=True):
        y = None if pd.isna(year) else int(year)
        r = norm.normalize_record(title or "", credit or "", y)
        cols["title_norm"].append(r.title_norm)
        cols["title_norm_full"].append(r.title_norm_full)
        cols["n_qualifiers"].append(len(r.title_qualifiers))
        cols["artist_norm"].append(r.artist_norm)
        cols["artist_norm_full"].append(r.artist_norm_full)
        cols["is_va"].append(r.is_various_artists)
        cols["is_self_titled"].append(r.is_self_titled)
        cols["year_norm"].append(r.year)
    out = df.copy()
    for k, v in cols.items():
        out[k] = v
    out["year_norm"] = out["year_norm"].astype("Int64")
    return out


def record_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregates over a normalised frame: completeness, years, VA share, duplicate rate."""
    n = int(len(df))
    years = df["year_norm"]
    present = years.dropna()
    in_range = present[(present >= YEAR_MIN) & (present <= YEAR_MAX)]
    decades = Counter((int(y) // 10) * 10 for y in in_range)
    key = df["title_norm"] + "\u0000" + df["artist_norm"]
    sizes = key.value_counts()
    dup_keys = int((sizes > 1).sum())
    dup_records = int(sizes[sizes > 1].sum())
    empty_title = int((df["title_norm"] == "").sum())
    empty_artist = int((df["artist_norm"] == "").sum())
    return {
        "total": n,
        "completeness": {
            "title": rate(n - empty_title, n),
            "artist_credit": rate(n - empty_artist, n),
            "year": rate(int(present.size), n),
        },
        "year": {
            "missing": int(n - present.size),
            "out_of_range": int(present.size - in_range.size),
            "min_in_range": int(in_range.min()) if in_range.size else None,
            "max_in_range": int(in_range.max()) if in_range.size else None,
            "by_decade": {str(k): int(v) for k, v in sorted(decades.items())},
        },
        "various_artists_share": rate(int(df["is_va"].sum()), n),
        "self_titled_share": rate(int(df["is_self_titled"].sum()), n),
        "qualifier_share": rate(int((df["n_qualifiers"] > 0).sum()), n),
        "duplicate_key": {
            "keys": int(sizes.size),
            "keys_with_duplicates": dup_keys,
            "records_in_duplicate_keys": dup_records,
            "record_rate": rate(dup_records, n),
            "largest_key_size": int(sizes.max()) if sizes.size else 0,
        },
    }


def classify_pair(a: pd.Series, b: pd.Series) -> str:
    """The name-convention pattern between a linked A record and its master (see PATTERNS)."""
    same_title = a["title_norm"] == b["title_norm"]
    same_artist = a["artist_norm"] == b["artist_norm"]
    same_year = (
        pd.notna(a["year_norm"]) and pd.notna(b["year_norm"]) and a["year_norm"] == b["year_norm"]
    )
    if same_title and same_artist:
        if same_year:
            return "identical"
        if a["title_norm_full"] != b["title_norm_full"] or a["n_qualifiers"] != b["n_qualifiers"]:
            return "edition_qualifier"
        if a["artist_norm_full"] != b["artist_norm_full"]:
            return "article_position"
        if "(" in str(b["artist_credit"]) and norm.strip_disambiguator(
            str(b["artist_credit"])
        ) != str(b["artist_credit"]):
            return "numeric_disambiguator"
        return "year_only"
    if bool(a["is_va"]) != bool(b["is_va"]):
        return "various_artists_credit"
    if a["title_norm_full"] == b["title_norm_full"] and same_artist:
        return "edition_qualifier"
    if (
        same_title
        and a["artist_norm_full"] != b["artist_norm_full"]
        and a["artist_norm"] == b["artist_norm"]
    ):
        return "article_position"
    ra, rb = (
        str(a["title"]) + "|" + str(a["artist_credit"]),
        str(b["title"]) + "|" + str(b["artist_credit"]),
    )
    if ra.replace("&", "and").casefold() == rb.replace("&", "and").casefold() and ra != rb:
        return "ampersand_vs_and"
    if norm.basic(ra) == norm.basic(rb):
        return "case_punct_diacritics"
    if bool(a["is_self_titled"]) != bool(b["is_self_titled"]):
        return "self_titled_vs_named"
    ta, tb = set(a["title_norm"].split()), set(b["title_norm"].split())
    aa, ab = set(a["artist_norm"].split()), set(b["artist_norm"].split())
    if same_artist and ta == tb:
        return "title_token_order"
    if same_artist and (ta < tb or tb < ta):
        return "title_token_subset"
    if same_title and (aa < ab or ab < aa):
        return "artist_credit_join"
    return "other"


def truth_profile(
    a: pd.DataFrame, links: pd.DataFrame, masters: pd.DataFrame, id_col: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Truth link quality against the current masters dump, pattern counts over every alive
    pair, and N_EXAMPLES hashed examples chosen deterministically (lowest pair hash per pattern,
    round robin). ``links`` has columns (a_id, master_id)."""
    links = links.drop_duplicates()
    master_ids = set(masters["master_id"].astype("int64"))
    alive = links[links["master_id"].isin(master_ids)]
    dead = int(len(links) - len(alive))
    per_a = links.groupby("a_id")["master_id"].nunique()
    per_b = links.groupby("master_id")["a_id"].nunique()
    a_idx = a.set_index(id_col)
    m_idx = masters.set_index("master_id")
    joined = alive.merge(a_idx, left_on="a_id", right_index=True).merge(
        m_idx, left_on="master_id", right_index=True, suffixes=("_a", "_b")
    )
    pattern_counts: Counter[str] = Counter()
    candidates: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for _, row in joined.iterrows():
        ra = pd.Series({k[:-2]: v for k, v in row.items() if k.endswith("_a")})
        rb = pd.Series({k[:-2]: v for k, v in row.items() if k.endswith("_b")})
        code = classify_pair(ra, rb)
        pattern_counts[code] += 1
        if code == "identical":
            continue
        pair_hash = sha256_text(f"{row['a_id']}|{row['master_id']}")
        example = {
            "pattern": code,
            "pair_hash": pair_hash,
            "a_title_hash": sha256_text(ra["title_norm"]),
            "b_title_hash": sha256_text(rb["title_norm"]),
            "a_artist_hash": sha256_text(ra["artist_norm"]),
            "b_artist_hash": sha256_text(rb["artist_norm"]),
            "year_a": None if pd.isna(ra["year_norm"]) else int(ra["year_norm"]),
            "year_b": None if pd.isna(rb["year_norm"]) else int(rb["year_norm"]),
        }
        bucket = candidates.setdefault(code, [])
        if len(bucket) < 50:
            bucket.append((pair_hash, example))
        elif pair_hash < max(bucket)[0]:
            bucket.remove(max(bucket))
            bucket.append((pair_hash, example))
    examples: list[dict[str, Any]] = []
    ordered = sorted(candidates, key=lambda c: (-pattern_counts[c], c))
    buckets = {c: sorted(candidates[c]) for c in ordered}
    while len(examples) < N_EXAMPLES and any(buckets.values()):
        for c in ordered:
            if buckets[c] and len(examples) < N_EXAMPLES:
                examples.append(buckets[c].pop(0)[1])
    return (
        {
            "links": int(len(links)),
            "a_records_with_link": int(per_a.size),
            "distinct_masters": int(per_b.size),
            "dead": dead,
            "dead_rate": rate(dead, int(len(links))),
            "alive": int(len(alive)),
            "one_to_many_a": int((per_a > 1).sum()),
            "one_to_many_a_rate": rate(int((per_a > 1).sum()), int(per_a.size)),
            "one_to_many_b": int((per_b > 1).sum()),
            "one_to_many_b_rate": rate(int((per_b > 1).sum()), int(per_b.size)),
            "alive_with_artist_and_year": int(
                ((joined["artist_norm_a"] != "") & joined["year_norm_a"].notna()).sum()
            ),
            "pattern_counts": {k: int(pattern_counts[k]) for k in PATTERNS if pattern_counts[k]},
        },
        examples,
    )


def base_artifact(source: str, side: str) -> dict[str, Any]:
    return {
        "profile_version": PROFILE_VERSION,
        "source": source,
        "side": side,
        "generated_at_utc": utc_now(),
        "feature_version": FEATURE_VERSION,
        "code_commit": code_commit(),
    }


def write_profile(artifact: dict[str, Any]) -> Path:
    schema = json.loads((SCHEMAS_DIR / "profile.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(artifact, schema)
    path = PROFILE_DIR / f"{artifact['source']}.json"
    write_json(artifact, path)
    print(f"wrote {path}")
    return path


# ----------------------------------------------------------------------------- discogs


def stream_discogs_masters(path: Path) -> pd.DataFrame:
    """Stream the masters dump with iterparse; one row per master, never the whole tree."""
    cache = PROFILE_CACHE / "discogs_masters.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rb") as fh:
        for _event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "master":
                continue
            # the credit as printed: name, then the join text only when another artist follows
            # (Discogs emits a trailing join such as "," on the last artist too)
            artists = elem.findall("./artists/artist")
            parts: list[str] = []
            for i, a in enumerate(artists):
                parts.append(a.findtext("name") or "")
                if i < len(artists) - 1:
                    parts.append(a.findtext("join") or "")
            credit = "".join(parts).strip()
            year_text = elem.findtext("year")
            rows.append(
                {
                    "master_id": int(elem.get("id")),
                    "title": elem.findtext("title") or "",
                    "artist_credit": credit,
                    # Discogs writes 0 for an unknown year
                    "year": int(year_text)
                    if year_text and year_text.isdigit() and int(year_text) > 0
                    else None,
                    "n_genres": len(elem.findall("./genres/genre")),
                    "main_release": int(elem.findtext("main_release") or 0) or None,
                    "n_artists": len(elem.findall("./artists/artist")),
                }
            )
            elem.clear()
    df = pd.DataFrame(rows)
    df["year"] = df["year"].astype("Int64")
    df["main_release"] = df["main_release"].astype("Int64")
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def masters_normalized() -> pd.DataFrame:
    cache = PROFILE_CACHE / "discogs_masters_norm.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    df = normalized_frame(stream_discogs_masters(RAW_DIR / DISCOGS_DUMP))
    df.to_parquet(cache, index=False)
    return df


def profile_discogs() -> dict[str, Any]:
    t0 = time.monotonic()
    meta = read_json(RAW_DIR / (DISCOGS_DUMP + ".meta.json"))
    df = masters_normalized()
    has_disamb = df["artist_credit"].map(lambda s: norm.strip_disambiguator(str(s)) != str(s))
    art = base_artifact("discogs", "B")
    art["acquisition"] = {
        "kind": "dump",
        "filename": meta["filename"],
        "url": meta["url"],
        "licence_url": DISCOGS_LICENCE_URL,
        "dump_date": meta["dump_date"],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "download_seconds": meta["download_seconds"],
        "free_disk_before_bytes": meta["free_disk_before_bytes"],
        "profile_seconds": None,
    }
    art["records"] = record_profile(df)
    art["records"]["numeric_disambiguator_share"] = rate(int(has_disamb.sum()), len(df))
    art["records"]["main_release_present"] = rate(int(df["main_release"].notna().sum()), len(df))
    art["records"]["genres_present"] = rate(int((df["n_genres"] > 0).sum()), len(df))
    art["records"]["multi_artist_credit_share"] = rate(int((df["n_artists"] > 1).sum()), len(df))
    art["acquisition"]["profile_seconds"] = round(time.monotonic() - t0, 1)
    write_profile(art)
    return art


# ----------------------------------------------------------------------------- musicbrainz


def _mb_table(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> None:
    path = (RAW_DIR / "mbdump" / table).as_posix()
    cols = ", ".join(f"'{c}': 'VARCHAR'" for c in columns)
    con.execute(
        f"create or replace table {table} as select * from read_csv('{path}', delim='\\t', "
        f"header=false, quote='', escape='', null_padding=true, nullstr='\\N', "
        f"columns={{{cols}}})"
    )


def load_musicbrainz(con: duckdb.DuckDBPyConnection) -> None:
    """The listed tables, with the column names from the MusicBrainz schema (CreateTables.sql);
    only the columns the profile needs are typed."""
    _mb_table(
        con,
        "release_group",
        ["id", "gid", "name", "artist_credit", "type", "comment", "edits_pending", "last_updated"],
    )
    _mb_table(
        con,
        "release",
        [
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
        ],
    )
    _mb_table(con, "release_country", ["release", "country", "date_year", "date_month", "date_day"])
    _mb_table(con, "release_unknown_country", ["release", "date_year", "date_month", "date_day"])
    # first release year per release group from the core release dates (ADR 0002): the earliest
    # dated release event of any release in the group
    con.execute(
        """
        create or replace table release_group_first_year as
        select r.release_group as id, min(try_cast(e.date_year as integer)) as first_release_date_year
        from (
            select release, date_year from release_country
            union all
            select release, date_year from release_unknown_country
        ) e
        join release r on r.id = e.release
        where try_cast(e.date_year as integer) > 0
        group by r.release_group
        """
    )
    _mb_table(
        con,
        "artist_credit",
        ["id", "name", "artist_count", "ref_count", "created", "edits_pending", "gid"],
    )
    _mb_table(
        con,
        "release_group_primary_type",
        ["id", "name", "parent", "child_order", "description", "gid"],
    )
    _mb_table(
        con,
        "l_release_group_url",
        [
            "id",
            "link",
            "entity0",
            "entity1",
            "edits_pending",
            "last_updated",
            "link_order",
            "entity0_credit",
            "entity1_credit",
        ],
    )
    _mb_table(con, "url", ["id", "gid", "url", "edits_pending", "last_updated"])
    _mb_table(
        con,
        "link",
        [
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
        ],
    )
    _mb_table(
        con,
        "link_type",
        [
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
        ],
    )


def profile_musicbrainz() -> dict[str, Any]:
    t0 = time.monotonic()
    meta = read_json(RAW_DIR / (MB_DUMP + ".meta.json"))
    extract = read_json(RAW_DIR / "mbdump" / "_extract.meta.json")
    con = duckdb.connect()
    load_musicbrainz(con)
    rg = con.execute(
        """
        select rg.gid as gid, rg.name as title, ac.name as artist_credit,
               try_cast(m.first_release_date_year as integer) as year,
               coalesce(pt.name, 'none') as primary_type
        from release_group rg
        left join artist_credit ac on ac.id = rg.artist_credit
        left join release_group_first_year m on m.id = rg.id
        left join release_group_primary_type pt on pt.id = rg.type
        """
    ).df()
    links = con.execute(
        """
        select rg.gid as a_id, u.url as url, lt.name as link_type_name
        from l_release_group_url l
        join release_group rg on rg.id = l.entity0
        join url u on u.id = l.entity1
        left join link lk on lk.id = l.link
        left join link_type lt on lt.id = lk.link_type
        where u.url like '%discogs.com/%'
        """
    ).df()
    by_type = con.execute(
        "select coalesce(pt.name, 'none') as t, count(*) as n from release_group rg "
        "left join release_group_primary_type pt on pt.id = rg.type group by 1 order by 2 desc"
    ).fetchall()
    rg["year"] = rg["year"].astype("Int64")
    rgn = normalized_frame(rg)
    rgn.to_parquet(PROFILE_CACHE / "musicbrainz_release_groups_norm.parquet", index=False)
    master_links = links[links["url"].str.match(DISCOGS_MASTER_URL_RE)].copy()
    master_links["master_id"] = (
        master_links["url"].str.extract(DISCOGS_MASTER_URL_RE.pattern)[1].astype("int64")
    )
    link_type_counts = Counter(master_links["link_type_name"].fillna("none"))
    masters = masters_normalized()
    truth, examples = truth_profile(rgn, master_links[["a_id", "master_id"]], masters, id_col="gid")
    truth["discogs_urls_total"] = int(len(links))
    truth["discogs_master_urls"] = int(len(master_links))
    truth["discogs_non_master_urls"] = int(len(links) - len(master_links))
    truth["link_type_counts"] = {str(k): int(v) for k, v in link_type_counts.items()}
    # linked A records per primary type: what a type-restricted sample scope would keep
    linked_types = rgn[rgn["gid"].isin(set(master_links["a_id"]))]["primary_type"]
    truth["a_records_with_link_by_primary_type"] = {
        str(k): int(v) for k, v in Counter(linked_types).items()
    }
    art = base_artifact("musicbrainz", "A")
    art["acquisition"] = {
        "kind": "dump",
        "filename": meta["filename"],
        "url": meta["url"],
        "licence_url": MB_LICENCE_URL,
        "dump_date": meta["dump_date"],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "download_seconds": meta["download_seconds"],
        "free_disk_before_bytes": meta["free_disk_before_bytes"],
        "extract_seconds": extract["extract_seconds"],
        "extract_passes": extract["extract_passes"],
        "extracted_bytes": extract["extracted_bytes"],
        "tables": {t: v["bytes"] for t, v in extract["tables"].items()},
        "profile_seconds": None,
    }
    art["records"] = record_profile(rgn)
    art["records"]["by_primary_type"] = {str(t): int(n) for t, n in by_type}
    album_mask = rgn["primary_type"] == "Album"
    art["records"]["albums"] = int(album_mask.sum())
    art["truth"] = truth
    art["examples"] = examples
    art["acquisition"]["profile_seconds"] = round(time.monotonic() - t0, 1)
    write_profile(art)
    return art


# ----------------------------------------------------------------------------- wikidata


class WikidataClient:
    """Paged SPARQL with a User-Agent, backoff, page-size halving on repeated failure and a
    per-page cache under data/profile/wikidata/. Counts requests, retries, timeouts, seconds
    and hashes every response body in order."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests = 0
        self.retries = 0
        self.timeouts = 0
        self.seconds = 0.0
        self.hasher = hashlib.sha256()
        self.cached_pages = 0

    def query(self, name: str, sparql: str) -> list[dict[str, Any]]:
        cache = self.cache_dir / f"{name}.json"
        if cache.exists():
            body = cache.read_bytes()
            self.cached_pages += 1
            self.hasher.update(body)
            return json.loads(body)["results"]["bindings"]
        data = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
        for attempt, wait in enumerate((0, *WD_BACKOFF_SECONDS)):
            if wait:
                time.sleep(wait)
                self.retries += 1
            t0 = time.monotonic()
            self.requests += 1
            try:
                req = _request(WD_ENDPOINT, "POST", data)
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                req.add_header("Accept", "application/sparql-results+json")
                with urllib.request.urlopen(req, timeout=120) as r:
                    body = r.read()
                self.seconds += time.monotonic() - t0
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                self.seconds += time.monotonic() - t0
                code = getattr(e, "code", None)
                if code in (429, 500, 502, 503, 504) or code is None:
                    self.timeouts += 1
                    print(
                        f"  wikidata {name}: attempt {attempt + 1} failed ({code or e}); backing off"
                    )
                    continue
                raise
        else:
            raise RuntimeError(
                f"wikidata {name}: gave up after {len(WD_BACKOFF_SECONDS) + 1} attempts"
            )
        cache.write_bytes(body)
        self.hasher.update(body)
        return json.loads(body)["results"]["bindings"]


def profile_wikidata() -> dict[str, Any]:
    t0 = time.monotonic()
    started = utc_now()
    client = WikidataClient(PROFILE_CACHE / "wikidata")
    # 1. every (item, discogs master id) pair, paged by QID order
    ids: list[tuple[str, str]] = []
    page_size = WD_PAGE_SIZE
    offset = 0
    page = 0
    while True:
        rows = client.query(
            f"ids_{offset:07d}_{page_size}",
            f"SELECT ?item ?discogs WHERE {{ ?item wdt:P1954 ?discogs }} "
            f"ORDER BY ?item LIMIT {page_size} OFFSET {offset}",
        )
        ids += [(r["item"]["value"].rsplit("/", 1)[1], r["discogs"]["value"]) for r in rows]
        page += 1
        if len(rows) < page_size:
            break
        offset += page_size
    server_count = client.query(
        "count", "SELECT (COUNT(*) AS ?n) WHERE { ?item wdt:P1954 ?discogs }"
    )
    server_n = int(server_count[0]["n"]["value"]) if server_count else None
    # 2. label, performer, year and class per item: four flat queries per batch of items
    # (a grouped query, or one with an OPTIONAL label on the VALUES block, crashes Blazegraph
    # with a StackOverflowError or times out); aggregation is done locally
    items = sorted({q for q, _ in ids})
    labels: dict[str, str] = {}
    performers: dict[str, set[str]] = {}
    years: dict[str, int] = {}
    classes: dict[str, str] = {}
    batch = 1000

    def qid(r: dict[str, Any]) -> str:
        return r["item"]["value"].rsplit("/", 1)[1]

    for i in range(0, len(items), batch):
        values = " ".join(f"wd:{q}" for q in items[i : i + batch])
        for r in client.query(
            f"labels_{i:07d}",
            f"SELECT ?item ?label WHERE {{ VALUES ?item {{ {values} }} "
            '?item rdfs:label ?label FILTER(LANG(?label) = "en") }',
        ):
            labels.setdefault(qid(r), r["label"]["value"])
        for r in client.query(
            f"performers_{i:07d}",
            f"SELECT ?item ?perf WHERE {{ VALUES ?item {{ {values} }} "
            '?item wdt:P175 ?p . ?p rdfs:label ?perf FILTER(LANG(?perf) = "en") }',
        ):
            performers.setdefault(qid(r), set()).add(r["perf"]["value"])
        for r in client.query(
            f"dates_{i:07d}",
            f"SELECT ?item ?date WHERE {{ VALUES ?item {{ {values} }} ?item wdt:P577 ?date }}",
        ):
            d = r["date"]["value"]
            if d[:4].isdigit() and int(d[:4]) > 0:
                q = qid(r)
                years[q] = min(years.get(q, 9999), int(d[:4]))
        for r in client.query(
            f"types_{i:07d}",
            f"SELECT ?item ?type WHERE {{ VALUES ?item {{ {values} }} ?item wdt:P31 ?type }}",
        ):
            q = qid(r)
            c = r["type"]["value"].rsplit("/", 1)[-1]
            classes[q] = min(classes.get(q, c), c)
    details = {
        q: {
            "title": labels.get(q, ""),
            "artist_credit": " & ".join(sorted(performers.get(q, ()))),
            "year": years.get(q),
            "p31": classes.get(q, "none"),
            "label_en": q in labels,
        }
        for q in items
    }
    a = pd.DataFrame([{"qid": q, **details[q]} for q in items])
    a["year"] = a["year"].astype("Int64")
    an = normalized_frame(a)
    an.to_parquet(PROFILE_CACHE / "wikidata_items_norm.parquet", index=False)
    links = pd.DataFrame(ids, columns=["a_id", "discogs"])
    numeric = links["discogs"].str.fullmatch(r"\d+")
    master_links = links[numeric].copy()
    master_links["master_id"] = master_links["discogs"].astype("int64")
    masters = masters_normalized()
    truth, examples = truth_profile(an, master_links[["a_id", "master_id"]], masters, id_col="qid")
    truth["non_numeric_ids"] = int((~numeric).sum())
    by_class = Counter(a["p31"])
    art = base_artifact("wikidata", "A")
    art["acquisition"] = {
        "kind": "endpoint",
        "url": WD_ENDPOINT,
        "licence_url": WD_LICENCE_URL,
        "queried_at_utc": started,
        "requests": client.requests,
        "retries": client.retries,
        "timeouts": client.timeouts,
        "request_seconds": round(client.seconds, 1),
        "cached_pages": client.cached_pages,
        "page_size": page_size,
        "id_pages": page,
        "response_sha256": client.hasher.hexdigest(),
        "server_count": server_n,
        "profile_seconds": None,
    }
    art["records"] = record_profile(an)
    art["records"]["with_english_label"] = rate(int(a["label_en"].sum()), len(a))
    art["records"]["with_performer_and_year"] = int(
        ((an["artist_norm"] != "") & an["year_norm"].notna()).sum()
    )
    art["records"]["by_class_top"] = {str(k): int(v) for k, v in by_class.most_common(10)}
    art["truth"] = truth
    art["examples"] = examples
    art["acquisition"]["profile_seconds"] = round(time.monotonic() - t0, 1)
    write_profile(art)
    return art


# ----------------------------------------------------------------------------- render


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _n(x: int | None) -> str:
    return "n/a" if x is None else f"{x:,}"


def _minutes(s: float | None) -> str:
    return "n/a" if s is None else f"{s / 60:.1f} min"


def render_profile(profiles: dict[str, dict[str, Any]]) -> str:
    d, mb, wd = profiles.get("discogs"), profiles.get("musicbrainz"), profiles.get("wikidata")
    lines = [
        "# Source profile (Phase 1)",
        "",
        "<!-- generated:profile start -->",
        "_Rendered by `scripts/profile_sources.py render` from `artifacts/profile/*.json`; do not edit_",
        "_the generated block by hand. Every figure below is the artifact value; the key is the column._",
        "",
        "## Side by side",
        "",
        "| measure | Discogs masters (B) | MusicBrainz release groups (A #1) | Wikidata P1954 items (A #3) | key |",
        "|---|---|---|---|---|",
    ]

    def row(label: str, key: str, f, path: str) -> None:
        def get(p):
            if p is None:
                return None
            cur: Any = p
            for part in path.split("."):
                if cur is None or part not in cur:
                    return None
                cur = cur[part]
            return cur

        lines.append(f"| {label} | {f(get(d))} | {f(get(mb))} | {f(get(wd))} | `{key}` |")

    row("records", "records.total", _n, "records.total")
    row("title completeness", "records.completeness.title", _pct, "records.completeness.title")
    row(
        "artist credit completeness",
        "records.completeness.artist_credit",
        _pct,
        "records.completeness.artist_credit",
    )
    row("year completeness", "records.completeness.year", _pct, "records.completeness.year")
    row(
        "year out of [1900, next year]",
        "records.year.out_of_range",
        _n,
        "records.year.out_of_range",
    )
    row(
        "various-artists share",
        "records.various_artists_share",
        _pct,
        "records.various_artists_share",
    )
    row("self-titled share", "records.self_titled_share", _pct, "records.self_titled_share")
    row(
        "bracketed edition qualifier share",
        "records.qualifier_share",
        _pct,
        "records.qualifier_share",
    )
    row(
        "records sharing a (title_norm, artist_norm) key",
        "records.duplicate_key.record_rate",
        _pct,
        "records.duplicate_key.record_rate",
    )
    row(
        "largest duplicate key",
        "records.duplicate_key.largest_key_size",
        _n,
        "records.duplicate_key.largest_key_size",
    )
    row(
        "numeric artist disambiguator share",
        "records.numeric_disambiguator_share",
        _pct,
        "records.numeric_disambiguator_share",
    )
    row(
        "acquisition bytes",
        "acquisition.bytes",
        lambda x: "n/a" if x is None else f"{gib(x)} GiB",
        "acquisition.bytes",
    )
    row("download time", "acquisition.download_seconds", _minutes, "acquisition.download_seconds")
    row("extract time", "acquisition.extract_seconds", _minutes, "acquisition.extract_seconds")
    row(
        "extracted bytes",
        "acquisition.extracted_bytes",
        lambda x: "n/a" if x is None else f"{gib(x)} GiB",
        "acquisition.extracted_bytes",
    )
    row("endpoint requests", "acquisition.requests", _n, "acquisition.requests")
    row(
        "endpoint request time",
        "acquisition.request_seconds",
        _minutes,
        "acquisition.request_seconds",
    )
    row("endpoint retries / failures", "acquisition.timeouts", _n, "acquisition.timeouts")
    row("profile time", "acquisition.profile_seconds", _minutes, "acquisition.profile_seconds")
    row("truth links to Discogs masters", "truth.links", _n, "truth.links")
    row("truth links alive in the current dump", "truth.alive", _n, "truth.alive")
    row("truth dead-id rate", "truth.dead_rate", _pct, "truth.dead_rate")
    row(
        "A records with more than one master",
        "truth.one_to_many_a_rate",
        _pct,
        "truth.one_to_many_a_rate",
    )
    row(
        "masters linked from more than one A record",
        "truth.one_to_many_b_rate",
        _pct,
        "truth.one_to_many_b_rate",
    )
    row(
        "alive links with artist and year on A",
        "truth.alive_with_artist_and_year",
        _n,
        "truth.alive_with_artist_and_year",
    )
    lines.append("")
    lines.append("## Year distribution by decade")
    lines.append("")
    decades = sorted({k for p in (d, mb, wd) if p for k in p["records"]["year"]["by_decade"]})
    lines.append("| decade | Discogs | MusicBrainz | Wikidata |")
    lines.append("|---|---|---|---|")
    for dec in decades:
        vals = [_n(p["records"]["year"]["by_decade"].get(dec)) if p else "n/a" for p in (d, mb, wd)]
        lines.append(f"| {dec}s | " + " | ".join(vals) + " |")
    lines.append("")
    if mb:
        lines.append("## MusicBrainz release groups by primary type")
        lines.append("")
        lines.append("| primary type | release groups |")
        lines.append("|---|---|")
        for t, n in sorted(mb["records"]["by_primary_type"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {t} | {_n(n)} |")
        lines.append("")
        lines.append(
            "Discogs link types on release groups (`truth.link_type_counts`): "
            + ", ".join(f"{k} {_n(v)}" for k, v in mb["truth"]["link_type_counts"].items())
            + f". Discogs URLs that are not master URLs (release or artist pages): {_n(mb['truth']['discogs_non_master_urls'])} (`truth.discogs_non_master_urls`)."
        )
        lines.append("")
    if wd:
        lines.append("## Wikidata items by class (top 10, `records.by_class_top`)")
        lines.append("")
        lines.append("| P31 class | items |")
        lines.append("|---|---|")
        for k, v in wd["records"]["by_class_top"].items():
            lines.append(f"| {k} | {_n(v)} |")
        lines.append("")
        lines.append(
            f"Server-side COUNT of P1954 items: {_n(wd['acquisition']['server_count'])} (`acquisition.server_count`); "
            f"items paged locally: {_n(wd['records']['total'])} (`records.total`); "
            f"items with an English label: {_pct(wd['records']['with_english_label'])} (`records.with_english_label`); "
            f"P1954 values that are not numeric: {_n(wd['truth']['non_numeric_ids'])} (`truth.non_numeric_ids`)."
        )
        lines.append("")
    for name, p in (("MusicBrainz", mb), ("Wikidata", wd)):
        if not p:
            continue
        lines.append(
            f"## Name-convention patterns over alive truth pairs: {name} (`truth.pattern_counts`)"
        )
        lines.append("")
        lines.append("| pattern | pairs | share of alive | description |")
        lines.append("|---|---|---|---|")
        alive = p["truth"]["alive"]
        for code, n in sorted(p["truth"]["pattern_counts"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{code}` | {_n(n)} | {_pct(rate(n, alive))} | {PATTERNS[code]} |")
        lines.append("")
        lines.append(
            f"### {N_EXAMPLES} examples (`examples[i]`): hashes of the normalised strings, never the strings"
        )
        lines.append("")
        lines.append(
            "| # | pattern | A title sha256 (12) | B title sha256 (12) | A artist sha256 (12) | B artist sha256 (12) | year A | year B | description |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for i, ex in enumerate(p["examples"]):
            lines.append(
                f"| {i} | `{ex['pattern']}` | `{ex['a_title_hash'][:12]}` | `{ex['b_title_hash'][:12]}` | "
                f"`{ex['a_artist_hash'][:12]}` | `{ex['b_artist_hash'][:12]}` | {ex['year_a'] if ex['year_a'] is not None else 'missing'} | "
                f"{ex['year_b'] if ex['year_b'] is not None else 'missing'} | {PATTERNS[ex['pattern']]} |"
            )
        lines.append("")
    lines.append("<!-- generated:profile end -->")
    lines.append("")
    return "\n".join(lines)


def render(*, check: bool = False) -> Path:
    """Rewrite the generated block of docs/PROFILE.md, keeping the hand-written tail; with
    ``check`` only compare and exit non-zero when the block is stale."""
    profiles = {
        p.stem: read_json(p) for p in sorted(PROFILE_DIR.glob("*.json")) if p.stem != "schema"
    }
    out = REPO_ROOT / "docs" / "PROFILE.md"
    generated = render_profile(profiles)
    existing = out.read_text(encoding="utf-8") if out.exists() else ""
    marker = "<!-- generated:profile end -->"
    if check:
        current = existing.split(marker, 1)[0] + marker + "\n" if marker in existing else ""
        if current != generated:
            raise SystemExit(
                f"{out}: generated block is stale; run scripts/profile_sources.py render"
            )
        print(f"ok: {out} generated block matches the profile artifacts")
        return out
    tail = (
        existing.split(marker, 1)[1]
        if marker in existing
        else "\n## Recommendation\n\n_(written by hand after the profile; every number cited)_\n"
    )
    out.write_text(generated + tail.lstrip("\n") if tail.strip() else generated, encoding="utf-8")
    print(f"wrote {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="stage", required=True)
    d = sub.add_parser("download")
    d.add_argument("--source", choices=sorted(SOURCES), required=True)
    for name in ("extract", "discogs", "musicbrainz", "wikidata"):
        sub.add_parser(name)
    r = sub.add_parser("render")
    r.add_argument("--check", action="store_true", help="fail when docs/PROFILE.md is stale")
    a = p.parse_args(argv)
    PROFILE_CACHE.mkdir(parents=True, exist_ok=True)
    if a.stage == "download":
        download(a.source)
    elif a.stage == "extract":
        extract_musicbrainz()
    elif a.stage == "discogs":
        profile_discogs()
    elif a.stage == "musicbrainz":
        profile_musicbrainz()
    elif a.stage == "wikidata":
        profile_wikidata()
    elif a.stage == "render":
        render(check=a.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
