"""``artifacts/lab/cases.json`` and ``case_selection.json``: a curated exhibit of test-fold A
records with the evidence each method exported for them (docs/DECISION_LAB.md section 6;
schema ``lab_cases.schema.json``).

Selection is deterministic: each criterion scans the A ids that qualify in ascending order and
takes the first ``cap`` of them; a case carries every reason code it qualifies for, whichever
criterion selected it, so the exhibit never hides a property of a record it shows. The
committed-exhibit criteria read only the three mapping exhibits and the FINDINGS narrative;
the local-evidence criteria and the ``labels`` block need the owner-run local stage
(hash-verified ``data/`` inputs) and are absent otherwise. It is a curated exhibit, not a
representative sample: no figure in the lab is computed from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from entity_resolution.config import METHOD_VERSIONS
from entity_resolution.decision_lab import contracts
from entity_resolution.decision_lab.policy import ReplayRow
from entity_resolution.decision_lab.replay import LocalInputs, MethodReplay
from entity_resolution.decision_lab.sources import SCORE_KIND, Committed, ExhibitRow
from entity_resolution.models import registry

STRATEGY_VERSION = "1.0"
NARRATIVE_SOURCE = "docs/FINDINGS.md#worked-examples-from-the-review-tier"

WORKED_EXAMPLES: dict[str, str] = {
    "03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2": (
        "learned_v1 scores two Discogs masters, 683263 and 82406, at the same calibrated "
        "probability; the truth link is to 82406. Discogs holds two masters that are the same "
        "work after normalisation, the top-2 gap is zero, and the ambiguity rule sends the "
        "record to review instead of auto-accepting the wrong one. All three methods tie here."
    ),
    "ac8ca6a0-b24b-314c-ba05-c6b22c564ac9": (
        "rules_v1 gives masters 120663 and 82443 the same score; the truth link is to 82443. "
        "A tie the rule cannot break is a review, not an accept. exact_v1 and learned_v1 accept "
        "82443: a genuine disagreement between methods, not ambiguity within one method."
    ),
    "41cb566c-8384-4a00-b944-e72280c673df": (
        "learned_v1 puts master 1214912 (a subtitle on one side) in the review tier and it is "
        "the truth link; a reviewer confirms it in one look. exact_v1 exports nothing for this "
        "record; rules_v1 reviews it at an exported gap of exactly 0.1, which the six-decimal "
        "exhibit cannot classify against the 0.10 threshold."
    ),
}


@dataclass(frozen=True)
class Criterion:
    reason_code: str
    description: str
    cap: int
    source: str
    deterministic_order: str = "ascending a_id"


COMMITTED_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "worked_example",
        "The release groups discussed in docs/FINDINGS.md; narrative copied from there.",
        3,
        "findings_narrative",
        "order of docs/FINDINGS.md",
    ),
    Criterion(
        "agreement_all_accept",
        "All three methods exported the same B in the auto_accept tier.",
        6,
        "committed_exhibits",
    ),
    Criterion(
        "method_disagreement",
        "At least two methods exported this record and chose different B ids.",
        8,
        "committed_exhibits",
    ),
    Criterion(
        "ambiguity_tie",
        "Some exported method has a top-2 gap of exactly 0.0 and the review tier.",
        6,
        "committed_exhibits",
    ),
    Criterion(
        "ambiguity_demoted",
        (
            "Some exported method has the review tier, a probability at or above its accept_min "
            "and a rounded top-2 gap strictly between 0 and ambiguity_gap: demoted by the "
            "ambiguity rule."
        ),
        6,
        "committed_exhibits",
    ),
    Criterion(
        "gap_at_rounded_boundary",
        (
            "Some exported method has the review tier and a six-decimal gap equal to "
            "ambiguity_gap; the exhibit alone cannot say whether the unrounded gap is below it."
        ),
        4,
        "committed_exhibits",
    ),
    Criterion(
        "single_candidate",
        "Some exported method has a null top-2 gap: the record had one blocked candidate.",
        5,
        "committed_exhibits",
    ),
    Criterion(
        "partial_export",
        "Exported by one or two methods only; the others rejected it or had no candidate.",
        5,
        "committed_exhibits",
    ),
)

LOCAL_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "unverified_accept",
        "Auto-accepted by some method and unlabelled: counted by coverage, invisible to precision.",
        5,
        "local_evidence",
    ),
    Criterion(
        "verified_wrong_accept",
        "Labelled and auto-accepted by some method with a chosen B outside the truth set.",
        5,
        "local_evidence",
    ),
    Criterion(
        "no_candidate",
        "A test-fold A record with no blocked candidate: reject for every method, absent from every exhibit.",
        4,
        "local_evidence",
    ),
    Criterion(
        "reject_all_methods",
        "A test-fold A record with candidates that every method rejected: absent from every exhibit.",
        3,
        "local_evidence",
    ),
)

ALL_CRITERIA = COMMITTED_CRITERIA + LOCAL_CRITERIA
LOCAL_ONLY_CODES = frozenset(cr.reason_code for cr in LOCAL_CRITERIA)


@dataclass
class LocalEvidence:
    """The owner-run local stage: verified truth, full candidate counts and the unrounded
    replays of the two rule methods."""

    local: LocalInputs
    replays: dict[str, MethodReplay]
    code_commit: str = field(default_factory=registry.code_commit)
    _index: dict[str, dict[str, tuple[str | None, ReplayRow]]] = field(
        default_factory=dict, repr=False
    )

    @property
    def verifier(self) -> str:
        return f"entity_resolution.decision_lab.local_evidence@{self.code_commit}"

    def replay_row(self, method_version: str, a_id: str) -> tuple[str | None, ReplayRow] | None:
        """``(chosen_b, row)`` of the method's replay for ``a_id``; ``None`` without a replay."""
        rep = self.replays.get(method_version)
        if rep is None:
            return None
        if method_version not in self._index:
            self._index[method_version] = rep.by_a_id()
        return self._index[method_version][a_id]


