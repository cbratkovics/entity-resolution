"""The one pure policy specification of the lab (docs/DECISION_LAB.md section 3).

It restates :func:`entity_resolution.models.tiering.decide` at A-record grain over compact
replay rows, so a policy can be re-applied to a whole population without pandas and without
the baseline's ``ambiguity_review`` flag. The TypeScript evaluator in
``apps/decision-lab/src/lib/policy.ts`` mirrors this module; ``fixtures.py`` writes the shared
canonical fixtures both are tested against.

Semantics preserved from ``decide()``:

- the chosen candidate is the one with the highest decision value, ties broken by the
  lexically smallest B id (``sort_values(["a_id", "probability", "b_id"])``);
- the top-two gap is ``v1 - v2`` over decision values; a single candidate has a null gap;
- ``auto_accept`` iff ``v1 >= accept_min``; ``review`` iff ``review_min <= v1 < accept_min``;
  ``reject`` below (inclusive lower bounds, as in ``decide``);
- the ambiguity override applies to non-reject decisions only, with a strict ``gap < ambiguity_gap``;
- ``demoted`` (the baseline's ``ambiguity_review``) is the ambiguity condition **and**
  ``v1 >= accept_min``; ``ambiguous`` is tracked separately;
- an A record with no candidate is ``reject`` with reason ``no_candidate`` and stays in the
  population (tier shares sum to one over every A record).

Metrics follow :mod:`entity_resolution.eval.evaluator` exactly, including its rounding
(ratios to six decimals, F1 from the rounded precision and recall, tier shares unrounded) so a
replay at a method's recorded policy reconciles to ``eval_<method>.json`` to the last digit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

TIER_AUTO_ACCEPT = "auto_accept"
TIER_REVIEW = "review"
TIER_REJECT = "reject"
TIERS = (TIER_AUTO_ACCEPT, TIER_REVIEW, TIER_REJECT)

REASON_NO_CANDIDATE = "no_candidate"
REASON_ACCEPT = "value_at_or_above_accept_min"
REASON_REVIEW = "value_at_or_above_review_min"
REASON_REJECT = "value_below_review_min"
REASON_AMBIGUOUS = "ambiguity_gap_below_threshold"


class PolicyError(ValueError):
    """An invalid or non-finite policy."""


@dataclass(frozen=True)
class Policy:
    accept_min: float
    review_min: float
    ambiguity_gap: float

    def __post_init__(self) -> None:
        for name in ("accept_min", "review_min", "ambiguity_gap"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int | float):
                raise PolicyError(f"{name} must be a number, got {v!r}")
            if not math.isfinite(v):
                raise PolicyError(f"{name} must be finite, got {v!r}")
        if not 0.0 <= self.review_min <= self.accept_min <= 1.0:
            raise PolicyError(
                "policy must satisfy 0 <= review_min <= accept_min <= 1, got "
                f"review_min={self.review_min}, accept_min={self.accept_min}"
            )
        if not 0.0 <= self.ambiguity_gap <= 1.0:
            raise PolicyError(f"ambiguity_gap must be in [0, 1], got {self.ambiguity_gap}")

    def as_dict(self) -> dict[str, float]:
        return {
            "accept_min": float(self.accept_min),
            "review_min": float(self.review_min),
            "ambiguity_gap": float(self.ambiguity_gap),
        }


@dataclass(frozen=True)
class ReplayRow:
    """One A record of the population.

    ``v1``/``v2``: decision values of the best and second-best candidate under the method's own
    tie order (``None`` when absent). ``n_candidates``: size of the full blocked candidate set.
    ``labelled``: the A record has an in-sample truth link. ``top1_correct``: the chosen B is in
    the truth set (``None`` when unlabelled or no candidate). ``truth_reachable``: some
    candidate in the **full** blocked set is a truth pair (``None`` when unlabelled)."""

    v1: float | None
    v2: float | None
    n_candidates: int
    labelled: bool
    top1_correct: bool | None
    truth_reachable: bool | None

    def __post_init__(self) -> None:
        if self.n_candidates < 0:
            raise ValueError("n_candidates must be >= 0")
        if (self.v1 is None) != (self.n_candidates == 0):
            raise ValueError("v1 is null exactly when there is no candidate")
        if self.v2 is not None and self.n_candidates < 2:
            raise ValueError("v2 requires at least two candidates")
        if self.v2 is None and self.n_candidates >= 2:
            raise ValueError("v2 must be present when there are two or more candidates")
        for v in (self.v1, self.v2):
            if v is not None and not math.isfinite(v):
                raise ValueError("decision values must be finite")
        if self.v1 is not None and self.v2 is not None and self.v2 > self.v1:
            raise ValueError("v2 must not exceed v1 (candidates are ranked by decision value)")
        if not self.labelled and (
            self.top1_correct is not None or self.truth_reachable is not None
        ):
            raise ValueError("unlabelled rows carry no correctness or reachability")
        if self.labelled and self.truth_reachable is None:
            raise ValueError("labelled rows must state truth reachability")
        if self.labelled and self.v1 is not None and self.top1_correct is None:
            raise ValueError("labelled rows with a candidate must state top1_correct")
        if self.v1 is None and self.top1_correct is not None:
            raise ValueError("no candidate means no top1_correct")


@dataclass(frozen=True)
class Decision:
    tier: str
    reason: str
    gap: float | None
    ambiguous: bool
    demoted: bool


def rank_candidates(candidates: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Order ``(b_id, value)`` pairs the way ``decide`` does: value descending, B id ascending
    (lexical, as strings). Non-finite values are rejected."""
    for b, v in candidates:
        if not isinstance(b, str) or not b:
            raise ValueError("b_id must be a non-empty string")
        if not math.isfinite(v):
            raise ValueError(f"non-finite decision value for {b}")
    return sorted(candidates, key=lambda bv: (-bv[1], bv[0]))


