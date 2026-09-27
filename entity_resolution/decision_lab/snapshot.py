"""``artifacts/lab/snapshot.json``: the aggregate comparison the lab renders by default
(docs/DECISION_LAB.md section 4; schema ``lab_snapshot.schema.json``).

Every metric value is copied verbatim from a committed artifact and carries the key it was
read from (``artifacts/eval_rules_v1.json#metrics.at_auto_accept.precision``). Numerators and
denominators are the counts the artifact stores. The two counts the evaluation artifact does
not store, auto-accepts over every test A record and the reject count, are read from the
committed test-fold mapping exhibit (its ``tier`` column) and the test population; each is
asserted against the artifact's own ratio before it is written. Nothing else is computed.
"""

from __future__ import annotations

from typing import Any

from entity_resolution.config import METHOD_VERSIONS
from entity_resolution.decision_lab import LAB_CONTRACT_VERSION, contracts
from entity_resolution.decision_lab.sources import SCORE_KIND, Committed, FileRef
from entity_resolution.eval.review_cost import REVIEW_FLOORS

METRIC_DEFINITIONS: dict[str, dict[str, str]] = {
    "precision": {
        "display_name": "Precision",
        "definition": (
            "Among labelled test-fold A records the method auto-accepted, the share whose "
            "accepted B is in the A record's truth set."
        ),
        "numerator": "correct auto-accepts (labelled A records)",
        "denominator": "labelled auto-accepted A records",
        "scope": "labelled test-fold A records, auto_accept tier",
        "unit": "ratio",
        "kind": "accuracy",
    },
    "recall_labelled": {
        "display_name": "Recall (reachable truth)",
        "definition": (
            "Correct auto-accepts over labelled A records whose truth survived blocking. "
            "Unlinked is not non-match: nothing is known about unlabelled records."
        ),
        "numerator": "correct auto-accepts (labelled A records)",
        "denominator": "labelled A records with a truth pair among their candidates",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "accuracy",
    },
    "recall_overall": {
        "display_name": "Recall (blocking loss included)",
        "definition": (
            "Correct auto-accepts over all labelled A records; equals recall_labelled times "
            "pair_completeness_test."
        ),
        "numerator": "correct auto-accepts (labelled A records)",
        "denominator": "all labelled test-fold A records",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "accuracy",
    },
    "f1": {
        "display_name": "F1",
        "definition": (
            "Harmonic mean of precision and recall_labelled, computed from the six-decimal "
            "rounded values as the evaluator does. No numerator or denominator of its own."
        ),
        "numerator": "none (harmonic mean)",
        "denominator": "none (harmonic mean)",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "accuracy",
    },
    "coverage": {
        "display_name": "Coverage",
        "definition": (
            "Auto-accepted A records over every test-fold A record, labelled or not, "
            "including records with no candidate. A volume measure, not an accuracy measure."
        ),
        "numerator": "auto-accepted test-fold A records",
        "denominator": "all test-fold A records",
        "scope": "all test-fold A records",
        "unit": "ratio",
        "kind": "volume",
    },
    "pair_completeness_test": {
        "display_name": "Pair completeness (test fold)",
        "definition": (
            "Labelled test-fold A records whose truth survived blocking over all labelled "
            "test-fold A records: the ceiling blocking puts on recall for every method."
        ),
        "numerator": "labelled A records with a truth pair among their candidates",
        "denominator": "all labelled test-fold A records",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "upper_bound",
    },
    "unverified_accepts_share": {
        "display_name": "Unverified accepts (share)",
        "definition": (
            "Auto-accepts on unlabelled A records over all test-fold auto-accepts. Counted by "
            "coverage, invisible to precision and recall."
        ),
        "numerator": "auto-accepted unlabelled test-fold A records",
        "denominator": "all auto-accepted test-fold A records",
        "scope": "all test-fold A records",
        "unit": "share",
        "kind": "volume",
    },
    "precision_or_review": {
        "display_name": "Precision if every review resolves correctly",
        "definition": (
            "Upper bound: a review row counts as correct when any of its candidates is in the "
            "truth set. Over labelled records in auto_accept or review."
        ),
        "numerator": "correct auto-accepts plus queued labelled A records with reachable truth",
        "denominator": "labelled A records in auto_accept or review",
        "scope": "labelled test-fold A records, auto_accept and review tiers",
        "unit": "ratio",
        "kind": "upper_bound",
    },
    "recall_labelled_or_review": {
        "display_name": "Recall if every review resolves correctly",
        "definition": (
            "Upper bound: correct auto-accepts plus queued labelled records whose truth is "
            "among the candidates, over labelled records whose truth survived blocking."
        ),
        "numerator": "correct auto-accepts plus queued labelled A records with reachable truth",
        "denominator": "labelled A records with a truth pair among their candidates",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "upper_bound",
    },
    "f1_or_review": {
        "display_name": "F1 if every review resolves correctly",
        "definition": "Harmonic mean of precision_or_review and recall_labelled_or_review.",
        "numerator": "none (harmonic mean)",
        "denominator": "none (harmonic mean)",
        "scope": "labelled test-fold A records",
        "unit": "ratio",
        "kind": "upper_bound",
    },
    "review_queue": {
        "display_name": "Review queue",
        "definition": (
            "Test-fold A records in the review tier at the recorded policy: records queued by "
            "value plus records the ambiguity rule moved from auto_accept."
        ),
        "numerator": "test-fold A records in the review tier",
        "denominator": "none (count)",
        "scope": "all test-fold A records",
        "unit": "count",
        "kind": "workload",
    },
    "decisions_moved_to_review": {
        "display_name": "Demoted by the ambiguity rule",
        "definition": (
            "Test-fold A records at or above accept_min whose top-2 gap is below "
            "ambiguity_gap and which therefore sit in review instead of auto_accept."
        ),
        "numerator": "test-fold A records demoted from auto_accept to review",
        "denominator": "none (count)",
        "scope": "all test-fold A records",
        "unit": "count",
        "kind": "workload",
    },
    "unverified_accepts": {
        "display_name": "Unverified accepts",
        "definition": "Auto-accepts on unlabelled test-fold A records.",
        "numerator": "auto-accepted unlabelled test-fold A records",
        "denominator": "none (count)",
        "scope": "all test-fold A records",
        "unit": "count",
        "kind": "volume",
    },
    "pair_level_ece": {
        "display_name": "Pair-level ECE",
        "definition": (
            "Expected calibration error over every labelled test-fold candidate pair: ten "
            "equal-width probability bins, count-weighted mean absolute gap between the mean "
            "probability and the observed match rate. rules_v1 uses an uncalibrated score as "
            "its probability, exact_v1 a binary score; learned_v1 is calibrated at this level."
        ),
        "numerator": "none (count-weighted mean absolute gap)",
        "denominator": "none (count-weighted mean absolute gap)",
        "scope": "labelled test-fold candidate pairs",
        "unit": "ratio",
        "kind": "calibration",
    },
    "decision_level_ece": {
        "display_name": "Decision-level ECE",
        "definition": (
            "The same calibration error over the top candidate of each labelled test-fold A "
            "record. Different from the pair level by construction: choosing the maximum "
            "selects overconfident probabilities, so a pair-calibrated model is overconfident "
            "at decision level."
        ),
        "numerator": "none (count-weighted mean absolute gap)",
        "denominator": "none (count-weighted mean absolute gap)",
        "scope": "labelled test-fold A records, top candidate",
        "unit": "ratio",
        "kind": "calibration",
    },
    "pair_level_brier": {
        "display_name": "Pair-level Brier score",
        "definition": "Mean squared error of the probability against the pair label.",
        "numerator": "none (mean squared error)",
        "denominator": "none (mean squared error)",
        "scope": "labelled test-fold candidate pairs",
        "unit": "ratio",
        "kind": "calibration",
    },
    "decision_level_brier": {
        "display_name": "Decision-level Brier score",
        "definition": (
            "Mean squared error of the top candidate's probability against its correctness."
        ),
        "numerator": "none (mean squared error)",
        "denominator": "none (mean squared error)",
        "scope": "labelled test-fold A records, top candidate",
        "unit": "ratio",
        "kind": "calibration",
    },
}

