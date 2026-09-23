"""Paths and the one project configuration shared by every layer.

Nothing here depends on the environment; there are no secrets. ``PROJECT`` is the single source
of the project-wide vocabulary (docs/BRIEF.md section 2). dbt cannot import Python, so
``dbt/dbt_project.yml`` carries a mirror of :func:`dbt_vars` and ``tests/test_project_config.py``
fails when the mirror diverges.

Side A is MusicBrainz release groups (ADR 0001); the sample scope and share are the
constants below, also from ADR 0001.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENV_PREFIX = "ENTITY_RESOLUTION_"
REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(os.environ.get(ENV_PREFIX + "ARTIFACTS_DIR", REPO_ROOT / "artifacts"))
DATA_DIR = Path(os.environ.get(ENV_PREFIX + "DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
SAMPLE_DIR = DATA_DIR / "sample"
MANIFEST_PATH = ARTIFACTS_DIR / "manifest.json"
TRUTH_AUDIT_PATH = ARTIFACTS_DIR / "truth_audit.json"
CONTRACTS_PATH = ARTIFACTS_DIR / "contracts.json"
SCHEMAS_DIR = ARTIFACTS_DIR / "schemas"
METHODS_DIR = ARTIFACTS_DIR / "methods"
SITE_DATA_DIR = REPO_ROOT / "docs" / "site" / "data"

SIDE_B = "discogs"
"""Side B is fixed by the brief: Discogs masters."""
SIDE_A_CANDIDATES: tuple[str, ...] = ("musicbrainz", "wikidata")
"""The two side-A candidates profiled in Phase 1; one is chosen in ADR 0001."""
METHOD_VERSIONS: tuple[str, ...] = ("exact_v1", "rules_v1", "learned_v1")
FOLDS: tuple[str, ...] = ("fit", "calibrate", "test")
TIERS: tuple[str, ...] = ("auto_accept", "review", "reject")

UNLINKED_SHARE = 0.50
"""ADR 0001: share of each sampled side that is unlinked (unlinked count equals linked count)."""
A_SCOPE_PRIMARY_TYPE = "Album"
"""ADR 0001: side A is restricted to release groups of this primary type."""


@dataclass(frozen=True)
class ProjectConfig:
    """Project-wide constants. Frozen: change the values here, then regenerate the mirrors."""

    slug: str
    display_name: str
    package_name: str
    domain_summary: str
    side_b: str
    side_a: str | None
    side_a_candidates: tuple[str, ...]
    method_versions: tuple[str, ...]
    folds: tuple[str, ...]
    tiers: tuple[str, ...]
    dbt_project_name: str
    github_owner: str
    repo_url: str
    pages_url: str
    python_version: str

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @property
    def sides(self) -> tuple[str, str | None]:
        """``(side_b, side_a)``; side A is ``None`` before ADR 0001."""
        return (self.side_b, self.side_a)

    def require_side_a(self) -> str:
        if self.side_a is None:
            raise RuntimeError(
                "side A is not decided yet: Phase 1 ends with a stop-and-present and the "
                "owner's choice is recorded in docs/adr/0001-*.md before any matching code runs"
            )
        return self.side_a


PROJECT = ProjectConfig(
    slug="entity-resolution",
    display_name="Entity Resolution",
    package_name="entity_resolution",
    domain_summary=(
        "Record linkage between open music catalogues, measured against labelled ground truth."
    ),
    side_b=SIDE_B,
    side_a="musicbrainz",
    side_a_candidates=SIDE_A_CANDIDATES,
    method_versions=METHOD_VERSIONS,
    folds=FOLDS,
    tiers=TIERS,
    dbt_project_name="entity_resolution_dbt",
    github_owner="cbratkovics",
    repo_url="https://github.com/cbratkovics/entity-resolution",
    pages_url="https://cbratkovics.github.io/entity-resolution/",
    python_version="3.12",
)


def env(name: str, default: str = "") -> str:
    """Read ``<PREFIX>_<name>`` from the environment."""
    return os.environ.get(ENV_PREFIX + name, default)


def dbt_vars() -> dict[str, Any]:
    """The project vars ``dbt/dbt_project.yml`` must declare with exactly these defaults."""
    return {
        "method_versions": list(PROJECT.method_versions),
        "folds": list(PROJECT.folds),
        "tiers": list(PROJECT.tiers),
        "artifacts_dir": "artifacts",
    }


def _main(argv: list[str]) -> int:  # pragma: no cover - thin CLI
    """python -m entity_resolution.config --dbt-vars | --json | <field>"""
    if not argv or argv[0] in {"-h", "--help"}:
        print(_main.__doc__)
        return 0
    if argv[0] == "--dbt-vars":
        print(json.dumps(dbt_vars()))
    elif argv[0] == "--json":
        print(json.dumps(PROJECT.as_dict(), indent=2, default=list))
    else:
        value = getattr(PROJECT, argv[0])
        print(",".join(map(str, value)) if isinstance(value, tuple) else value)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv[1:]))
