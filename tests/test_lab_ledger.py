"""Receipts and review-event ledgers validate against their schemas, hostile strings are
rejected or carried as data, and effective state is derived with one accepted B per
(scenario_id, a_id), reversible only through appended undo events
(docs/DECISION_LAB.md section 8)."""

from __future__ import annotations

import copy

import pytest

from entity_resolution.decision_lab import contracts, ledger

SNAPSHOT_ID = "20260923T140606+0000@7b7bf2ae19b1"
SNAPSHOT_REF = {
    "snapshot_id": SNAPSHOT_ID,
    "analytical_digest": "a" * 64,
    "evaluation_code_commit": "6b3124b176ea8ffaf198c3ee6aa966cd6a2eccb4",
    "feature_version": "0.2.0",
    "lab_contract_version": "1.0",
}
A1 = "03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2"
A2 = "ac8ca6a0-b24b-314c-ba05-c6b22c564ac9"


def receipt() -> dict:
    return {
        "receipt_version": "1.0",
        "receipt_id": "rcpt_0001_abcd",
        "kind": "policy_scenario",
        "created_at_utc": "2026-09-26T10:00:00+00:00",
        "decision_question": "Can the rules_v1 review queue fit a 10,000-row budget?",
        "snapshot": dict(SNAPSHOT_REF),
        "population": {
            "fold": "test",
            "grain": "a_record",
            "a_records": 96557,
            "labelled_a": 48372,
        },
        "method": {
            "method_version": "rules_v1",
            "score_kind": "uncalibrated_score",
            "policy": {"accept_min": 0.65, "review_min": 0.0756756772994995, "ambiguity_gap": 0.1},
            "policy_source": "artifacts/methods/rules_v1.json#tier_policy",
        },
        "selected_controls": {
            "control_kind": "supported_floor",
            "review_floor": 0.6,
            "replay_policy": None,
            "scenario_id": "floor:rules_v1@0.6",
            "what_stayed_fixed": "accept_min and ambiguity_gap at recorded values",
        },
        "user_constraints": {"queue_budget": 10000, "review_minutes_per_row": 1.5, "notes": ""},
        "observations": [
            {
                "claim": "queue at floor 0.6",
                "value": 10551,
                "source_key": "artifacts/review_sensitivity.json#methods.rules_v1.review_floor_sweep.points",
                "verified_by": "artifact",
            }
        ],
        "assumptions": ["review capacity is constant"],
        "alternatives_considered": [
            {"option": "floor 0.55", "why_not": "queue 15075 exceeds budget"}
        ],
        "chosen_action": "adopt_scenario_for_review",
        "rationale": "Fits the budget with recall_with_review 0.99571.",
        "limitations": ["recall is against labelled pairs only"],
        "outcome": {"status": "not_observed", "measured_value": None},
    }


def event(seq: int, action: str, a_id: str = A1, b_id: str | None = "683263", **over) -> dict:  # type: ignore[no-untyped-def]
    e = {
        "event_id": f"evt_{seq:04d}_xyz",
        "seq": seq,
        "occurred_at_utc": "2026-09-26T10:00:00+00:00",
        "snapshot_id": SNAPSHOT_ID,
        "scenario_id": "native:rules_v1",
        "a_id": a_id,
        "method_version": "rules_v1",
        "action": action,
        "b_id": b_id,
        "reason_code": "evidence_sufficient",
        "rationale": None,
        "supersedes_event_id": None,
        "reverses_event_id": None,
        "evidence_ref": {"case_id": a_id, "source": "cases.json"},
    }
    e.update(over)
    return e


def export(events: list[dict]) -> dict:
    return {
        "review_events_version": "1.0",
        "snapshot": dict(SNAPSHOT_REF),
        "exported_at_utc": "2026-09-26T10:00:00+00:00",
        "events": events,
    }