def row_from_candidates(
    candidates: list[tuple[str, float]],
    *,
    labelled: bool,
    truth_b_ids: frozenset[str] | None = None,
    truth_reachable: bool | None = None,
) -> tuple[str | None, ReplayRow]:
    """Build a replay row from a full candidate list; returns ``(chosen_b_id, row)``.
    ``truth_reachable`` may be given when the candidate list is truncated for display; when it
    is omitted it is computed from the (then assumed complete) list."""
    ranked = rank_candidates(candidates)
    truth = truth_b_ids or frozenset()
    if not labelled:
        return (ranked[0][0] if ranked else None), ReplayRow(
            v1=ranked[0][1] if ranked else None,
            v2=ranked[1][1] if len(ranked) > 1 else None,
            n_candidates=len(ranked),
            labelled=False,
            top1_correct=None,
            truth_reachable=None,
        )
    reachable = (
        truth_reachable if truth_reachable is not None else any(b in truth for b, _ in ranked)
    )
    return (ranked[0][0] if ranked else None), ReplayRow(
        v1=ranked[0][1] if ranked else None,
        v2=ranked[1][1] if len(ranked) > 1 else None,
        n_candidates=len(ranked),
        labelled=True,
        top1_correct=(ranked[0][0] in truth) if ranked else None,
        truth_reachable=bool(reachable),
    )


def decide_row(row: ReplayRow, policy: Policy) -> Decision:
    if row.v1 is None:
        return Decision(TIER_REJECT, REASON_NO_CANDIDATE, None, False, False)
    v1 = row.v1
    if v1 >= policy.accept_min:
        base, reason = TIER_AUTO_ACCEPT, REASON_ACCEPT
    elif v1 >= policy.review_min:
        base, reason = TIER_REVIEW, REASON_REVIEW
    else:
        base, reason = TIER_REJECT, REASON_REJECT
    gap = None if row.v2 is None else v1 - row.v2
    ambiguous = base != TIER_REJECT and gap is not None and gap < policy.ambiguity_gap
    tier = TIER_REVIEW if ambiguous else base
    demoted = ambiguous and v1 >= policy.accept_min
    return Decision(tier, REASON_AMBIGUOUS if ambiguous else reason, gap, ambiguous, demoted)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 6) if d else None


def _f1(p: float | None, r: float | None, accepted: int, base: int) -> float | None:
    # evaluator._prf: F1 from the rounded precision and recall; 0.0 when either is zero but
    # something was accepted or there is a recall base; None when nothing was measurable.
    if p and r and (p + r):
        return round(2 * p * r / (p + r), 6)
    return 0.0 if accepted or base else None


def evaluate(rows: list[ReplayRow], policy: Policy) -> dict[str, Any]:
    """Every metric of ``eval_<method>.json#metrics`` that the replay rows can support, each
    with its numerator and denominator, at A-record grain over the population ``rows``."""
    n_test_a = len(rows)
    tiers = {t: 0 for t in TIERS}
    n_lab = n_reach = 0
    acc_lab = acc_lab_correct = 0
    rev_lab = rev_lab_reachable = 0
    n_accept_all = n_review_all = n_unverified = 0
    n_demoted = n_ambiguous = n_no_candidate = 0
    for row in rows:
        d = decide_row(row, policy)
        tiers[d.tier] += 1
        if d.reason == REASON_NO_CANDIDATE:
            n_no_candidate += 1
        n_ambiguous += int(d.ambiguous)
        n_demoted += int(d.demoted)
        if d.tier == TIER_AUTO_ACCEPT:
            n_accept_all += 1
            if not row.labelled:
                n_unverified += 1
        elif d.tier == TIER_REVIEW:
            n_review_all += 1
        if row.labelled:
            n_lab += 1
            n_reach += int(bool(row.truth_reachable))
            if d.tier == TIER_AUTO_ACCEPT:
                acc_lab += 1
                acc_lab_correct += int(bool(row.top1_correct))
            elif d.tier == TIER_REVIEW:
                rev_lab += 1
                rev_lab_reachable += int(bool(row.truth_reachable))
    p = _rate(acc_lab_correct, acc_lab)
    r = _rate(acc_lab_correct, n_reach)
    p_or = _rate(acc_lab_correct + rev_lab_reachable, acc_lab + rev_lab)
    r_or = _rate(acc_lab_correct + rev_lab_reachable, n_reach)
    return {
        "policy": policy.as_dict(),
        "test_a": n_test_a,
        "labelled_a": n_lab,
        "labelled_a_reachable": n_reach,
        "no_candidate_a": n_no_candidate,
        "pair_completeness_test": _rate(n_reach, n_lab),
        "at_auto_accept": {
            "accepted": acc_lab,
            "correct": acc_lab_correct,
            "precision": p,
            "recall_labelled": r,
            "f1": _f1(p, r, acc_lab, n_reach),
        },
        "at_auto_accept_or_review": {
            "accepted": acc_lab + rev_lab,
            "correct": acc_lab_correct + rev_lab_reachable,
            "precision": p_or,
            "recall_labelled": r_or,
            "f1": _f1(p_or, r_or, acc_lab + rev_lab, n_reach),
        },
        "recall_overall": _rate(acc_lab_correct, n_lab),
        "coverage": _rate(n_accept_all, n_test_a),
        "accepted_all": n_accept_all,
        "unverified_accepts": {
            "count": n_unverified,
            "share_of_accepts": _rate(n_unverified, n_accept_all),
        },
        "tier_counts": dict(tiers),
        "tier_shares": {t: (tiers[t] / n_test_a if n_test_a else None) for t in TIERS},
        "ambiguity_rule": {
            "decisions_moved_to_review": n_demoted,
            "ambiguous_non_reject": n_ambiguous,
            "review_queue": n_review_all,
        },
        "denominators": {
            "precision": "labelled auto-accepted A records",
            "recall_labelled": "labelled A records whose truth survived blocking",
            "recall_overall": "all labelled A records",
            "coverage": "all A records in the population",
            "share_of_accepts": "all auto-accepted A records",
        },
    }


