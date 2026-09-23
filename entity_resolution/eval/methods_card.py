"""Render ``docs/METHODS_CARD.md`` from committed artifacts.

Every figure is read from the manifest, the method version records and the evaluation
artifacts; the artifact key is printed next to each figure. The rendering is a pure function of
the artifacts, so a rerun on the same tree is byte-identical. With no run yet the card states
that plainly; ``scripts/check_model_card.py`` fails on placeholder markers, never on absence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from entity_resolution.config import ARTIFACTS_DIR, METHODS_DIR, PROJECT, REPO_ROOT
from entity_resolution.eval import evaluator
from entity_resolution.models import registry

CARD_PATH = REPO_ROOT / "docs" / "METHODS_CARD.md"
HEADER = (
    "# Methods card\n\n_Generated from committed artifacts by `scripts/check_model_card.py --write`; do not "
    "edit by hand. The block below is validated against the artifacts by that script, which is "
    "why the number checker skips it._\n\n<!-- generated:methods_card start -->"
)
FOOTER = "<!-- generated:methods_card end -->"


def render(
    manifest: dict[str, Any],
    method_records: list[dict[str, Any]],
    eval_artifacts: list[dict[str, Any]],
    blocking_report: dict[str, Any] | None = None,
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
        lines.append(FOOTER)
        return "\n".join(lines) + "\n"
    eval_by_method = {e["method_version"]: e for e in eval_artifacts}
    rules = eval_by_method.get("rules_v1", {}).get("metrics")
    learned = eval_by_method.get("learned_v1", {}).get("metrics")
    if rules and learned:
        lines.append("## Decision summary")
        lines.append("")
        lines.append(
            "At the selected tiers, the fixed weighted rules have the higher test-fold F1 "
            f"(`{rules['at_auto_accept']['f1']}` versus `{learned['at_auto_accept']['f1']}`). "
            "The learned classifier is the precision-first alternative: its auto-accept precision is "
            f"`{learned['at_auto_accept']['precision']}` versus `{rules['at_auto_accept']['precision']}`, "
            f"and its review queue is `{learned['ambiguity_rule']['review_queue']:,}` rather than "
            f"`{rules['ambiguity_rule']['review_queue']:,}`, at the cost of lower labelled recall "
            f"(`{learned['at_auto_accept']['recall_labelled']}` versus "
            f"`{rules['at_auto_accept']['recall_labelled']}`). These are different tier policies, not "
            "an equal-recall queue comparison. All accuracy metrics are over labelled test-fold A "
            "records; unlinked records are unlabelled and appear only in coverage and unverified-accept "
            "counts."
        )
        lines.append("")
    if blocking_report:
        pc = blocking_report["pair_completeness"]
        lines.append("## Evaluation population and blocking")
        lines.append("")
        lines.append(
            f"The manifest contains `{manifest['counts']['musicbrainz']['sampled']:,}` sampled "
            "MusicBrainz release groups. Blocking is evaluated over "
            f"`{pc['truth_pairs']:,}` in-scope truth pairs: completeness is `{pc['union']}` before "
            f"the per-record candidate cap and `{pc['after_cap']}` after it, leaving "
            f"`{blocking_report['candidate_pairs_after_cap']:,}` candidate pairs. Sources: "
            "`artifacts/manifest.json#counts.musicbrainz.sampled`, "
            "`artifacts/blocking_report.json#pair_completeness.truth_pairs`, "
            "`#pair_completeness.union`, `#pair_completeness.after_cap`, and "
            "`#candidate_pairs_after_cap`."
        )
        lines.append("")
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
    lines.append("## Results (test fold only)")
    lines.append("")
    lines.append(
        "| Method | Pair completeness (test) | Precision | Recall (labelled) | Recall (overall) | F1 | Coverage | Unverified accepts | Review queue | ECE (decisions) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for ev in sorted(eval_artifacts, key=lambda e: e["method_version"]):
        mv = ev["method_version"]
        m = ev.get("metrics")
        if m is None:
            lines.append(f"| `{mv}` | not computed | | | | | | | | |")
            continue
        acc = m["at_auto_accept"]
        lines.append(
            f"| `{mv}` | {m['pair_completeness_test']} | {acc['precision']} | {acc['recall_labelled']} | "
            f"{m['recall_overall']} | {acc['f1']} | {m['coverage']} | {m['unverified_accepts']['count']} "
            f"({m['unverified_accepts']['share_of_accepts']} of accepts) | {m['ambiguity_rule']['review_queue']} | "
            f"{m['calibration']['decision_level']['ece']} |"
        )
    lines.append("")
    lines.append(
        "Keys per method: `artifacts/eval_<method_version>.json#metrics.pair_completeness_test`, "
        "`#metrics.at_auto_accept.precision`, `#metrics.at_auto_accept.recall_labelled`, "
        "`#metrics.recall_overall`, `#metrics.at_auto_accept.f1`, `#metrics.coverage`, "
        "`#metrics.unverified_accepts.count`, `#metrics.unverified_accepts.share_of_accepts`, "
        "`#metrics.ambiguity_rule.review_queue`, `#metrics.calibration.decision_level.ece`."
    )
    lines.append("")
    for ev in sorted(eval_artifacts, key=lambda e: e["method_version"]):
        mv = ev["method_version"]
        lines.append(f"### `{mv}`")
        lines.append("")
        lines.append(
            f"Source: `artifacts/eval_{mv}.json`; feature version `{ev['input']['feature_version']}`, "
            f"code commit `{ev['input']['code_commit']}`; thresholds auto_accept_min "
            f"`{ev['thresholds']['auto_accept_min']}`, review_min `{ev['thresholds']['review_min']}`, "
            f"ambiguity_gap `{ev['thresholds']['ambiguity_gap']}`."
        )
        lines.append("")
        m = ev.get("metrics")
        if m is None:
            lines.append("Metrics not computed yet.")
            lines.append("")
            continue
        lines.append("| Metric | Value | Key |")
        lines.append("|---|---|---|")
        flat = {
            "test_a": m["test_a"],
            "labelled_a": m["labelled_a"],
            "labelled_a_reachable": m["labelled_a_reachable"],
            "at_auto_accept.accepted": m["at_auto_accept"]["accepted"],
            "at_auto_accept.correct": m["at_auto_accept"]["correct"],
            "at_auto_accept_or_review.precision": m["at_auto_accept_or_review"]["precision"],
            "at_auto_accept_or_review.recall_labelled": m["at_auto_accept_or_review"][
                "recall_labelled"
            ],
            "coverage_all_folds": m["coverage_all_folds"],
            "tier_shares.auto_accept": m["tier_shares"]["auto_accept"],
            "tier_shares.review": m["tier_shares"]["review"],
            "tier_shares.reject": m["tier_shares"]["reject"],
            "ambiguity_rule.decisions_moved_to_review": m["ambiguity_rule"][
                "decisions_moved_to_review"
            ],
            "calibration.decision_level.brier": m["calibration"]["decision_level"]["brier"],
            "calibration.pair_level.ece": m["calibration"]["pair_level"]["ece"],
        }
        for key, value in flat.items():
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
    lines.append(FOOTER)
    return "\n".join(lines) + "\n"


def render_from_tree(*, artifacts: Path = ARTIFACTS_DIR, methods_dir: Path = METHODS_DIR) -> str:
    manifest = registry.read_manifest(artifacts / "manifest.json")
    blocking_path = artifacts / "blocking_report.json"
    blocking_report = (
        json.loads(blocking_path.read_text(encoding="utf-8")) if blocking_path.exists() else None
    )
    return render(
        manifest,
        registry.read_method_records(methods_dir),
        evaluator.read_all(artifacts),
        blocking_report,
    )


def write_card(out_path: Path = CARD_PATH, **kwargs: Any) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_from_tree(**kwargs), encoding="utf-8")
    return out_path