def test_valid_receipt_and_events_validate() -> None:
    ledger.validate_receipt(receipt())
    ledger.validate_events(export([event(1, "accept_candidate")]))


def test_hostile_strings_are_data_not_code() -> None:
    r = receipt()
    r["rationale"] = "<script>alert(1)</script> {{ 7 * 7 }} ${x} %s"
    ledger.validate_receipt(r)  # carried as data; the schema only bounds its length
    ev = event(1, "accept_candidate", rationale="<img src=x onerror=alert(1)>")
    ledger.validate_events(export([ev]))
    state = ledger.effective_state([ev], SNAPSHOT_ID)
    assert state[("native:rules_v1", A1)].accepted_b_id == "683263"


def test_overlong_strings_and_bad_ids_are_rejected() -> None:
    r = receipt()
    r["rationale"] = "x" * 5000
    with pytest.raises(contracts.ContractError):
        ledger.validate_receipt(r)
    for bad in ("not-a-uuid", "SYN-A-1", "03CF0B3D-48F1-3B04-A3BE-5E4D5B7DCAE2", ""):
        with pytest.raises(contracts.ContractError):
            ledger.validate_events(export([event(1, "accept_candidate", a_id=bad)]))
    for bad in ("0", "01", "1234567890123", "a b", "<b>"):
        with pytest.raises(contracts.ContractError):
            ledger.validate_events(export([event(1, "accept_candidate", b_id=bad)]))
    with pytest.raises(contracts.ContractError):
        ledger.validate_events(export([event(1, "accept_candidate", rationale="y" * 2001)]))
    with pytest.raises(contracts.ContractError):
        ledger.validate_events(export([event(1, "accept_candidate", scenario_id="bad scenario")]))
    with pytest.raises(contracts.ContractError):
        ledger.validate_events(export([event(1, "accept_candidate", extra="x")]))


def test_effective_state_append_accept_supersede_reject_defer_undo() -> None:
    events = [
        event(1, "accept_candidate", b_id="683263"),
        event(2, "accept_candidate", b_id="82406", supersedes_event_id="evt_0001_xyz"),
        event(3, "defer", a_id=A2, b_id=None),
        event(4, "reject_candidate", a_id=A2, b_id="120663"),
        event(5, "reject_candidate", b_id="1214912"),
    ]
    state = ledger.effective_state(events, SNAPSHOT_ID)
    s1 = state[("native:rules_v1", A1)]
    assert s1.accepted_b_id == "82406" and s1.accepted_event_id == "evt_0002_xyz"
    assert s1.rejected_candidates == {"1214912"} and s1.status == "accepted"
    s2 = state[("native:rules_v1", A2)]
    assert s2.deferred and s2.rejected_candidates == {"120663"} and not s2.has_effective_accept
    assert s2.status == "deferred"
    # reject_candidate never means "no match anywhere"
    only_reject = ledger.effective_state([event(1, "reject_candidate", b_id="1")], SNAPSHOT_ID)
    s = only_reject[("native:rules_v1", A1)]
    assert s.status == "rejected_candidates" and s.has_effective_accept is False
    # undo of the superseding accept restores the state without it
    events.append(
        event(6, "undo", b_id=None, reason_code="reversal", reverses_event_id="evt_0002_xyz")
    )
    state = ledger.effective_state(events, SNAPSHOT_ID)
    s1 = state[("native:rules_v1", A1)]
    assert s1.accepted_b_id == "683263" and "evt_0002_xyz" in s1.reversed_event_ids
    # rejecting the accepted candidate clears the accept
    events.append(event(7, "reject_candidate", b_id="683263"))
    s1 = ledger.effective_state(events, SNAPSHOT_ID)[("native:rules_v1", A1)]
    assert not s1.has_effective_accept and s1.rejected_candidates == {"1214912", "683263"}
    summary = ledger.summarize(
        ledger.effective_state(events, SNAPSHOT_ID), [A1, A2, "x"], {A1: "683263", A2: "82443"}
    )
    assert summary == {
        "cases": 3,
        "accepted": 0,
        "deferred": 1,
        "rejected_candidate_only": 1,
        "untouched": 1,
        "changed_mappings": 0,
        "unresolved_evidence": 1,
    }