CALIBRATION_NOTES: dict[str, str] = {
    "exact_v1": (
        "The score is 0 or 1 and is used as the probability, so ECE equals the Brier score and "
        "both measure how often an exact hit is wrong and a miss is right; not a calibrated "
        "probability."
    ),
    "rules_v1": (
        "The raw weighted score is used as the probability without calibration; the pair-level "
        "error shows what an uncalibrated score looks like and is not comparable with a "
        "calibrated probability."
    ),
    "learned_v1": (
        "Isotonic calibration was fitted on calibrate-fold pairs, so the pair-level error is "
        "small; the decision level (top candidate per A record) is overconfident because the "
        "maximum of several probabilities is selected."
    ),
}


def _metric(
    value: Any,
    numerator: int | None,
    denominator: int | None,
    source_key: str,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "source_key": source_key,
        "unavailable_reason": unavailable_reason,
    }


def _count(value: int | None, source_key: str) -> dict[str, Any]:
    return {"value": value, "source_key": source_key}


def _fileref(ref: FileRef, code_commit: str, generated_at_utc: str) -> dict[str, Any]:
    return {
        "path": ref.relpath,
        "sha256": ref.sha256,
        "code_commit": code_commit,
        "generated_at_utc": generated_at_utc,
    }


def evidence_block(c: Committed) -> dict[str, Any]:
    e = c.evals[METHOD_VERSIONS[0]]
    return {
        "run_id": c.run_id,
        "evaluation_code_commit": e["input"]["code_commit"],
        "feature_version": e["input"]["feature_version"],
        "manifest_sha256_at_evaluation": c.manifest["manifest_sha256_at_evaluation"],
        "evaluation_generated_at_utc": e["generated_at_utc"],
        "artifact_version": e["artifact_version"],
        "sensitivity_version": c.sensitivity["sensitivity_version"],
        "lab_contract_version": LAB_CONTRACT_VERSION,
    }


