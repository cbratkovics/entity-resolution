"""Decision records of the lab: scenario receipts and the append-only review-event ledger
(docs/DECISION_LAB.md section 8; schemas ``lab_receipt.schema.json`` and
``lab_review_events.schema.json``).

Imports are untrusted. Every string is length-limited and every identifier pattern-checked by
the schema; nothing here evaluates, formats or interprets a rationale, it is carried as data.
Effective state is derived, never stored: events are applied in ``seq`` order, an undo appends
a reversal that must name an earlier, not yet reversed event of the same ``(scenario_id,
a_id)``, an accept must name the accept it supersedes, and a rejected candidate never means
"no match anywhere": the state keeps the rejected set beside the accepted B. At most one
accepted B is effective per ``(scenario_id, a_id)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from entity_resolution.decision_lab import contracts


class LedgerError(ValueError):
    """An event log that cannot be applied."""


class IncompatibleSnapshot(LedgerError):
    """An event or export refers to a snapshot other than the loaded one."""


def validate_receipt(receipt: dict[str, Any]) -> None:
    contracts.validate(receipt, "lab_receipt")


def validate_events(export: dict[str, Any]) -> None:
    contracts.validate(export, "lab_review_events")


@dataclass
class CaseState:
    accepted_b_id: str | None = None
    accepted_event_id: str | None = None
    rejected_candidates: set[str] = field(default_factory=set)
    deferred: bool = False
    reversed_event_ids: set[str] = field(default_factory=set)

    @property
    def has_effective_accept(self) -> bool:
        return self.accepted_b_id is not None

    @property
    def status(self) -> str:
        if self.has_effective_accept:
            return "accepted"
        if self.deferred:
            return "deferred"
        if self.rejected_candidates:
            return "rejected_candidates"
        return "none"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted_b_id": self.accepted_b_id,
            "accepted_event_id": self.accepted_event_id,
            "has_effective_accept": self.has_effective_accept,
            "rejected_candidates": sorted(self.rejected_candidates),
            "deferred": self.deferred,
        }


Key = tuple[str, str]


def _check_sequence(events: list[dict[str, Any]], snapshot_id: str) -> None:
    seqs = [e["seq"] for e in events]
    if seqs != sorted(seqs):
        raise LedgerError("events are not sorted by seq")
    if seqs != list(range(1, len(seqs) + 1)):
        raise LedgerError("seq must be unique and contiguous from 1")
    ids = [e["event_id"] for e in events]
    if len(set(ids)) != len(ids):
        raise LedgerError("event_id values must be unique")
    for e in events:
        if e["snapshot_id"] != snapshot_id:
            raise IncompatibleSnapshot(
                f"event {e['event_id']} refers to snapshot {e['snapshot_id']!r}, loaded {snapshot_id!r}"
            )


def _fold(events: list[dict[str, Any]], reversed_ids: set[str]) -> dict[Key, CaseState]:
    """The state after applying, in order, every event that is neither an undo nor reversed."""
    state: dict[Key, CaseState] = {}
    for e in events:
        if e["action"] == "undo" or e["event_id"] in reversed_ids:
            continue
        key = (e["scenario_id"], e["a_id"])
        cs = state.setdefault(key, CaseState())
        action = e["action"]
        if action == "accept_candidate":
            cs.accepted_b_id = e["b_id"]
            cs.accepted_event_id = e["event_id"]
            cs.deferred = False
        elif action == "reject_candidate":
            cs.rejected_candidates.add(e["b_id"])
            if cs.accepted_b_id == e["b_id"]:
                cs.accepted_b_id = None
                cs.accepted_event_id = None
        elif action == "defer":
            cs.deferred = True
    return state


def effective_state(events: list[dict[str, Any]], snapshot_id: str) -> dict[Key, CaseState]:
    """Per ``(scenario_id, a_id)``: the accepted B (if any), the rejected candidate set and
    the deferred flag after every event has been applied in ``seq`` order. An undo removes
    the named event from the fold, so the state is what it would have been without it.

    Raises :class:`LedgerError` on a malformed log and :class:`IncompatibleSnapshot` when an
    event names another snapshot."""
    _check_sequence(events, snapshot_id)
    by_id: dict[str, dict[str, Any]] = {}
    reversed_by: dict[str, str] = {}
    seen: list[dict[str, Any]] = []
    for e in events:
        eid = e["event_id"]
        key = (e["scenario_id"], e["a_id"])
        action = e["action"]
        current = _fold(seen, set(reversed_by)).get(key, CaseState())
        if action == "undo":
            target = e["reverses_event_id"]
            if target is None or target not in by_id:
                raise LedgerError(f"undo {eid} does not name an earlier event")
            t = by_id[target]
            if (t["scenario_id"], t["a_id"]) != key:
                raise LedgerError(f"undo {eid} targets an event of another (scenario_id, a_id)")
            if t["action"] == "undo":
                raise LedgerError(f"undo {eid} targets another undo")
            if target in reversed_by:
                raise LedgerError(
                    f"undo {eid} targets {target}, already reversed by {reversed_by[target]}"
                )
            if e["supersedes_event_id"] is not None or e["b_id"] is not None:
                raise LedgerError(f"undo {eid} must not carry a b_id or supersede")
            reversed_by[target] = eid
        else:
            if e["reverses_event_id"] is not None:
                raise LedgerError(f"{action} {eid} must not reverse an event")
            if action == "accept_candidate":
                if e["b_id"] is None:
                    raise LedgerError(f"accept {eid} without a b_id")
                if e["supersedes_event_id"] != current.accepted_event_id:
                    raise LedgerError(
                        f"accept {eid} must supersede the effective accept "
                        f"{current.accepted_event_id!r} of {key}, names {e['supersedes_event_id']!r}"
                    )
            elif action == "reject_candidate":
                if e["b_id"] is None:
                    raise LedgerError(f"reject {eid} without a b_id")
                if e["supersedes_event_id"] is not None:
                    raise LedgerError(f"reject {eid} must not supersede")
            elif action == "defer":
                if e["b_id"] is not None or e["supersedes_event_id"] is not None:
                    raise LedgerError(f"defer {eid} carries a b_id or supersedes")
            else:  # pragma: no cover - the schema restricts the enum
                raise LedgerError(f"unknown action {action!r}")
        by_id[eid] = e
        seen.append(e)
    state = _fold(seen, set(reversed_by))
    for target in reversed_by:
        t = by_id[target]
        key = (t["scenario_id"], t["a_id"])
        state.setdefault(key, CaseState()).reversed_event_ids.add(target)
    return state


def summarize(
    effective: dict[Key, CaseState],
    case_set: list[str],
    baseline: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Counts over ``case_set`` (A ids): accepted, deferred, rejected_candidate_only, untouched,
    changed_mappings against ``baseline`` (A id -> baseline chosen B, or None) and
    unresolved_evidence (touched but neither accepted nor deferred)."""
    by_a: dict[str, list[CaseState]] = {}
    for (_, a_id), cs in effective.items():
        by_a.setdefault(a_id, []).append(cs)
    accepted = deferred = rejected_only = untouched = changed = unresolved = 0
    for a in case_set:
        states = by_a.get(a, [])
        if not states:
            untouched += 1
            continue
        if any(s.has_effective_accept for s in states):
            accepted += 1
            if baseline is not None:
                chosen = {s.accepted_b_id for s in states if s.has_effective_accept}
                if chosen != {baseline.get(a)}:
                    changed += 1
        elif any(s.deferred for s in states):
            deferred += 1
        elif any(s.rejected_candidates for s in states):
            rejected_only += 1
            unresolved += 1
        else:
            untouched += 1
    return {
        "cases": len(case_set),
        "accepted": accepted,
        "deferred": deferred,
        "rejected_candidate_only": rejected_only,
        "untouched": untouched,
        "changed_mappings": changed if baseline is not None else None,
        "unresolved_evidence": unresolved,
    }