def test_one_effective_accept_per_scenario_and_a() -> None:
    events = [
        event(1, "accept_candidate", b_id="683263"),
        event(2, "accept_candidate", b_id="82406"),
    ]
    with pytest.raises(ledger.LedgerError, match="supersede"):
        ledger.effective_state(events, SNAPSHOT_ID)
    events[1]["supersedes_event_id"] = "evt_0001_xyz"
    state = ledger.effective_state(events, SNAPSHOT_ID)
    assert sum(1 for s in state.values() if s.has_effective_accept) == 1
    other = [
        event(1, "accept_candidate", b_id="1"),
        event(2, "accept_candidate", b_id="2", scenario_id="floor:rules_v1@0.6"),
    ]
    state = ledger.effective_state(other, SNAPSHOT_ID)
    assert {k[0] for k in state} == {"native:rules_v1", "floor:rules_v1@0.6"}
    with pytest.raises(ledger.LedgerError):
        ledger.effective_state(
            [event(1, "accept_candidate", supersedes_event_id="evt_0009_xyz")], SNAPSHOT_ID
        )


def test_undo_rules() -> None:
    base = [event(1, "accept_candidate")]
    undo = event(2, "undo", b_id=None, reason_code="reversal", reverses_event_id="evt_0001_xyz")
    ledger.effective_state(base + [undo], SNAPSHOT_ID)
    again = event(3, "undo", b_id=None, reason_code="reversal", reverses_event_id="evt_0001_xyz")
    with pytest.raises(ledger.LedgerError, match="already reversed"):
        ledger.effective_state(base + [undo, again], SNAPSHOT_ID)
    undo_undo = event(
        3, "undo", b_id=None, reason_code="reversal", reverses_event_id="evt_0002_xyz"
    )
    with pytest.raises(ledger.LedgerError):
        ledger.effective_state(base + [undo, undo_undo], SNAPSHOT_ID)
    with pytest.raises(ledger.LedgerError, match="earlier event"):
        ledger.effective_state(
            [event(1, "undo", b_id=None, reverses_event_id="evt_0009_xyz")], SNAPSHOT_ID
        )
    wrong_case = event(2, "undo", a_id=A2, b_id=None, reverses_event_id="evt_0001_xyz")
    with pytest.raises(ledger.LedgerError, match="another"):
        ledger.effective_state(base + [wrong_case], SNAPSHOT_ID)


def test_sequence_and_snapshot_rules() -> None:
    with pytest.raises(ledger.LedgerError, match="contiguous"):
        ledger.effective_state(
            [event(1, "defer", b_id=None), event(3, "defer", b_id=None)], SNAPSHOT_ID
        )
    with pytest.raises(ledger.LedgerError):
        ledger.effective_state(
            [event(2, "defer", b_id=None), event(1, "defer", b_id=None)], SNAPSHOT_ID
        )
    dup = [event(1, "defer", b_id=None), event(2, "defer", b_id=None, event_id="evt_0001_xyz")]
    with pytest.raises(ledger.LedgerError, match="unique"):
        ledger.effective_state(dup, SNAPSHOT_ID)
    with pytest.raises(ledger.IncompatibleSnapshot):
        ledger.effective_state([event(1, "defer", b_id=None)], "20260101T000000+0000@000000000000")
    foreign = copy.deepcopy(event(1, "defer", b_id=None))
    foreign["snapshot_id"] = "20260101T000000+0000@000000000000"
    with pytest.raises(ledger.IncompatibleSnapshot):
        ledger.effective_state([foreign], SNAPSHOT_ID)
    assert ledger.effective_state([], SNAPSHOT_ID) == {}