def floor_sweep(
    rows: list[ReplayRow], *, accept_min: float, ambiguity_gap: float, floors: list[float]
) -> list[dict[str, Any]]:
    """The corrected review-floor sweep: every floor strictly below ``accept_min`` is a full
    replay with ``review_min = floor``. ``recall_with_review`` counts correct auto-accepts plus
    queued labelled rows whose truth is reachable, over labelled reachable A records."""
    out = []
    for floor in floors:
        if floor >= accept_min:
            continue
        m = evaluate(rows, Policy(accept_min, floor, ambiguity_gap))
        n_reach = m["labelled_a_reachable"]
        out.append(
            {
                "floor": floor,
                "queue_floor": m["ambiguity_rule"]["review_queue"]
                - m["ambiguity_rule"]["decisions_moved_to_review"],
                "queue_ambiguity": m["ambiguity_rule"]["decisions_moved_to_review"],
                "queue_total": m["ambiguity_rule"]["review_queue"],
                "queue_share_of_test_a": _rate(m["ambiguity_rule"]["review_queue"], m["test_a"]),
                "recall_with_review": _rate(m["at_auto_accept_or_review"]["correct"], n_reach),
            }
        )
    return out


def accept_sweep(
    rows: list[ReplayRow], *, review_min: float, ambiguity_gap: float, thresholds: list[float]
) -> list[dict[str, Any]]:
    """The corrected accept-threshold sweep: a full replay at every threshold. Compare with the
    legacy ``review_sensitivity.json#points``, which reused the baseline demotion flag."""
    out = []
    for t in thresholds:
        if t < review_min:
            continue
        m = evaluate(rows, Policy(t, review_min, ambiguity_gap))
        out.append(
            {
                "threshold": t,
                "accepts": m["accepted_all"],
                "queue_floor": m["ambiguity_rule"]["review_queue"]
                - m["ambiguity_rule"]["decisions_moved_to_review"],
                "queue_ambiguity": m["ambiguity_rule"]["decisions_moved_to_review"],
                "review_queue": m["ambiguity_rule"]["review_queue"],
                "precision_labelled": m["at_auto_accept"]["precision"],
                "labelled_accepts": m["at_auto_accept"]["accepted"],
                "labelled_false_accepts": m["at_auto_accept"]["accepted"]
                - m["at_auto_accept"]["correct"],
            }
        )
    return out


def legacy_accept_sweep(
    rows: list[ReplayRow],
    *,
    baseline: Policy,
    thresholds: list[float],
) -> list[dict[str, Any]]:
    """The legacy calculation of ``review_cost.sweep`` restated over replay rows: the demotion
    flag is computed once at ``baseline`` and reused at every threshold. Kept only to
    characterise the divergence from :func:`accept_sweep`; never a replay."""
    # the flag is a property of the baseline only, so it is computed once per row
    flagged = [(row.v1, decide_row(row, baseline).demoted) for row in rows if row.v1 is not None]
    out = []
    for t in thresholds:
        accepts = q_floor = q_amb = 0
        for v1, flag in flagged:
            if v1 >= t and not flag:
                accepts += 1
            if baseline.review_min <= v1 < t:
                q_floor += 1
            if flag and v1 >= t:
                q_amb += 1
        out.append(
            {
                "threshold": t,
                "accepts": accepts,
                "queue_floor": q_floor,
                "queue_ambiguity": q_amb,
                "review_queue": q_floor + q_amb,
            }
        )
    return out
