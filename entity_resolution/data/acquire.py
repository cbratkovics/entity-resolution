"""Acquisition: the dumps, their download with a disk check and sha256, and streaming
extraction of named members out of a tar archive without unpacking anything else.

Used by the Phase 1 profiler and the Phase 2 adapters alike, so every download is timed,
hashed and recorded the same way (docs/BRIEF.md 2.2: filenames, sizes, sha256, URLs, licence
URLs travel into the manifest).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import tarfile
import time
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from entity_resolution.config import RAW_DIR

USER_AGENT = (
    "entity-resolution/0.1 (https://github.com/cbratkovics/entity-resolution; "
    "cbratkovics@gmail.com)"
)
MIN_FREE_FACTOR = 2.0
"""Refuse a download unless free disk is at least this many times the file size."""


@dataclass(frozen=True)
class DumpSpec:
    name: str
    side: str
    filename: str
    url: str
    licence_url: str
    dump_date: str


DISCOGS = DumpSpec(
    name="discogs",
    side="B",
    filename="discogs_20260901_masters.xml.gz",
    url="https://data.discogs.com/?download=data%2F2026%2Fdiscogs_20260901_masters.xml.gz",
    licence_url="https://data.discogs.com/",
    dump_date="2026-09-01",
)
MUSICBRAINZ = DumpSpec(
    name="musicbrainz",
    side="A",
    filename="mbdump.tar.bz2",
    url=(
        "https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20260919-002047/mbdump.tar.bz2"
    ),
    licence_url="https://musicbrainz.org/doc/About/Data_License",
    dump_date="2026-09-19",
)
DUMPS: dict[str, DumpSpec] = {d.name: d for d in (DISCOGS, MUSICBRAINZ)}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def gib(n: int) -> float:
    return round(n / 2**30, 2)


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def request(url: str, method: str = "GET", data: bytes | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, method=method, data=data, headers={"User-Agent": USER_AGENT})


def file_sha256(path: Path) -> tuple[int, str]:
    sha = hashlib.sha256()
    n = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            sha.update(chunk)
            n += len(chunk)
    return n, sha.hexdigest()


def check_free_disk(path: Path, needed_bytes: int | None) -> int:
    """Print free disk and the requirement; abort before the first byte if it is not met."""
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    need = needed_bytes or 0
    print(
        f"free disk at {path}: {gib(free)} GiB; download size "
        f"{gib(need) if needed_bytes else 'unknown'} GiB; required {gib(int(need * MIN_FREE_FACTOR))} GiB"
    )
    if needed_bytes and free < needed_bytes * MIN_FREE_FACTOR:
        raise SystemExit("not enough free disk; aborting before any download")
    return free


def meta_path(spec: DumpSpec, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / (spec.filename + ".meta.json")


def download(spec: DumpSpec, raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    """Download a dump once; return its metadata (bytes, sha256, seconds, url, dump date)."""
    dest = raw_dir / spec.filename
    meta = meta_path(spec, raw_dir)
    if dest.exists() and meta.exists():
        return read_json(meta)
    sha = hashlib.sha256()
    n = 0
    started = utc_now()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(request(spec.url), timeout=120) as r:
        expected = int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None
        free_before = check_free_disk(raw_dir, expected)
        print(f"{spec.name}: downloading {spec.url} -> {dest}")
        t0 = time.monotonic()
        with tmp.open("wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                sha.update(chunk)
                n += len(chunk)
    seconds = round(time.monotonic() - t0, 1)
    if expected is not None and n != expected:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"{spec.name}: downloaded {n} bytes, expected {expected}")
    tmp.rename(dest)
    record = {
        **asdict(spec),
        "source": spec.name,
        "bytes": n,
        "sha256": sha.hexdigest(),
        "download_seconds": seconds,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "free_disk_before_bytes": free_before,
    }
    write_json(record, meta)
    print(f"{spec.name}: {gib(n)} GiB in {seconds}s, sha256 {record['sha256'][:12]}…")
    return record


def extract_members(
    archive: Path, wanted: dict[str, str], out_dir: Path
) -> tuple[dict[str, dict[str, Any]], int]:
    """Stream ``archive`` once and write the members named in ``wanted`` (member name ->
    output file name) to ``out_dir``; nothing else touches disk. Returns per-file stats and
    the number of members scanned."""
    out_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, dict[str, Any]] = {}
    members_seen = 0
    t0 = time.monotonic()
    with tarfile.open(archive, mode="r|bz2") as tar:
        for member in tar:
            members_seen += 1
            name = wanted.get(member.name)
            if name is None or not member.isfile():
                continue
            src = tar.extractfile(member)
            assert src is not None
            dest = out_dir / name
            sha = hashlib.sha256()
            n = 0
            with dest.open("wb") as fh:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    sha.update(chunk)
                    n += len(chunk)
            found[name] = {"bytes": n, "sha256": sha.hexdigest()}
            print(f"  extracted {name}: {gib(n)} GiB ({round(time.monotonic() - t0)}s elapsed)")
            if len(found) == len(wanted):
                break
    return found, members_seen


def extract_tables(
    archive: Path, tables: Iterable[str], out_dir: Path, prefix: str = "mbdump/"
) -> dict[str, Any]:
    """Extract the listed tables (skipping those already on disk) in as many streaming passes
    as have been needed; every pass is timed and the record is kept in ``_extract.meta.json``."""
    tables = list(tables)
    meta_file = out_dir / "_extract.meta.json"
    passes_file = out_dir / "_extract_passes.json"
    if meta_file.exists():
        meta = read_json(meta_file)
        if set(meta["tables"]) >= set(tables):
            return meta
    out_dir.mkdir(parents=True, exist_ok=True)
    passes: list[dict[str, Any]] = read_json(passes_file) if passes_file.exists() else []
    wanted = {f"{prefix}{t}": t for t in tables if not (out_dir / t).exists()}
    found: dict[str, dict[str, Any]] = {}
    members_seen = 0
    started = utc_now()
    t0 = time.monotonic()
    if wanted:
        print(f"{archive.name}: streaming the archive for {sorted(wanted.values())}")
        found, members_seen = extract_members(archive, wanted, out_dir)
    seconds = round(time.monotonic() - t0, 1)
    if wanted:
        passes.append(
            {
                "tables": sorted(found),
                "members_scanned": members_seen,
                "extract_seconds": seconds,
                "started_at_utc": started,
                "finished_at_utc": utc_now(),
            }
        )
        write_json(passes, passes_file)
    missing = sorted(t for t in tables if not (out_dir / t).exists())
    if missing:
        raise SystemExit(f"{archive.name}: tables missing from the archive: {missing}")
    stats: dict[str, dict[str, Any]] = {}
    for t in tables:
        if t in found:
            stats[t] = found[t]
        else:
            n, digest = file_sha256(out_dir / t)
            stats[t] = {"bytes": n, "sha256": digest}
    meta = {
        "archive": archive.name,
        "tables": stats,
        "passes": passes,
        "extract_passes": len(passes),
        "extract_seconds": round(sum(p["extract_seconds"] for p in passes), 1),
        "extracted_bytes": sum(v["bytes"] for v in stats.values()),
        "finished_at_utc": utc_now(),
    }
    write_json(meta, meta_file)
    return meta
