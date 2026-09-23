"""Method version records and the artifact manifest.

``artifacts/manifest.json`` (schema ``manifest.schema.json``) records the dumps, the sample rule
and the counts a run was produced from. ``artifacts/methods/<method_version>.json`` (schema
``method_version.schema.json``) records what each method is: its definition, fixed parameters,
what it was fitted on and the tier policy it was decided under. Both hold identifiers, hashes,
parameters and counts only.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

from entity_resolution.config import (
    ARTIFACTS_DIR,
    MANIFEST_PATH,
    METHODS_DIR,
    REPO_ROOT,
    SCHEMAS_DIR,
)
from entity_resolution.features import FEATURE_VERSION

MANIFEST_VERSION = "2.0"
METHOD_RECORD_VERSION = "1.0"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def code_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _dump_json(obj: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def empty_manifest(commit: str | None = None) -> dict[str, Any]:
    """A valid manifest for a tree with no data: no sources, no sample, zero counts."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "updated_at_utc": "1970-01-01T00:00:00+00:00",
        "feature_version": FEATURE_VERSION,
        "code_commit": commit if commit is not None else "unknown",
        "side_a": None,
        "sources": [],
        "sample": None,
        "counts": {},
        "run_id": None,
    }


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found at {path}; run `make full` first")
    return json.loads(path.read_text(encoding="utf-8"))


def schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_and_write(obj: dict[str, Any], schema_name: str, path: Path) -> Path:
    """Validate against ``artifacts/schemas/<name>.schema.json`` before anything is written."""
    jsonschema.validate(obj, schema(schema_name))
    _dump_json(obj, path)
    return path


def write_manifest(
    manifest: dict[str, Any], path: Path = MANIFEST_PATH, *, validate: bool = False
) -> None:
    manifest = {**manifest, "manifest_version": MANIFEST_VERSION, "updated_at_utc": utc_now_iso()}
    if validate:
        jsonschema.validate(manifest, schema("manifest"))
    _dump_json(manifest, path)


def method_record_path(method_version: str, methods_dir: Path = METHODS_DIR) -> Path:
    return methods_dir / f"{method_version}.json"


def read_method_records(methods_dir: Path = METHODS_DIR) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(methods_dir.glob("*.json"))]


def write_method_record(record: dict[str, Any], methods_dir: Path = METHODS_DIR) -> Path:
    record = {**record, "record_version": METHOD_RECORD_VERSION}
    path = method_record_path(record["method_version"], methods_dir)
    _dump_json(record, path)
    return path


def eval_artifact_paths(artifacts: Path = ARTIFACTS_DIR) -> list[Path]:
    return sorted(artifacts.glob("eval_*.json"))
