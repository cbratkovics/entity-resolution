"""Canonical policy fixtures shared by the Python and TypeScript evaluators.

``python -m entity_resolution.decision_lab.fixtures`` writes
``apps/decision-lab/fixtures/policy_fixtures.json``; ``tests/test_lab_policy.py`` asserts the file
equals a fresh render (stale detection) and that :mod:`policy` reproduces every expectation;
the Vitest suite asserts ``policy.ts`` does the same. Every expected value is produced by the
Python evaluator, so the two implementations are tested against one oracle, not against each
other's opinions. Numbers are serialised with ``repr`` (shortest round-trip), so JavaScript
parses the identical IEEE double.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from entity_resolution.config import REPO_ROOT
from entity_resolution.decision_lab.policy import (
    Policy,
    PolicyError,
    ReplayRow,
    accept_sweep,
    decide_row,
    evaluate,
    floor_sweep,
    legacy_accept_sweep,
    rank_candidates,
)

FIXTURES_PATH = REPO_ROOT / "apps" / "decision-lab" / "fixtures" / "policy_fixtures.json"
FIXTURES_VERSION = "1.0"

NATIVE = {"accept_min": 0.95, "review_min": 0.50, "ambiguity_gap": 0.10}


def _row(v1, v2, n, labelled, correct, reach) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "v1": v1,
        "v2": v2,
        "n_candidates": n,
        "labelled": labelled,
        "top1_correct": correct,
        "truth_reachable": reach,
    }


def _rows(spec: list[dict[str, Any]]) -> list[ReplayRow]:
    return [ReplayRow(**r) for r in spec]


CASES: list[dict[str, Any]] = [
    {
        "id": "regression_ambiguity_flag_reuse",
        "description": (
            "Mandatory regression: top scores 0.80 and 0.76 (gap 0.04). At accept 0.95 the record "
            "is in review by value and the baseline demotion flag is false. Lowering accept to "
            "0.75 must still give review because the gap is below 0.10; reusing the old flag "
            "would accept it."
        ),
        "policy": {"accept_min": 0.75, "review_min": 0.50, "ambiguity_gap": 0.10},
        "baseline_policy": NATIVE,
        "rows": [_row(0.80, 0.76, 2, True, True, True)],
        "legacy_thresholds": [0.75, 0.95],
        "corrected_thresholds": [0.75, 0.95],
    },
    {
        "id": "boundaries_accept_review_gap",
        "description": (
            "Values immediately below, at and above accept_min and review_min; gaps immediately "
            "below, at and above ambiguity_gap. Inclusive lower bounds; strict gap comparison. "
            "The pair (0.99, 0.89) shows that a decimal gap of 0.10 is 0.0999... as a double and "
            "is therefore ambiguous; exact_gap_boundary tests a representable gap."
        ),
        "policy": NATIVE,
        "rows": [
            _row(0.95, 0.50, 2, True, True, True),  # at accept -> auto_accept
            _row(0.9499999999999999, 0.50, 2, True, True, True),  # just below accept -> review
            _row(0.9500000000000001, 0.50, 2, True, False, True),  # just above -> accept (wrong)
            _row(0.50, 0.10, 2, True, True, True),  # at review -> review
            _row(0.49999999999999994, 0.10, 2, True, True, True),  # below review -> reject
            _row(
                0.99, 0.89, 2, True, True, True
            ),  # decimal gap 0.10 is 0.0999... in binary: ambiguous
            _row(0.99, 0.8900000000000001, 2, True, True, True),  # gap just under -> ambiguous
            _row(
                0.99, 0.8899999999999999, 2, True, True, True
            ),  # gap 0.10000000000000009 -> accept
            _row(0.60, 0.55, 2, True, True, True),  # review by value and ambiguous, not demoted
            _row(0.40, 0.39, 2, True, True, True),  # reject: ambiguity never lifts a reject
        ],
    },
    {
        "id": "exact_gap_boundary",
        "description": (
            "With ambiguity_gap 0.25 the gap 1.0 - 0.75 is exactly representable: equal to the "
            "threshold is not ambiguous (strict <); one ulp under is; one ulp over is not."
        ),
        "policy": {"accept_min": 0.95, "review_min": 0.50, "ambiguity_gap": 0.25},
        "rows": [
            _row(1.0, 0.75, 2, True, True, True),
            _row(1.0, 0.7500000000000001, 2, True, True, True),
            _row(1.0, 0.7499999999999999, 2, True, True, True),
        ],
    },
    {
        "id": "single_candidate_and_no_candidate",
        "description": (
            "A single candidate has a null gap, never zero or a perfect gap, so it is never "
            "ambiguous; a no-candidate A record is reject with reason no_candidate and stays in "
            "the population. An unlabelled accept is an unverified accept."
        ),
        "policy": NATIVE,
        "rows": [
            _row(0.99, None, 1, True, True, True),
            _row(0.99, None, 1, False, None, None),
            _row(None, None, 0, True, None, False),
            _row(None, None, 0, False, None, None),
            _row(0.70, None, 1, True, False, True),
        ],
    },
    {
        "id": "ties_and_lexical_order",
        "description": (
            "A tie on value gives gap zero, which is ambiguous under any positive gap threshold; "
            "the chosen candidate is the lexically smallest B id ('10' before '9')."
        ),
        "policy": NATIVE,
        "rows": [_row(1.0, 1.0, 2, True, False, True), _row(1.0, 1.0, 3, True, True, True)],
    },
    {
        "id": "zero_denominators",
        "description": (
            "No labelled record and nothing accepted: precision, recall and F1 are unavailable "
            "(null), never perfect or zero by default; coverage still counts."
        ),
        "policy": NATIVE,
        "rows": [_row(0.30, 0.20, 2, False, None, None), _row(None, None, 0, False, None, None)],
    },
    {
        "id": "blocking_loss_denominators",
        "description": (
            "recall_labelled divides by labelled records whose truth survived blocking; "
            "recall_overall by all labelled records; their ratio is pair_completeness_test. A "
            "labelled record whose truth is unreachable can still be accepted (wrongly) or "
            "queued; queued unreachable rows do not count toward recall with review."
        ),
        "policy": NATIVE,
        "rows": [
            _row(0.99, 0.10, 2, True, True, True),
            _row(0.99, 0.10, 2, True, False, False),  # truth lost in blocking, wrong accept
            _row(0.80, 0.10, 2, True, False, False),  # queued, unreachable
            _row(0.80, 0.10, 2, True, False, True),  # queued, reachable -> counts in upper bound
            _row(0.20, 0.10, 2, True, False, True),  # rejected, reachable
        ],
        "floors": [0.05, 0.5, 0.9, 0.95],
        "floor_accept_min": 0.95,
    },
    {
        "id": "rules_native_shape",
        "description": (
            "The rules_v1 policy shape (accept 0.65, review 0.0757, gap 0.10) over an "
            "uncalibrated score in [0, 1]; nothing about these rows is from the real snapshot."
        ),
        "policy": {"accept_min": 0.65, "review_min": 0.0756756772994995, "ambiguity_gap": 0.10},
        "rows": [
            _row(1.0, 0.9, 35, True, True, True),  # gap 0.0999... -> ambiguous (rounded shows 0.1)
            _row(0.65, 0.1, 4, False, None, None),
            _row(0.0756756772994995, None, 1, True, False, True),
            _row(0.07, None, 1, True, False, True),
        ],
    },
]

INVALID_POLICIES: list[dict[str, Any]] = [
    {
        "id": "review_above_accept",
        "policy": {"accept_min": 0.5, "review_min": 0.6, "ambiguity_gap": 0.1},
    },
    {
        "id": "accept_above_one",
        "policy": {"accept_min": 1.5, "review_min": 0.5, "ambiguity_gap": 0.1},
    },
    {
        "id": "negative_review",
        "policy": {"accept_min": 0.9, "review_min": -0.1, "ambiguity_gap": 0.1},
    },
    {"id": "nan_accept", "policy": {"accept_min": "NaN", "review_min": 0.5, "ambiguity_gap": 0.1}},
    {
        "id": "inf_gap",
        "policy": {"accept_min": 0.9, "review_min": 0.5, "ambiguity_gap": "Infinity"},
    },
    {"id": "gap_above_one", "policy": {"accept_min": 0.9, "review_min": 0.5, "ambiguity_gap": 1.5}},
    {
        "id": "string_accept",
        "policy": {"accept_min": "0.9", "review_min": 0.5, "ambiguity_gap": 0.1},
    },
]

RANK_CASES: list[dict[str, Any]] = [
    {
        "id": "lexical_tie",
        "candidates": [["9", 1.0], ["10", 1.0], ["2", 0.5]],
        "expected_order": ["10", "9", "2"],
    },
    {
        "id": "value_first",
        "candidates": [["1", 0.2], ["2", 0.9], ["3", 0.5]],
        "expected_order": ["2", "3", "1"],
    },
    {
        "id": "all_tied",
        "candidates": [["b", 0.7], ["a", 0.7], ["c", 0.7]],
        "expected_order": ["a", "b", "c"],
    },
]


def _json_policy(p: dict[str, Any]) -> Policy:
    return Policy(**p)


def render() -> dict[str, Any]:
    out_cases = []
    for c in CASES:
        rows = _rows(c["rows"])
        policy = _json_policy(c["policy"])
        entry: dict[str, Any] = {
            "id": c["id"],
            "description": c["description"],
            "policy": policy.as_dict(),
            "rows": c["rows"],
            "expected_decisions": [dataclasses.asdict(decide_row(r, policy)) for r in rows],
            "expected_metrics": evaluate(rows, policy),
        }
        if "baseline_policy" in c:
            base = _json_policy(c["baseline_policy"])
            entry["baseline_policy"] = base.as_dict()
            entry["expected_baseline_decisions"] = [
                dataclasses.asdict(decide_row(r, base)) for r in rows
            ]
            entry["expected_legacy_sweep"] = legacy_accept_sweep(
                rows, baseline=base, thresholds=c["legacy_thresholds"]
            )
            entry["expected_corrected_sweep"] = accept_sweep(
                rows,
                review_min=base.review_min,
                ambiguity_gap=base.ambiguity_gap,
                thresholds=c["corrected_thresholds"],
            )
        if "floors" in c:
            entry["floors"] = c["floors"]
            entry["floor_accept_min"] = c["floor_accept_min"]
            entry["expected_floor_sweep"] = floor_sweep(
                rows,
                accept_min=c["floor_accept_min"],
                ambiguity_gap=policy.ambiguity_gap,
                floors=c["floors"],
            )
        out_cases.append(entry)
    invalid = []
    for p in INVALID_POLICIES:
        raw = dict(p["policy"])
        try:
            _json_policy(
                {
                    k: (float(v) if isinstance(v, str) and v in ("NaN", "Infinity") else v)
                    for k, v in raw.items()
                }
            )
            raise AssertionError(f"{p['id']} should be invalid")
        except PolicyError:
            pass
        invalid.append({"id": p["id"], "policy": raw, "error": True})
    ranks = []
    for r in RANK_CASES:
        ranked = rank_candidates([(b, float(v)) for b, v in r["candidates"]])
        assert [b for b, _ in ranked] == r["expected_order"], r["id"]
        ranks.append(r)
    return {
        "fixtures_version": FIXTURES_VERSION,
        "generated_by": "entity_resolution.decision_lab.fixtures",
        "note": (
            "Synthetic rows; every expected value comes from entity_resolution.decision_lab.policy. "
            "Strings 'NaN' and 'Infinity' in invalid policies stand for the non-finite doubles."
        ),
        "cases": out_cases,
        "invalid_policies": invalid,
        "rank_cases": ranks,
    }


def dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n"


def write(path: Path = FIXTURES_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(render()), encoding="utf-8")
    return path


def check(path: Path = FIXTURES_PATH) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == dumps(render())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--check"]:
        ok = check()
        print(("ok" if ok else "STALE") + f": {FIXTURES_PATH.relative_to(REPO_ROOT)}")
        return 0 if ok else 1
    print(f"wrote {write().relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
