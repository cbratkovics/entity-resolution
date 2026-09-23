"""Every profile artifact validates against profile.schema.json and carries no free text."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

from entity_resolution.config import ARTIFACTS_DIR, SCHEMAS_DIR

PROFILES = sorted((ARTIFACTS_DIR / "profile").glob("*.json"))
SCHEMA = json.loads((SCHEMAS_DIR / "profile.schema.json").read_text(encoding="utf-8"))
ALLOWED_STRING = re.compile(
    r"^([0-9a-f]{40}|[0-9a-f]{64}|unknown|https?://\S+|\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\+00:00|Z))?"
    r"|\d+\.\d+\.\d+|[A-Za-z0-9_.-]+)$"
)
"""A string value is a hash, a URL, a date, a version or a single token (enum value, filename).
Anything with a space is free text and fails: a title or an artist credit cannot pass."""


def _strings(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def test_profile_schema_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.name)
def test_profile_validates_and_names_its_source(path: Path) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(artifact, SCHEMA)
    assert artifact["source"] == path.stem


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.name)
def test_profile_strings_are_hashes_urls_dates_or_tokens(path: Path) -> None:
    values: list[str] = []
    _strings(json.loads(path.read_text(encoding="utf-8")), values)
    bad = [v for v in values if not ALLOWED_STRING.fullmatch(v)]
    assert not bad, f"{path.name}: free-text string values {bad[:5]}"


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.name)
def test_examples_are_hashes_only(path: Path) -> None:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    for ex in artifact.get("examples", []):
        for k, v in ex.items():
            if k.endswith("_hash"):
                assert re.fullmatch(r"[0-9a-f]{64}", v), f"{path.name}: {k} is not a sha256"
            elif k == "pattern":
                assert v in SCHEMA["$defs"]["pattern"]["enum"]
            else:
                assert k in ("year_a", "year_b") and (v is None or isinstance(v, int))
