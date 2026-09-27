"""The lab contracts: schema loading with cross-file references, canonical JSON, hashing, the
public export allowlist, the forbidden-key check and the identifier validators
(docs/DECISION_LAB.md section 2; docs/BRIEF.md hard rule 2).

Every file the lab publishes under ``artifacts/lab/`` is written by :func:`dumps_canonical`
(sorted keys, one-space indent, ASCII, no non-finite numbers, trailing newline) so the same
content always gives the same bytes and the same sha256. The allowlist is closed: ``check``
fails on any file under ``artifacts/lab/`` it does not name. The forbidden-key check is stricter
than ``tests/test_no_raw_rows.py``: a key named ``title``, ``artist``, ``artists``,
``artist_credit``, ``name`` or ``label`` is rejected whatever its value, and identifier and
hash fields must hold tokens, never free text.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from entity_resolution.config import METHOD_VERSIONS, SCHEMAS_DIR

SCHEMA_NAMES: tuple[str, ...] = (
    "lab_manifest",
    "lab_snapshot",
    "lab_cases",
    "lab_replay_meta",
    "lab_receipt",
    "lab_review_events",
    "lab_synthetic_sandbox",
)

FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {"title", "artist", "artists", "artist_credit", "name", "label"}
)
"""Keys that could carry a record attribute (tests/test_no_raw_rows.py); never allowed here."""

ID_LIKE_KEY = re.compile(r"(^|_)(id|ids|sha256|digest|commit)$")
"""Keys whose string values must be tokens (identifiers, hashes, commits), never free text."""
TOKEN = re.compile(r"^[A-Za-z0-9_.:/+@=-]+$")

A_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
"""A MusicBrainz release-group gid: lower-case UUID."""
B_ID_RE = re.compile(r"^[1-9][0-9]{0,11}$")
"""A Discogs master id: positive integer without leading zeros."""

MUSICBRAINZ_RELEASE_GROUP = "https://musicbrainz.org/release-group/"
DISCOGS_MASTER = "https://www.discogs.com/master/"

PUBLIC_EXPORT_ALLOWLIST: tuple[str, ...] = (
    "manifest.json",
    "snapshot.json",
    "cases.json",
    "case_selection.json",
    *(f"replay/replay_{m}.json" for m in METHOD_VERSIONS),
    *(f"replay/replay_{m}.test.csv.gz" for m in METHOD_VERSIONS),
)
"""Every file that may exist under ``artifacts/lab/``, as a path relative to that directory."""

SCHEMA_BY_FILE: dict[str, str] = {
    "manifest.json": "lab_manifest",
    "snapshot.json": "lab_snapshot",
    "cases.json": "lab_cases",
    **{f"replay/replay_{m}.json": "lab_replay_meta" for m in METHOD_VERSIONS},
}
"""Schema per allowlisted JSON file; ``case_selection.json`` is a flat list checked in code."""


class ContractError(ValueError):
    """A lab file or object violates its contract."""


class InvalidIdentifier(ValueError):
    """An identifier does not match its source-native pattern."""


# ---- schemas ---------------------------------------------------------------------------------


def schema_path(schema_name: str, schemas_dir: Path = SCHEMAS_DIR) -> Path:
    if schema_name not in SCHEMA_NAMES:
        raise KeyError(f"unknown lab schema {schema_name!r}; known: {SCHEMA_NAMES}")
    return schemas_dir / f"{schema_name}.schema.json"


def load_schema(schema_name: str, schemas_dir: Path = SCHEMAS_DIR) -> dict[str, Any]:
    return json.loads(schema_path(schema_name, schemas_dir).read_text(encoding="utf-8"))


_REGISTRY_CACHE: dict[Path, Registry] = {}


def registry(schemas_dir: Path = SCHEMAS_DIR) -> Registry:
    """Every lab schema registered under its file name, so ``$ref``s such as
    ``lab_manifest.schema.json#/$defs/population`` resolve across files."""
    if schemas_dir not in _REGISTRY_CACHE:
        resources = [
            (
                f"{n}.schema.json",
                Resource.from_contents(
                    load_schema(n, schemas_dir), default_specification=DRAFT202012
                ),
            )
            for n in SCHEMA_NAMES
        ]
        _REGISTRY_CACHE[schemas_dir] = Registry().with_resources(resources)
    return _REGISTRY_CACHE[schemas_dir]


def validator(schema_name: str, schemas_dir: Path = SCHEMAS_DIR) -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(schema_name, schemas_dir), registry=registry(schemas_dir)
    )


