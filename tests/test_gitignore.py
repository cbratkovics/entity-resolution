""".gitignore keeps the dumps and every derived row out of git (docs/BRIEF.md rule 2)."""

from __future__ import annotations

import subprocess

import pytest

from entity_resolution.config import REPO_ROOT


@pytest.mark.parametrize(
    "path",
    [
        "data/x.parquet",
        "data/cache/discogs.parquet",
        "discogs_20260901_masters.xml.gz",
        "data/mbdump.tar.bz2",
        ".venv/bin/python",
        ".duckdb/dev.duckdb",
        "docs/site/data/fct_eval_metrics.csv",
    ],
)
def test_path_is_ignored(path: str) -> None:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, f"{path} is not ignored"


@pytest.mark.parametrize(
    "path",
    [
        "artifacts/manifest.json",
        "artifacts/schemas/x.schema.json",
        # the data/ rule is anchored to the repository root: package modules under
        # entity_resolution/data/ must never be ignored (a new adapter was once left unstaged)
        "entity_resolution/data/new_adapter.py",
        "tests/data/fixture.py",
    ],
)
def test_artifacts_are_not_ignored(path: str) -> None:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 1, f"{path} is ignored"
