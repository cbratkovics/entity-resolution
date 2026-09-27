"""The QA scenario catalog (docs/lab/scenarios.json) names only things that exist: case ids in
the committed case bundle, fixture ids in the shared policy fixtures, files in the tree and Make
targets in the Makefile. The app source types no measured artifact number of its own."""

from __future__ import annotations

import json
import re

import pytest

from entity_resolution.config import ARTIFACTS_DIR, REPO_ROOT

CATALOG = REPO_ROOT / "docs" / "lab" / "scenarios.json"
FIXTURES = REPO_ROOT / "apps" / "decision-lab" / "fixtures" / "policy_fixtures.json"
APP_SRC = REPO_ROOT / "apps" / "decision-lab" / "src"


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_catalog_shape_and_stable_ids() -> None:
    cat = _catalog()
    ids = [s["id"] for s in cat["scenarios"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    required = {
        "id",
        "kind",
        "question",
        "evidence",
        "code",
        "expected",
        "perturbation",
        "disproof",
        "commands",
        "ui",
    }
    for s in cat["scenarios"]:
        assert required <= set(s), s["id"]
        assert s["kind"] in {"real", "synthetic"}
        assert re.fullmatch(r"S\d{2}_[a-z0-9_]+", s["id"])
        assert s["ui"].startswith("#/")


def test_catalog_case_and_fixture_ids_exist() -> None:
    cases = json.loads((ARTIFACTS_DIR / "lab" / "cases.json").read_text(encoding="utf-8"))
    case_ids = {c["case_id"] for c in cases["cases"]}
    fixture_ids = {c["id"] for c in json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]}
    for s in _catalog()["scenarios"]:
        for cid in s.get("case_ids", []):
            assert cid in case_ids, (s["id"], cid)
        for fid in s.get("fixture_ids", []):
            assert fid in fixture_ids, (s["id"], fid)
        if s["kind"] == "synthetic":
            assert not s.get("case_ids"), "synthetic scenarios never cite real cases"


def test_catalog_files_and_make_targets_exist() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.M))
    for s in _catalog()["scenarios"]:
        for ref in s["evidence"] + s["code"]:
            path = ref.split("#", 1)[0]
            assert (REPO_ROOT / path).exists(), (s["id"], path)
        for cmd in s["commands"]:
            m = re.match(r"make (\S+)", cmd)
            if m:
                assert m.group(1) in targets, (s["id"], cmd)


def _artifact_numbers() -> set[str]:
    """Six-decimal ratios and large counts from the evaluation artifacts: the values the app
    must read from data, never type."""
    out: set[str] = set()

    def walk(o) -> None:  # type: ignore[no-untyped-def]
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, float) and not o.is_integer():
            s = repr(o)
            if len(s.split(".")[1]) >= 4:
                out.add(s)
        elif isinstance(o, int) and o >= 1000:
            out.add(str(o))

    for p in sorted(ARTIFACTS_DIR.glob("eval_*.json")):
        walk(json.loads(p.read_text(encoding="utf-8"))["metrics"])
    return out


@pytest.mark.skipif(not APP_SRC.exists(), reason="app source not present")
def test_app_source_types_no_artifact_number() -> None:
    numbers = _artifact_numbers()
    offenders = []
    for f in sorted(APP_SRC.rglob("*")):
        if f.suffix not in {".ts", ".tsx", ".css", ".html"}:
            continue
        text = f.read_text(encoding="utf-8")
        for n in numbers:
            if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w.])", text):
                offenders.append((f.relative_to(REPO_ROOT).as_posix(), n))
    assert not offenders, offenders[:10]