def validation_errors(obj: Any, schema_name: str, schemas_dir: Path = SCHEMAS_DIR) -> list[str]:
    """Every schema violation as ``<json path>: <message>``; empty when the object validates."""
    out = []
    for e in sorted(
        validator(schema_name, schemas_dir).iter_errors(obj), key=lambda e: list(e.path)
    ):
        where = "/".join(str(p) for p in e.absolute_path) or "<root>"
        out.append(f"{where}: {e.message[:200]}")
    return out


def validate(obj: Any, schema_name: str, schemas_dir: Path = SCHEMAS_DIR) -> None:
    """Raise :class:`ContractError` naming the best-matching violation (and the count)."""
    errors = list(validator(schema_name, schemas_dir).iter_errors(obj))
    if errors:
        best = best_match(errors)
        where = "/".join(str(p) for p in best.absolute_path) or "<root>"
        raise ContractError(
            f"{schema_name}: {len(errors)} violation(s); best match at {where}: {best.message[:300]}"
        )


# ---- canonical JSON and hashes ---------------------------------------------------------------


def _assert_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ContractError(f"non-finite number at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ContractError(f"non-string key at {path}: {k!r}")
            _assert_finite(v, f"{path}.{k}")
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            _assert_finite(v, f"{path}[{i}]")


def dumps_canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, indent 1, ASCII only, no NaN or infinity, one trailing
    newline. Floats serialise with ``repr`` (shortest round-trip), so JavaScript reads the
    identical double."""
    _assert_finite(obj)
    return json.dumps(obj, sort_keys=True, indent=1, allow_nan=False, ensure_ascii=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_canonical(obj: Any) -> str:
    """sha256 of the canonical JSON bytes of ``obj`` (what a written file would hash to)."""
    return sha256_bytes(dumps_canonical(obj).encode("utf-8"))


def write_canonical(path: Path, obj: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dumps_canonical(obj).encode("utf-8")
    path.write_bytes(data)
    return data


# ---- allowlist and forbidden keys ------------------------------------------------------------


def is_allowlisted(relative_path: str) -> bool:
    return relative_path in PUBLIC_EXPORT_ALLOWLIST


def unlisted_files(lab_dir: Path) -> list[str]:
    """Files under ``lab_dir`` (recursively) that the allowlist does not name."""
    if not lab_dir.exists():
        return []
    out = []
    for p in sorted(lab_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(lab_dir).as_posix()
            if not is_allowlisted(rel):
                out.append(rel)
    return out


def forbidden_key_problems(obj: Any, path: str = "$") -> list[str]:
    """Forbidden keys anywhere in ``obj`` and free text in identifier or hash fields."""
    problems: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}"
            if str(k).lower() in FORBIDDEN_KEYS:
                problems.append(f"forbidden key at {here}")
            if ID_LIKE_KEY.search(str(k)):
                values = v if isinstance(v, list) else [v]
                for x in values:
                    if isinstance(x, str) and not TOKEN.fullmatch(x):
                        problems.append(f"free text in identifier field at {here}: {x[:40]!r}")
            problems.extend(forbidden_key_problems(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            problems.extend(forbidden_key_problems(v, f"{path}[{i}]"))
    return problems


def assert_no_forbidden_keys(obj: Any, what: str = "object") -> None:
    problems = forbidden_key_problems(obj)
    if problems:
        raise ContractError(f"{what}: " + "; ".join(problems[:5]))


# ---- identifiers and links -------------------------------------------------------------------


def validate_a_id(a_id: Any) -> str:
    if not isinstance(a_id, str) or not A_ID_RE.fullmatch(a_id):
        raise InvalidIdentifier(f"not a release-group gid: {str(a_id)[:60]!r}")
    return a_id


def validate_b_id(b_id: Any) -> str:
    if not isinstance(b_id, str) or not B_ID_RE.fullmatch(b_id):
        raise InvalidIdentifier(f"not a Discogs master id: {str(b_id)[:60]!r}")
    return b_id


def musicbrainz_release_group_url(a_id: str) -> str:
    """The one allowlisted side-A link; raises on anything that is not a gid."""
    return MUSICBRAINZ_RELEASE_GROUP + validate_a_id(a_id)


def discogs_master_url(b_id: str) -> str:
    """The one allowlisted side-B link; raises on anything that is not a master id."""
    return DISCOGS_MASTER + validate_b_id(b_id)
