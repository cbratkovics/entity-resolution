#!/usr/bin/env python
"""Render the generated blocks of docs/FINDINGS.md and README.md from the committed artifacts:
the results table (one row per method, every cell from eval_<method>.json) and the review-floor
table (from review_sensitivity.json). The blocks sit between
``<!-- generated:<name> start -->`` and ``end`` markers; the number checker skips them because
this script's ``--check`` validates them byte for byte.

    python scripts/render_findings.py            # rewrite the blocks
    python scripts/render_findings.py --check    # fail when a block is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import re

from entity_resolution.config import ARTIFACTS_DIR, REPO_ROOT

METHODS = ("exact_v1", "rules_v1", "learned_v1")
FLOORS_SHOWN = (0.5, 0.7, 0.9)


def _evals() -> dict[str, dict]:
    return {
        m: json.loads((ARTIFACTS_DIR / f"eval_{m}.json").read_text(encoding="utf-8"))
        for m in METHODS
        if (ARTIFACTS_DIR / f"eval_{m}.json").exists()
    }


def _sensitivity() -> dict:
    p = ARTIFACTS_DIR / "review_sensitivity.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def results_table() -> str:
    evals = _evals()
    if not evals:
        return "No run has been recorded (`artifacts/manifest.json#run_id` is null).\n"
    lines = [
        "| method | pair completeness (test) | precision | recall (labelled) | recall (overall) | F1 | coverage | unverified accepts | review queue | ECE (decisions) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in METHODS:
        e = evals.get(m)
        if not e or e.get("metrics") is None:
            continue
        x = e["metrics"]
        a = x["at_auto_accept"]
        lines.append(
            f"| `{m}` | {x['pair_completeness_test']} | {a['precision']} | {a['recall_labelled']} | "
            f"{x['recall_overall']} | {a['f1']} | {x['coverage']} | {x['unverified_accepts']['count']:,} "
            f"({x['unverified_accepts']['share_of_accepts']} of accepts) | {x['ambiguity_rule']['review_queue']:,} | "
            f"{x['calibration']['decision_level']['ece']} |"
        )
    lines.append("")
    lines.append(
        "Keys, per method, in `artifacts/eval_<method_version>.json#metrics`: `pair_completeness_test`, "
        "`at_auto_accept.precision`, `at_auto_accept.recall_labelled`, `recall_overall`, `at_auto_accept.f1`, "
        "`coverage`, `unverified_accepts.count`, `unverified_accepts.share_of_accepts`, "
        "`ambiguity_rule.review_queue`, `calibration.decision_level.ece`. Every metric is on the test fold; "
        "precision, recall and F1 are over labelled A records; coverage counts every test-fold A record."
    )
    return "\n".join(lines) + "\n"


def floor_table() -> str:
    s = _sensitivity()
    if not s:
        return "No review-floor sweep has been recorded.\n"
    lines = [
        "| method | review floor | queue (floor) | queue (ambiguity) | queue (total) | share of test A | recall with review |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in METHODS:
        v = s["methods"].get(m)
        if not v:
            continue
        sweep = v["review_floor_sweep"]
        shown = [p for p in sweep["points"] if p["floor"] in FLOORS_SHOWN]
        for p in shown:
            lines.append(
                f"| `{m}` | {p['floor']} | {p['queue_floor']:,} | {p['queue_ambiguity']:,} | {p['queue_total']:,} | "
                f"{p['queue_share_of_test_a']} | {p['recall_with_review']} |"
            )
        omitted = sweep["floors_omitted_at_or_above_accept_min"]
        if omitted and not shown:
            lines.append(
                f"| `{m}` | (every floor shown is at or above its accept threshold {sweep['accept_min']}; the queue is undefined there) | | | | | |"
            )
    lines.append("")
    lines.append(
        "Keys: `artifacts/review_sensitivity.json#methods.<method_version>.review_floor_sweep.points[i]` with "
        "`floor`, `queue_floor`, `queue_ambiguity`, `queue_total`, `queue_share_of_test_a`, `recall_with_review`; "
        "floors at or above the method's accept threshold are omitted (`floors_omitted_at_or_above_accept_min`). "
        "The auto-accept threshold stays at `accept_min`; only the floor moves."
    )
    return "\n".join(lines) + "\n"


BLOCKS = {
    (REPO_ROOT / "docs" / "FINDINGS.md", "results"): results_table,
    (REPO_ROOT / "docs" / "FINDINGS.md", "review_floor"): floor_table,
    (REPO_ROOT / "README.md", "results"): results_table,
}


def _replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!-- generated:{name} start -->\n).*?(<!-- generated:{name} end -->)", re.S
    )
    if not pattern.search(text):
        raise SystemExit(f"no generated:{name} block found")
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    stale = []
    for (path, name), render in BLOCKS.items():
        text = path.read_text(encoding="utf-8")
        new = _replace_block(text, name, render())
        if new != text:
            if a.check:
                stale.append(f"{path.relative_to(REPO_ROOT)}: generated:{name}")
            else:
                path.write_text(new, encoding="utf-8")
                print(f"rendered {path.relative_to(REPO_ROOT)} generated:{name}")
    if a.check:
        for s in stale:
            print("stale:", s)
        print(
            "FAIL: run scripts/render_findings.py"
            if stale
            else "ok: generated blocks match the artifacts"
        )
        return 1 if stale else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