def population_block(c: Committed) -> dict[str, Any]:
    m0 = METHOD_VERSIONS[0]
    return {
        "fold": "test",
        "grain": "a_record",
        "a_records": int(c.split["folds"]["test"]["a_records"]),
        "labelled_a": int(c.split["folds"]["test"]["labelled_a_records"]),
        "labelled_a_reachable": int(c.evals[m0]["metrics"]["labelled_a_reachable"]),
        "source_keys": [
            "artifacts/split.json#folds.test.a_records",
            "artifacts/split.json#folds.test.labelled_a_records",
            f"artifacts/eval_{m0}.json#metrics.labelled_a_reachable",
            *(f"artifacts/eval_{m}.json#metrics.test_a" for m in METHOD_VERSIONS),
            *(f"artifacts/eval_{m}.json#metrics.labelled_a" for m in METHOD_VERSIONS),
        ],
    }


def _method_block(c: Committed, m: str) -> dict[str, Any]:
    e = c.evals[m]
    met = e["metrics"]
    rec = c.methods[m]
    sens = c.sensitivity["methods"][m]
    ex = c.exhibits[m]
    ek = f"artifacts/eval_{m}.json#metrics"
    rk = f"artifacts/methods/{m}.json"
    sk = f"artifacts/review_sensitivity.json#methods.{m}"
    xk = f"{ex.relpath}"
    acc, either = met["at_auto_accept"], met["at_auto_accept_or_review"]
    test_a, lab, reach = met["test_a"], met["labelled_a"], met["labelled_a_reachable"]
    accepted_all = ex.tier_count("auto_accept")
    review_all = ex.tier_count("review")
    exhibit_rows = len(ex.rows)
    if abs(accepted_all / test_a - met["coverage"]) >= 1e-6:
        raise contracts.ContractError(
            f"{m}: {accepted_all} auto_accept exhibit rows / {test_a} != coverage {met['coverage']}"
        )
    if accepted_all / test_a != met["tier_shares"]["auto_accept"]:
        raise contracts.ContractError(f"{m}: exhibit auto_accept rows disagree with tier_shares")
    if review_all != met["ambiguity_rule"]["review_queue"]:
        raise contracts.ContractError(f"{m}: exhibit review rows disagree with review_queue")
    if review_all / test_a != met["tier_shares"]["review"]:
        raise contracts.ContractError(f"{m}: exhibit review rows disagree with tier_shares")
    reject_all = test_a - exhibit_rows
    if reject_all / test_a != met["tier_shares"]["reject"]:
        raise contracts.ContractError(f"{m}: test_a minus exhibit rows disagrees with tier_shares")
    unverified = met["unverified_accepts"]["count"]
    if met["unverified_accepts"]["share_of_accepts"] != round(unverified / accepted_all, 6):
        raise contracts.ContractError(f"{m}: unverified share does not recompute from its counts")
    cal = met["calibration"]
    floor = sens["review_floor_sweep"]
    metrics = {
        "precision": _metric(
            acc["precision"], acc["correct"], acc["accepted"], f"{ek}.at_auto_accept.precision"
        ),
        "recall_labelled": _metric(
            acc["recall_labelled"], acc["correct"], reach, f"{ek}.at_auto_accept.recall_labelled"
        ),
        "recall_overall": _metric(
            met["recall_overall"], acc["correct"], lab, f"{ek}.recall_overall"
        ),
        "f1": _metric(acc["f1"], None, None, f"{ek}.at_auto_accept.f1"),
        "coverage": _metric(met["coverage"], accepted_all, test_a, f"{ek}.coverage"),
        "pair_completeness_test": _metric(
            met["pair_completeness_test"], reach, lab, f"{ek}.pair_completeness_test"
        ),
        "unverified_accepts_share": _metric(
            met["unverified_accepts"]["share_of_accepts"],
            unverified,
            accepted_all,
            f"{ek}.unverified_accepts.share_of_accepts",
        ),
        "precision_or_review": _metric(
            either["precision"],
            either["correct"],
            either["accepted"],
            f"{ek}.at_auto_accept_or_review.precision",
        ),
        "recall_labelled_or_review": _metric(
            either["recall_labelled"],
            either["correct"],
            reach,
            f"{ek}.at_auto_accept_or_review.recall_labelled",
        ),
        "f1_or_review": _metric(either["f1"], None, None, f"{ek}.at_auto_accept_or_review.f1"),
    }
    counts = {
        "test_a": _count(test_a, f"{ek}.test_a"),
        "labelled_a": _count(lab, f"{ek}.labelled_a"),
        "labelled_a_reachable": _count(reach, f"{ek}.labelled_a_reachable"),
        "accepted_labelled": _count(acc["accepted"], f"{ek}.at_auto_accept.accepted"),
        "correct_labelled": _count(acc["correct"], f"{ek}.at_auto_accept.correct"),
        "accepted_or_review_labelled": _count(
            either["accepted"], f"{ek}.at_auto_accept_or_review.accepted"
        ),
        "correct_or_review_labelled": _count(
            either["correct"], f"{ek}.at_auto_accept_or_review.correct"
        ),
        "accepted_all": _count(accepted_all, f"{xk}#tier=auto_accept rows"),
        "unverified_accepts": _count(unverified, f"{ek}.unverified_accepts.count"),
        "review_queue": _count(
            met["ambiguity_rule"]["review_queue"], f"{ek}.ambiguity_rule.review_queue"
        ),
        "decisions_moved_to_review": _count(
            met["ambiguity_rule"]["decisions_moved_to_review"],
            f"{ek}.ambiguity_rule.decisions_moved_to_review",
        ),
        "tier_auto_accept": _count(accepted_all, f"{xk}#tier=auto_accept rows"),
        "tier_review": _count(review_all, f"{xk}#tier=review rows"),
        "tier_reject": _count(reject_all, f"{ek}.test_a - {xk}#rows"),
        "exhibit_rows": _count(exhibit_rows, f"{xk}#rows"),
    }
    calibration = {
        "pair_level_ece": _metric(
            cal["pair_level"]["ece"], None, None, f"{ek}.calibration.pair_level.ece"
        ),
        "decision_level_ece": _metric(
            cal["decision_level"]["ece"], None, None, f"{ek}.calibration.decision_level.ece"
        ),
        "pair_level_brier": _metric(
            cal["pair_level"]["brier"], None, None, f"{ek}.calibration.pair_level.brier"
        ),
        "decision_level_brier": _metric(
            cal["decision_level"]["brier"], None, None, f"{ek}.calibration.decision_level.brier"
        ),
        "note": CALIBRATION_NOTES[m],
    }
    policy = c.policy_of(m)
    review_floor = {
        "accept_min": float(floor["accept_min"]),
        "status": "supported_exact_at_native_accept",
        "note": (
            "Only the review floor moves; accept_min and ambiguity_gap stay at the method's "
            "recorded values. Every point is copied from the sensitivity artifact and was "
            "computed at the native accept threshold, so only these exported floor values are "
            "supported; any other floor is a replay, not a snapshot figure."
        ),
        "points": [dict(p) for p in floor["points"]],
        "floors_omitted_at_or_above_accept_min": list(
            floor["floors_omitted_at_or_above_accept_min"]
        ),
        "source_key": f"{sk}.review_floor_sweep.points",
    }
    if [p["floor"] for p in floor["points"]] != [
        f for f in REVIEW_FLOORS if f < policy["accept_min"]
    ]:
        raise contracts.ContractError(f"{m}: review floor points are not the expected floors")
    legacy = {
        "status": "legacy_snapshot_calculation",
        "note": (
            "The accept-threshold sweep of the snapshot reused the ambiguity-demotion flag "
            "computed at the recorded accept threshold at every swept threshold. For thresholds "
            "below the recorded accept_min it can accept records whose top-2 gap is below "
            "ambiguity_gap; a faithful replay keeps them in review. Not an arbitrary-policy "
            "replay: see legacy_sweep_divergence in the replay bundle metadata."
        ),
        "review_min": float(sens["review_min"]),
        "chosen_accept_threshold": float(sens["chosen_accept_threshold"]),
        "false_accept_cost_ratios": [float(r) for r in sens["false_accept_cost_ratios"]],
        "points": [dict(p) for p in sens["points"]],
        "source_key": f"{sk}.points",
    }
    return {
        "method_version": m,
        "definition": rec["definition"],
        "score_kind": SCORE_KIND[m],
        "fitted_on": rec["fitted_on"],
        "policy": policy,
        "policy_source": f"{rk}#tier_policy",
        "metrics": metrics,
        "counts": counts,
        "calibration": calibration,
        "review_floor": review_floor,
        "legacy_threshold_sweep": legacy,
        "mapping_exhibit": {
            "path": ex.relpath,
            "sha256": ex.sha256,
            "rows": exhibit_rows,
            "note": (
                "Test-fold decisions in the auto_accept and review tiers only; scores, "
                "probabilities and top-2 gaps rounded to six decimals; reject-tier and "
                "no-candidate A records are absent. Identifiers, numbers and tiers only."
            ),
        },
    }