# ---- evidence rows -------------------------------------------------------------------------


def exported_row(r: ExhibitRow, policy: dict[str, float], source: str) -> dict[str, Any]:
    gap = r.top2_gap
    if gap is None:
        derived = None
    else:
        derived = (
            r.tier == "review"
            and r.probability >= policy["accept_min"]
            and gap < policy["ambiguity_gap"]
        )
    return {
        "method_version": source.split("mapping_")[-1].split(".test")[0],
        "exported": True,
        "b_id": r.b_id,
        "score": r.score,
        "probability": r.probability,
        "tier": r.tier,
        "top2_gap": gap,
        "gap_state": "single_candidate" if gap is None else "exported",
        "block_keys": list(r.block_keys),
        "ambiguity_demoted_derived": derived,
        "gap_at_rounded_boundary": gap is not None and gap == round(policy["ambiguity_gap"], 6),
        "run_id": r.run_id,
        "decided_at_utc": r.decided_at_utc,
        "source": source,
    }


def not_exported_row(method_version: str, reason: str, source: str) -> dict[str, Any]:
    return {
        "method_version": method_version,
        "exported": False,
        "state": "not_exported",
        "reason": reason,
        "source": source,
    }


def evidence_rows(c: Committed, a_id: str, local: LocalEvidence | None) -> list[dict[str, Any]]:
    rows = []
    for m in METHOD_VERSIONS:
        ex = c.exhibits[m]
        source = ex.relpath
        r = ex.rows.get(a_id)
        if r is not None:
            rows.append(exported_row(r, c.policy_of(m), source))
        elif local is None:
            rows.append(not_exported_row(m, "reject_or_no_candidate", source))
        else:
            n = local.local.candidate_counts.get(a_id, 0)
            rows.append(not_exported_row(m, "no_candidate" if n == 0 else "rejected", source))
    return rows


def comparison_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exported = [r for r in rows if r["exported"]]
    b_ids = sorted({r["b_id"] for r in exported})
    n = len(exported)
    if n == 0:
        cls = "none_exported"
        note = "No method exported this record: rejected by every method or no blocked candidate."
    elif n == 1:
        cls = "single_method_exported"
        note = (
            f"Only {exported[0]['method_version']} exported this record; agreement between "
            "methods cannot be assessed from one exported row."
        )
    elif len(b_ids) == 1:
        cls = "all_exported_agree"
        tiers = sorted({r["tier"] for r in exported})
        note = (
            f"The {n} exporting methods chose the same B ({b_ids[0]}); tiers {', '.join(tiers)}. "
            "Agreement on the B id says nothing about within-method ambiguity: see each row's "
            "top2_gap and tier."
        )
    else:
        cls = "methods_disagree"
        note = (
            f"The {n} exporting methods chose {len(b_ids)} different B ids: a disagreement "
            "between methods, distinct from the within-method ambiguity the gap rule measures."
        )
    return {
        "methods_exported": n,
        "distinct_chosen_b_ids": len(b_ids),
        "agreement_class": cls,
        "note": note,
    }


