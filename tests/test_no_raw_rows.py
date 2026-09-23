"""No record attribute ever enters git (docs/BRIEF.md rule 2): no tracked CSV, JSON or parquet
carries a title, artist or name column, and no dump or data directory is tracked."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

from entity_resolution.config import REPO_ROOT

FORBIDDEN_COLUMNS = {"title", "artist", "artists", "artist_credit", "name", "label"}
FORBIDDEN_PATHS = ("data/",)
FORBIDDEN_SUFFIXES = (".xml.gz", ".tar.bz2", ".parquet")


def _tracked() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def _json_keys(obj, keys: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k).lower())
            _json_keys(v, keys)
    elif isinstance(obj, list):
        for v in obj:
            _json_keys(v, keys)


def test_no_data_directory_or_dump_is_tracked() -> None:
    for p in _tracked():
        s = p.as_posix()
        assert not any(s.startswith(d) for d in FORBIDDEN_PATHS), s
        assert not any(s.endswith(x) for x in FORBIDDEN_SUFFIXES), s


def test_no_tracked_csv_has_an_attribute_column() -> None:
    for p in _tracked():
        if p.suffix.lower() != ".csv":
            continue
        with (REPO_ROOT / p).open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh), [])
        bad = {h.strip().lower() for h in header} & FORBIDDEN_COLUMNS
        assert not bad, f"{p}: forbidden columns {sorted(bad)}"


FREE_TEXT_ALLOWED_PREFIXES = ("artifacts/eval_", "artifacts/methods/")
"""Artifacts whose schema carries prose (metric definitions, method definitions). Profile
artifacts are not among them: every string there must be a hash, URL, date or token."""


def _string_values(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _string_values(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _string_values(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def test_profile_artifacts_carry_no_free_text() -> None:
    token = re.compile(r"^[A-Za-z0-9_.:/+%?=&-]+$")
    for p in _tracked():
        if not p.as_posix().startswith("artifacts/profile/") or p.suffix != ".json":
            continue
        values: list[str] = []
        _string_values(json.loads((REPO_ROOT / p).read_text(encoding="utf-8")), values)
        with_space = [v for v in values if not token.fullmatch(v)]
        assert not with_space, f"{p}: string values that look like free text: {with_space[:5]}"


def test_no_tracked_artifact_json_has_an_attribute_key() -> None:
    for p in _tracked():
        if p.suffix.lower() != ".json" or not p.as_posix().startswith("artifacts/"):
            continue
        if p.parent.name == "schemas":
            continue
        keys: set[str] = set()
        _json_keys(json.loads((REPO_ROOT / p).read_text(encoding="utf-8")), keys)
        bad = keys & FORBIDDEN_COLUMNS
        assert not bad, f"{p}: forbidden keys {sorted(bad)}"
