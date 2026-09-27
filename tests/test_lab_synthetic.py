"""The synthetic sandbox is invented end to end: its ids cannot be real ids, every readable
token comes from the nonsense vocabulary, no real exhibit id appears in it, and its expected
decisions reproduce with the policy engine (docs/DECISION_LAB.md section 7)."""

from __future__ import annotations

import json
import re

import pytest

from entity_resolution.config import METHOD_VERSIONS
from entity_resolution.decision_lab import contracts, sources, synthetic
from entity_resolution.decision_lab.policy import Policy, decide_row, row_from_candidates

SYN_A = re.compile(r"^SYN-A-[0-9]{3}$")
SYN_B = re.compile(r"^SYN-B-[0-9]{3}$")


@pytest.fixture(scope="module")
def doc() -> dict:
    return synthetic.render()


def test_fixture_file_is_current_and_valid(doc: dict) -> None:
    assert synthetic.SANDBOX_PATH.exists(), (
        "run python -m entity_resolution.decision_lab.cli synthetic"
    )
    assert synthetic.SANDBOX_PATH.read_text(encoding="utf-8") == synthetic.dumps()
    contracts.validate(
        json.loads(synthetic.SANDBOX_PATH.read_text(encoding="utf-8")), "lab_synthetic_sandbox"
    )
    assert doc["synthetic"] is True and doc["badge"] == synthetic.BADGE
    assert "not a prediction of any fitted model" in doc["score_kinds"]["synthetic_rules_like"]
    assert "learned_v1 is omitted" in doc["score_kinds"]["synthetic_exact_like"]


def test_ids_are_synthetic_and_never_real(doc: dict) -> None:
    a_ids = {r["id"] for r in doc["records"]["a"]}
    b_ids = {r["id"] for r in doc["records"]["b"]}
    assert all(SYN_A.fullmatch(a) for a in a_ids) and all(SYN_B.fullmatch(b) for b in b_ids)
    for x in a_ids | b_ids:
        assert not contracts.A_ID_RE.fullmatch(x) and not contracts.B_ID_RE.fullmatch(x)
    for c in doc["candidates"]:
        assert c["a_id"] in a_ids and c["b_id"] in b_ids
    for a, bs in doc["labels"].items():
        assert a in a_ids and set(bs) <= b_ids
    for cs in doc["cases"]:
        assert cs["a_id"] in a_ids and cs["case_id"].startswith("SYN-CASE-")
    for row in doc["downstream_fixture"]["mapping_with_duplicate"]:
        assert row["a_id"] in a_ids and row["b_id"] in b_ids


def test_every_readable_token_is_vocabulary(doc: dict) -> None:
    vocab = set(doc["vocabulary"])
    assert len(vocab) == 24
    for r in doc["records"]["a"] + doc["records"]["b"]:
        for token in (r["title"] + " " + r["artist_credit"]).split():
            assert token in vocab, token


def test_no_real_exhibit_id_appears_in_the_fixture(doc: dict) -> None:
    text = json.dumps(doc)
    committed = sources.load()
    for m in METHOD_VERSIONS:
        for a_id, row in committed.exhibits[m].rows.items():
            assert a_id not in text
            assert f'"{row.b_id}"' not in text
    assert not any(SYN_A.fullmatch(a) for m in METHOD_VERSIONS for a in committed.exhibits[m].rows)


def test_expected_decisions_reproduce(doc: dict) -> None:
    presets = {p["preset"]: Policy(**p["policy"]) for p in doc["policies"]}
    assert set(presets) == {"native_0.95_0.50_0.10", "lowered_accept_0.75", "wide_gap_0.25"}
    by_a: dict[str, list[dict]] = {}
    for c in doc["candidates"]:
        by_a.setdefault(c["a_id"], []).append(c)
    for cs in doc["cases"]:
        a = cs["a_id"]
        truth = frozenset(doc["labels"].get(a, []))
        for preset, per_kind in cs["expected"].items():
            for kind, want in per_kind.items():
                cands = [(c["b_id"], c["values"][kind]) for c in by_a.get(a, [])]
                chosen, row = row_from_candidates(
                    cands, labelled=a in doc["labels"], truth_b_ids=truth or None
                )
                d = decide_row(row, presets[preset])
                assert (
                    want["chosen_b_id"] == chosen
                    and want["tier"] == d.tier
                    and want["reason"] == d.reason
                )
                assert (
                    want["gap"] == d.gap
                    and want["ambiguous"] == d.ambiguous
                    and want["demoted"] == d.demoted
                )
    exp = {cs["case_id"]: cs["expected"] for cs in doc["cases"]}
    reg = exp["SYN-CASE-regression_0_80_0_76"]
    assert reg["native_0.95_0.50_0.10"]["synthetic_rules_like"]["tier"] == "review"
    assert reg["lowered_accept_0.75"]["synthetic_rules_like"]["tier"] == "review"
    assert reg["lowered_accept_0.75"]["synthetic_rules_like"]["demoted"] is True
    tie = exp["SYN-CASE-exact_tie_gap_zero"]["native_0.95_0.50_0.10"]["synthetic_exact_like"]
    assert tie["gap"] == 0.0 and tie["tier"] == "review" and tie["chosen_b_id"] == "SYN-B-001"
    assert (
        exp["SYN-CASE-no_candidate"]["native_0.95_0.50_0.10"]["synthetic_rules_like"]["reason"]
        == "no_candidate"
    )
    assert (
        exp["SYN-CASE-value_exactly_at_accept"]["native_0.95_0.50_0.10"]["synthetic_rules_like"][
            "tier"
        ]
        == "auto_accept"
    )
    assert (
        exp["SYN-CASE-blocking_unreachable_truth"]["native_0.95_0.50_0.10"]["synthetic_rules_like"][
            "truth_reachable"
        ]
        is False
    )
    assert (
        exp["SYN-CASE-labelled_wrong_accept"]["native_0.95_0.50_0.10"]["synthetic_exact_like"][
            "top1_correct"
        ]
        is False
    )
    assert (
        exp["SYN-CASE-unlabelled_accept"]["native_0.95_0.50_0.10"]["synthetic_exact_like"][
            "top1_correct"
        ]
        is None
    )


def test_downstream_fixture_conserves_row_count(doc: dict) -> None:
    fx = doc["downstream_fixture"]
    assert fx["conserved_row_count"] == len(fx["fact_rows"])
    b_units = {r["b_id"]: r["units"] for r in fx["fact_rows"]}
    joined = [(m["a_id"], m["b_id"], b_units[m["b_id"]]) for m in fx["mapping_with_duplicate"]]
    # a B mapped from two A records appears twice in the join: inflation without a fact change
    assert len({b for _, b, _ in joined}) < len(joined)
    assert sum(b_units.values()) == sum(r["units"] for r in fx["fact_rows"])