def labels_block(
    c: Committed, a_id: str, rows: list[dict[str, Any]], local: LocalEvidence | None
) -> dict[str, Any]:
    if local is None:
        return {
            "state": "truth_unavailable",
            "note": (
                "Labels, full candidate counts and unrounded gaps come from the owner-run local "
                "evidence stage over the hash-verified data/ inputs; this export did not run it."
            ),
        }
    truth = local.local.truth_sets.get(a_id)
    labelled = truth is not None
    truth_b_ids = sorted(truth) if labelled else []
    n_full = local.local.candidate_counts.get(a_id, 0)
    chosen = {r["method_version"]: r["b_id"] for r in rows if r["exported"]}
    per_method: dict[str, Any] = {}
    reachable: bool | None = None
    for m in METHOD_VERSIONS:
        b = chosen.get(m)
        correct = (b in truth) if (labelled and b is not None) else None
        found = local.replay_row(m, a_id)
        if found is not None:
            _, rrow = found
            gap = None if rrow.v2 is None else rrow.v1 - rrow.v2
            if labelled:
                reachable = bool(rrow.truth_reachable) if reachable is None else reachable
            per_method[m] = {
                "chosen_correct": correct,
                "unrounded_gap": gap,
                "unrounded_ambiguous": None
                if gap is None
                else gap < c.policy_of(m)["ambiguity_gap"],
            }
        else:
            per_method[m] = {
                "chosen_correct": correct,
                "unrounded_gap": None,
                "unrounded_ambiguous": None,
                "note": "no unrounded learned scores exist",
            }
    if labelled and reachable is None:
        # no replay carried it (should not happen); compute from the candidate pairs
        feats = local.local.features_test
        cand_b = set(feats.loc[feats["a_id"] == a_id, "b_id"].tolist())
        reachable = bool(cand_b & truth)
    return {
        "state": "verified_local",
        "labelled": labelled,
        "truth_b_ids": truth_b_ids,
        "n_candidates_full": n_full,
        "truth_reachable_full": reachable if labelled else None,
        "truth_visible_in_exported_choices": (
            bool(set(chosen.values()) & truth) if labelled else None
        ),
        "per_method": per_method,
        "verifier": local.verifier,
    }


# ---- criteria --------------------------------------------------------------------------------


def committed_tags(c: Committed, a_id: str) -> set[str]:
    """Every committed-exhibit reason code the record qualifies for."""
    exported = {m: c.exhibits[m].rows[a_id] for m in METHOD_VERSIONS if a_id in c.exhibits[m].rows}
    tags: set[str] = set()
    if a_id in WORKED_EXAMPLES:
        tags.add("worked_example")
    if not exported:
        return tags
    b_ids = {r.b_id for r in exported.values()}
    if (
        len(exported) == 3
        and len(b_ids) == 1
        and all(r.tier == "auto_accept" for r in exported.values())
    ):
        tags.add("agreement_all_accept")
    if len(exported) >= 2 and len(b_ids) > 1:
        tags.add("method_disagreement")
    for m, r in exported.items():
        pol = c.policy_of(m)
        gap = r.top2_gap
        if gap is None:
            tags.add("single_candidate")
            continue
        if r.tier != "review":
            continue
        if gap == 0.0:
            tags.add("ambiguity_tie")
        if r.probability >= pol["accept_min"] and 0.0 < gap < pol["ambiguity_gap"]:
            tags.add("ambiguity_demoted")
        if gap == round(pol["ambiguity_gap"], 6):
            tags.add("gap_at_rounded_boundary")
    if 1 <= len(exported) <= 2:
        tags.add("partial_export")
    return tags


def local_tags(c: Committed, a_id: str, local: LocalEvidence) -> set[str]:
    tags: set[str] = set()
    truth = local.local.truth_sets.get(a_id)
    exported = {m: c.exhibits[m].rows[a_id] for m in METHOD_VERSIONS if a_id in c.exhibits[m].rows}
    accepts = [r for r in exported.values() if r.tier == "auto_accept"]
    if accepts and truth is None:
        tags.add("unverified_accept")
    if accepts and truth is not None and any(r.b_id not in truth for r in accepts):
        tags.add("verified_wrong_accept")
    if not exported:
        n = local.local.candidate_counts.get(a_id, 0)
        tags.add("no_candidate" if n == 0 else "reject_all_methods")
    return tags


