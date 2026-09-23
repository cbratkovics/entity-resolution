"""Render ``docs/METHODS_CARD.md`` from committed artifacts.

Every figure is read from the manifest, the method version records and the evaluation
artifacts; the artifact key is printed next to each figure. The rendering is a pure function of
the artifacts, so a rerun on the same tree is byte-identical. With no run yet the card states
that plainly; ``scripts/check_model_card.py`` fails on placeholder markers, never on absence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from entity_resolution.config import ARTIFACTS_DIR, METHODS_DIR, PROJECT, REPO_ROOT
from entity_resolution.eval import evaluator
from entity_resolution.models import registry

CARD_PATH = REPO_ROOT / "docs" / "METHODS_CARD.md"
HEADER = "# Methods card\n\n_Generated from committed artifacts by `scripts/check_model_card.py --write`; do not edit by hand._\n"


def render(
    manifest: dict[str, Any],
    method_records: list[dict[str, Any]],
    eval_artifacts: list[dict[str, Any]],
) -> str:
    lines = [HEADER]
    lines.append("## Run")
    lines.append("")
    lines.append("| Field | Value | Source key |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Feature version | `{manifest['feature_version']}` | `artifacts/manifest.json#feature_version` |"
    )
    lines.append(
        f"| Code commit | `{manifest['code_commit']}` | `artifacts/manifest.json#code_commit` |"
    )
    side_a = manifest.get("side_a") or "undecided (ADR 0001 pending)"
    lines.append(f"| Side A | {side_a} | `artifacts/manifest.json#side_a` |")
    lines.append(f"| Side B | {PROJECT.side_b} | fixed by `docs/BRIEF.md` (section `2.1`) |")
    run_id = manifest.get("run_id") or "none"
    lines.append(f"| Run id | `{run_id}` | `artifacts/manifest.json#run_id` |")
    lines.append("")
    if not method_records and not eval_artifacts:
        lines.append("## Methods")
        lines.append("")
        lines.append(
            "No run has been recorded: `artifacts/methods/` and `artifacts/eval_*.json` are "
            "empty. The methods `exact_v1`, `rules_v1` and `learned_v1` are defined in "
            "docs/BRIEF.md (section `2.7`) and are built in Phase 4."
        )
        lines.append("")
        return "\n".join(lines)
    lines.append("## Methods")
    lines.append("")
    lines.append("| Method version | Definition | Fitted on | Source |")
    lines.append("|---|---|---|---|")
    for rec in sorted(method_records, key=lambda r: r["method_version"]):
        mv = rec["method_version"]
        lines.append(
            f"| `{mv}` | {rec['definition']} | {rec['fitted_on'] or 'nothing'} | `artifacts/methods/{mv}.json` |"
        )
    lines.append("")
    lines.append("## Evaluation (test fold only)")
    lines.append("")
    for ev in sorted(eval_artifacts, key=lambda e: e["method_version"]):
        mv = ev["method_version"]
        lines.append(f"### `{mv}`")
        lines.append("")
        lines.append(
            f"Source: `artifacts/eval_{mv}.json`; input feature version `{ev['input']['feature_version']}`, code commit `{ev['input']['code_commit']}`."
        )
        lines.append("")
        if ev.get("metrics") is None:
            lines.append("Metrics not computed yet (Phase 4).")
            lines.append("")
            continue
        lines.append("| Metric | Value | Key |")
        lines.append("|---|---|---|")
        for key in sorted(ev["metrics"]):
            value = ev["metrics"][key]
            if isinstance(value, int | float):
                lines.append(f"| {key} | {value} | `artifacts/eval_{mv}.json#metrics.{key}` |")
        lines.append("")
    lines.append("## Metric definitions")
    lines.append("")
    definitions = (
        eval_artifacts[0]["metric_definitions"] if eval_artifacts else evaluator.METRIC_DEFINITIONS
    )
    for key in sorted(definitions):
        lines.append(f"- `{key}`: {definitions[key]}")
    lines.append("")
    return "\n".join(lines)


def render_from_tree(*, artifacts: Path = ARTIFACTS_DIR, methods_dir: Path = METHODS_DIR) -> str:
    manifest = registry.read_manifest(artifacts / "manifest.json")
    return render(
        manifest, registry.read_method_records(methods_dir), evaluator.read_all(artifacts)
    )


def write_card(out_path: Path = CARD_PATH, **kwargs: Any) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_from_tree(**kwargs), encoding="utf-8")
    return out_path
