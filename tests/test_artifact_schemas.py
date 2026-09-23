"""Every committed artifact validates against its schema under artifacts/schemas/."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from entity_resolution.config import ARTIFACTS_DIR, METHODS_DIR, SCHEMAS_DIR


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schemas_are_valid_json_schema() -> None:
    for p in SCHEMAS_DIR.glob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(_load(p))


def test_manifest_validates() -> None:
    jsonschema.validate(_load(ARTIFACTS_DIR / "manifest.json"), _schema("manifest"))


@pytest.mark.parametrize("path", sorted(METHODS_DIR.glob("*.json")), ids=lambda p: p.name)
def test_method_records_validate(path: Path) -> None:
    record = _load(path)
    jsonschema.validate(record, _schema("method_version"))
    assert path.stem == record["method_version"]


@pytest.mark.parametrize("path", sorted(ARTIFACTS_DIR.glob("eval_*.json")), ids=lambda p: p.name)
def test_eval_artifacts_validate(path: Path) -> None:
    artifact = _load(path)
    jsonschema.validate(artifact, _schema("eval_artifact"))
    assert path.stem == f"eval_{artifact['method_version']}"