def _universe(c: Committed, local: LocalEvidence | None) -> list[str]:
    ids: set[str] = set()
    for m in METHOD_VERSIONS:
        ids.update(c.exhibits[m].rows)
    ids.update(WORKED_EXAMPLES)
    if local is not None:
        ids.update(local.local.test_a_ids)
    return sorted(ids)


@dataclass(frozen=True)
class Selection:
    tags: dict[str, set[str]]
    """Reason codes per selected A id."""
    selected_by: dict[str, list[str]]
    """A ids each criterion selected (within its cap), in order."""
    available: dict[str, int]


def select(c: Committed, local: LocalEvidence | None) -> Selection:
    universe = _universe(c, local)
    all_tags: dict[str, set[str]] = {}
    for a in universe:
        t = committed_tags(c, a)
        if local is not None:
            t |= local_tags(c, a, local)
        if t:
            all_tags[a] = t
    criteria = ALL_CRITERIA if local is not None else COMMITTED_CRITERIA
    selected_by: dict[str, list[str]] = {}
    available: dict[str, int] = {}
    for cr in criteria:
        if cr.reason_code == "worked_example":
            qualifying = [a for a in WORKED_EXAMPLES if a in all_tags]
        else:
            qualifying = [a for a in universe if cr.reason_code in all_tags.get(a, ())]
        available[cr.reason_code] = len(qualifying)
        selected_by[cr.reason_code] = qualifying[: cr.cap]
    chosen = {a for ids in selected_by.values() for a in ids}
    return Selection(
        tags={a: all_tags[a] for a in sorted(chosen)},
        selected_by=selected_by,
        available=available,
    )


# ---- documents -------------------------------------------------------------------------------


def _case(c: Committed, a_id: str, tags: set[str], local: LocalEvidence | None) -> dict[str, Any]:
    rows = evidence_rows(c, a_id, local)
    narrative = None
    if a_id in WORKED_EXAMPLES:
        narrative = {"kind": "narrative", "source": NARRATIVE_SOURCE, "note": WORKED_EXAMPLES[a_id]}
    return {
        "case_id": contracts.validate_a_id(a_id),
        "a_id": a_id,
        "reason_codes": sorted(tags),
        "narrative": narrative,
        "evidence": rows,
        "comparison": comparison_block(rows),
        "labels": labels_block(c, a_id, rows, local),
    }


def selection_block(
    c: Committed, sel: Selection, local: LocalEvidence | None, *, with_local_hashes: bool
) -> dict[str, Any]:
    criteria = ALL_CRITERIA if local is not None else COMMITTED_CRITERIA
    counts: dict[str, int] = {}
    for tags in sel.tags.values():
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
    limitations = [
        "A curated exhibit, not a representative sample: no figure in the lab is computed from these cases.",
        "Each criterion takes the first `cap` qualifying A records in ascending A id order; a case carries every reason code it qualifies for, so counts_by_reason can exceed a criterion's cap.",
        *(
            f"{cr.reason_code}: {sel.available[cr.reason_code]} available, {len(sel.selected_by[cr.reason_code])} selected (cap {cr.cap})"
            for cr in criteria
        ),
        "Exhibit values are rounded to six decimals; a gap equal to the threshold is flagged gap_at_rounded_boundary because the exhibit cannot classify it.",
    ]
    if local is None:
        limitations.append(
            "Local-evidence criteria (unverified_accept, verified_wrong_accept, no_candidate, reject_all_methods) and the labels block need the owner-run local stage and are absent here."
        )
    block: dict[str, Any] = {
        "strategy_version": STRATEGY_VERSION,
        "total_cases": len(sel.tags),
        "counts_by_reason": dict(sorted(counts.items())),
        "criteria": [
            {
                "reason_code": cr.reason_code,
                "description": cr.description,
                "cap": cr.cap,
                "source": cr.source,
                "deterministic_order": cr.deterministic_order,
                "selected": len(sel.selected_by[cr.reason_code]),
                "available": sel.available[cr.reason_code],
            }
            for cr in criteria
        ],
        "limitations": limitations,
    }
    if with_local_hashes:
        if local is None:
            block["local_evidence"] = {
                "available": False,
                "note": "the owner-run local evidence stage did not run; labels are truth_unavailable",
            }
        else:
            by_role = {i["role"]: i["sha256"] for i in local.local.inputs}
            block["local_evidence"] = {
                "available": True,
                "note": "labels, candidate counts and unrounded gaps verified against the hash-checked data/ inputs of the recorded run",
                "verifier": local.verifier,
                "truth_content_sha256": c.manifest["sample"]["files"]["truth"]["content_sha256"],
                "candidates_file_sha256": by_role["local_candidates"],
                "features_file_sha256": by_role["local_features"],
            }
    return block