def build(c: Committed) -> dict[str, Any]:
    snapshot = {
        "lab_snapshot_version": "1.0",
        "snapshot_id": c.snapshot_id,
        "evidence": evidence_block(c),
        "population": population_block(c),
        "metric_definitions": dict(METRIC_DEFINITIONS),
        "methods": {m: _method_block(c, m) for m in METHOD_VERSIONS},
        "provenance": {
            "eval_artifacts": {
                m: _fileref(
                    c.eval_refs[m],
                    c.evals[m]["input"]["code_commit"],
                    c.evals[m]["generated_at_utc"],
                )
                for m in METHOD_VERSIONS
            },
            "method_records": {
                m: _fileref(
                    c.method_refs[m], c.methods[m]["code_commit"], c.methods[m]["created_at_utc"]
                )
                for m in METHOD_VERSIONS
            },
            "review_sensitivity": _fileref(
                c.sensitivity_ref, c.sensitivity["code_commit"], c.sensitivity["generated_at_utc"]
            ),
            "split": _fileref(c.split_ref, c.split["code_commit"], c.split["generated_at_utc"]),
            "note": (
                "Every value above is copied from the committed artifact named by its "
                "source_key; counts read from a mapping exhibit are asserted against the "
                "artifact's own ratio before writing. No curated case contributes to any figure."
            ),
        },
    }
    contracts.validate(snapshot, "lab_snapshot")
    contracts.assert_no_forbidden_keys(snapshot, "snapshot.json")
    return snapshot