def build(c: Committed, local: LocalEvidence | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``(cases.json object, case_selection.json list)``."""
    sel = select(c, local)
    cases = [_case(c, a, sel.tags[a], local) for a in sorted(sel.tags)]
    doc = {
        "lab_cases_version": "1.0",
        "snapshot_id": c.snapshot_id,
        "policies": {
            m: {
                **c.policy_of(m),
                "score_kind": SCORE_KIND[m],
                "source_key": f"artifacts/methods/{m}.json#tier_policy",
            }
            for m in METHOD_VERSIONS
        },
        "selection": selection_block(c, sel, local, with_local_hashes=True),
        "cases": cases,
    }
    contracts.validate(doc, "lab_cases")
    contracts.assert_no_forbidden_keys(doc, "cases.json")
    flat = [
        {
            "case_id": cs["case_id"],
            "a_id": cs["a_id"],
            "reason_codes": cs["reason_codes"],
            "selection_rank": i + 1,
        }
        for i, cs in enumerate(cases)
    ]
    return doc, flat


# ---- consistency checks (used by `check`, with or without local data) ---------------------


def consistency_problems(doc: dict[str, Any], c: Committed) -> list[str]:
    """Recompute everything the committed exhibits determine and compare it with ``doc``; check
    the local parts for internal consistency without recomputing them."""
    problems: list[str] = []
    has_local = doc["selection"]["local_evidence"]["available"]
    sel = select(c, None)
    by_id = {cs["case_id"]: cs for cs in doc["cases"]}
    if [cs["case_id"] for cs in doc["cases"]] != sorted(by_id):
        problems.append("cases are not in ascending case_id order or contain duplicates")
    for a in sel.tags:
        if a not in by_id:
            problems.append(f"case {a} selected by a committed criterion is missing")
    for cs in doc["cases"]:
        a = cs["case_id"]
        if cs["a_id"] != a:
            problems.append(f"{a}: case_id and a_id differ")
        tags = set(cs["reason_codes"])
        committed = committed_tags(c, a)
        if tags - LOCAL_ONLY_CODES != committed:
            problems.append(
                f"{a}: committed reason codes {sorted(tags - LOCAL_ONLY_CODES)} != recomputed {sorted(committed)}"
            )
        if a not in sel.tags and not (tags & LOCAL_ONLY_CODES):
            problems.append(
                f"{a}: not selected by any committed criterion and carries no local reason code"
            )
        if (tags & LOCAL_ONLY_CODES) and not has_local:
            problems.append(f"{a}: local reason codes without local evidence")
        rows = evidence_rows(c, a, None)
        got = cs["evidence"]
        if len(got) != 3 or [r["method_version"] for r in got] != list(METHOD_VERSIONS):
            problems.append(f"{a}: evidence rows are not one per method in order")
            continue
        for want, have in zip(rows, got, strict=True):
            if want["exported"]:
                if have != want:
                    problems.append(
                        f"{a}/{want['method_version']}: evidence row differs from the exhibit"
                    )
            else:
                if have.get("exported") is not False:
                    problems.append(
                        f"{a}/{want['method_version']}: exported but absent from the exhibit"
                    )
                elif not has_local and have != want:
                    problems.append(f"{a}/{want['method_version']}: not-exported row differs")
                elif has_local and have["reason"] not in ("rejected", "no_candidate"):
                    problems.append(
                        f"{a}/{want['method_version']}: local not-exported reason must name the cause"
                    )
        if cs["comparison"] != comparison_block(rows):
            problems.append(f"{a}: comparison block differs from a fresh computation")
        want_narr = None
        if a in WORKED_EXAMPLES:
            want_narr = {
                "kind": "narrative",
                "source": NARRATIVE_SOURCE,
                "note": WORKED_EXAMPLES[a],
            }
        if cs["narrative"] != want_narr:
            problems.append(f"{a}: narrative differs from docs/FINDINGS.md")
        problems += _label_problems(cs, c)
    counts: dict[str, int] = {}
    for cs in doc["cases"]:
        for t in cs["reason_codes"]:
            counts[t] = counts.get(t, 0) + 1
    if doc["selection"]["counts_by_reason"] != counts:
        problems.append("selection.counts_by_reason differs from the cases")
    if doc["selection"]["total_cases"] != len(doc["cases"]):
        problems.append("selection.total_cases differs from the cases")
    for cr in doc["selection"]["criteria"]:
        code = cr["reason_code"]
        if code in sel.selected_by:
            if (
                cr["selected"] != len(sel.selected_by[code])
                or cr["available"] != sel.available[code]
            ):
                problems.append(
                    f"criterion {code}: selected/available counts differ from a fresh selection"
                )
        elif code in LOCAL_ONLY_CODES:
            if cr["selected"] > cr["cap"] or cr["selected"] > counts.get(code, 0):
                problems.append(f"criterion {code}: selected exceeds cap or tagged cases")
        else:
            problems.append(f"unknown criterion {code}")
    return problems


def _label_problems(cs: dict[str, Any], c: Committed) -> list[str]:
    a = cs["case_id"]
    lab = cs["labels"]
    tags = set(cs["reason_codes"])
    problems = []
    if lab["state"] == "truth_unavailable":
        if tags & LOCAL_ONLY_CODES:
            problems.append(f"{a}: local reason codes with truth_unavailable labels")
        return problems
    chosen = {r["method_version"]: r["b_id"] for r in cs["evidence"] if r["exported"]}
    truth = set(lab["truth_b_ids"])
    if lab["labelled"] != bool(truth):
        problems.append(f"{a}: labelled flag disagrees with truth_b_ids")
    if lab["labelled"]:
        if lab["truth_visible_in_exported_choices"] != bool(set(chosen.values()) & truth):
            problems.append(f"{a}: truth_visible_in_exported_choices disagrees with the evidence")
        if lab["truth_reachable_full"] is None:
            problems.append(f"{a}: labelled case without truth_reachable_full")
        if lab["truth_visible_in_exported_choices"] and not lab["truth_reachable_full"]:
            problems.append(f"{a}: truth visible in choices but marked unreachable")
    else:
        if (
            lab["truth_reachable_full"] is not None
            or lab["truth_visible_in_exported_choices"] is not None
        ):
            problems.append(f"{a}: unlabelled case with reachability flags")
    for m, pm in lab["per_method"].items():
        b = chosen.get(m)
        want = (b in truth) if (lab["labelled"] and b is not None) else None
        if pm["chosen_correct"] != want:
            problems.append(f"{a}/{m}: chosen_correct disagrees with truth_b_ids and the evidence")
        if m == "learned_v1" and (
            pm["unrounded_gap"] is not None or pm["unrounded_ambiguous"] is not None
        ):
            problems.append(f"{a}/learned_v1: unrounded learned values cannot exist")
        if pm["unrounded_gap"] is not None:
            row = next(r for r in cs["evidence"] if r["method_version"] == m)
            if (
                row["exported"]
                and row["top2_gap"] is not None
                and abs(round(pm["unrounded_gap"], 6) - row["top2_gap"]) > 1e-9
            ):
                problems.append(f"{a}/{m}: unrounded gap does not round to the exhibit gap")
            if pm["unrounded_ambiguous"] != (pm["unrounded_gap"] < c.policy_of(m)["ambiguity_gap"]):
                problems.append(f"{a}/{m}: unrounded_ambiguous disagrees with unrounded_gap")
    if "unverified_accept" in tags and lab["labelled"]:
        problems.append(f"{a}: unverified_accept case is labelled")
    if "verified_wrong_accept" in tags and not any(
        r["exported"] and r["tier"] == "auto_accept" and r["b_id"] not in truth
        for r in cs["evidence"]
    ):
        problems.append(f"{a}: verified_wrong_accept without a wrong auto-accept")
    if "no_candidate" in tags and (
        lab["n_candidates_full"] != 0 or any(r["exported"] for r in cs["evidence"])
    ):
        problems.append(f"{a}: no_candidate case with candidates or exported rows")
    if "reject_all_methods" in tags and (
        lab["n_candidates_full"] == 0 or any(r["exported"] for r in cs["evidence"])
    ):
        problems.append(f"{a}: reject_all_methods case without candidates or with exported rows")
    return problems
