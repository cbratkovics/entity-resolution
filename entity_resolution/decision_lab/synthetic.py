"""``apps/decision-lab/fixtures/synthetic_sandbox.json``: readable, entirely invented records
and hand-picked fixture scores that demonstrate the policy mechanics (docs/DECISION_LAB.md
section 7; schema ``lab_synthetic_sandbox.schema.json``).

Identifiers are ``SYN-A-nnn`` / ``SYN-B-nnn`` and every title and artist token comes from a
fixed nonsense vocabulary, so nothing here can collide with a MusicBrainz or Discogs record.
The two value kinds are fixture scores chosen by hand to exercise the policy: they are not
predictions of any fitted model, and ``learned_v1`` is omitted because no frozen model can
score synthetic pairs. Expected decisions are computed by :func:`policy.decide_row`, the same
evaluator the real replay uses, so the sandbox teaches the real mechanics on fake records.
"""

from __future__ import annotations

from typing import Any

from entity_resolution.config import LAB_FIXTURES_DIR
from entity_resolution.decision_lab import contracts
from entity_resolution.decision_lab.policy import Policy, decide_row, row_from_candidates

SANDBOX_PATH = LAB_FIXTURES_DIR / "synthetic_sandbox.json"
BADGE = "SYNTHETIC — invented records and fixture scores; not the historical snapshot"

VOCABULARY: tuple[str, ...] = (
    "Zorbic",
    "Quandle",
    "Mirvane",
    "Plonket",
    "Drassil",
    "Vombrel",
    "Teskan",
    "Ulpharo",
    "Brindlow",
    "Cravitt",
    "Ostrume",
    "Fennwick",
    "Glomper",
    "Hexadrim",
    "Jollivant",
    "Kremdusk",
    "Lurvane",
    "Nubbleton",
    "Pharquil",
    "Rondobel",
    "Skelvish",
    "Trombique",
    "Wexlorn",
    "Yarbuckle",
)

PRESETS: tuple[tuple[str, dict[str, float]], ...] = (
    ("native_0.95_0.50_0.10", {"accept_min": 0.95, "review_min": 0.50, "ambiguity_gap": 0.10}),
    ("lowered_accept_0.75", {"accept_min": 0.75, "review_min": 0.50, "ambiguity_gap": 0.10}),
    ("wide_gap_0.25", {"accept_min": 0.95, "review_min": 0.50, "ambiguity_gap": 0.25}),
)

VALUE_KINDS = ("synthetic_exact_like", "synthetic_rules_like")


def _a(n: int, title: str, artist: str, year: int | None) -> dict[str, Any]:
    return {"id": f"SYN-A-{n:03d}", "title": title, "artist_credit": artist, "year": year}


def _b(n: int, title: str, artist: str, year: int | None) -> dict[str, Any]:
    return {"id": f"SYN-B-{n:03d}", "title": title, "artist_credit": artist, "year": year}


RECORDS_A: list[dict[str, Any]] = [
    _a(1, "Zorbic Quandle", "Mirvane", 1991),  # exact tie: two identical B masters
    _a(2, "Plonket Drassil", "Vombrel Teskan", 1984),  # near-gap demotion
    _a(3, "Ulpharo", "Brindlow", 2003),  # mandatory regression 0.80 / 0.76
    _a(4, "Cravitt Ostrume", "Fennwick", 1977),  # single candidate
    _a(5, "Glomper Hexadrim", "Jollivant", 2010),  # no candidate
    _a(6, "Kremdusk", "Lurvane Nubbleton", 1999),  # value exactly at accept
    _a(7, "Pharquil Rondobel", "Skelvish", None),  # unlabelled accept
    _a(8, "Trombique", "Wexlorn", 1968),  # labelled wrong accept
    _a(9, "Yarbuckle Zorbic", "Quandle Mirvane", 2015),  # blocking-unreachable truth
    _a(10, "Drassil Vombrel", "Teskan", 1990),  # clean accept with a clear gap
    _a(11, "Ulpharo Brindlow", "Cravitt", 1972),  # review by value, wide gap
    _a(12, "Ostrume Fennwick", "Glomper Hexadrim", 2001),  # reject: below review floor
]

RECORDS_B: list[dict[str, Any]] = [
    _b(1, "Zorbic Quandle", "Mirvane", 1991),
    _b(2, "Zorbic Quandle", "Mirvane", 1991),
    _b(3, "Plonket Drassil", "Vombrel Teskan", 1984),
    _b(4, "Plonket Drassil", "Vombrel", 1984),
    _b(5, "Ulpharo", "Brindlow", 2003),
    _b(6, "Ulpharo", "Brindlow Cravitt", 2004),
    _b(7, "Cravitt Ostrume", "Fennwick", 1977),
    _b(8, "Kremdusk", "Lurvane Nubbleton", 1999),
    _b(9, "Kremdusk", "Lurvane", 1998),
    _b(10, "Pharquil Rondobel", "Skelvish", 1988),
    _b(11, "Trombique", "Wexlorn", 1968),
    _b(12, "Trombique", "Wexlorn Yarbuckle", 1969),
    _b(13, "Yarbuckle Zorbic", "Quandle Mirvane", 2015),
    _b(14, "Drassil Vombrel", "Teskan", 1990),
    _b(15, "Ulpharo Brindlow", "Cravitt", 1972),
    _b(16, "Ostrume Fennwick", "Glomper", 1994),
]

# (a, b, exact_like, rules_like): fixture scores chosen by hand to exercise the policy.
CANDIDATES: list[tuple[int, int, float, float]] = [
    (1, 1, 1.0, 1.0),
    (1, 2, 1.0, 1.0),
    (2, 3, 1.0, 0.98),
    (2, 4, 0.0, 0.93),
    (3, 5, 0.0, 0.80),
    (3, 6, 0.0, 0.76),
    (4, 7, 1.0, 0.97),
    (6, 8, 1.0, 0.95),
    (6, 9, 0.0, 0.60),
    (7, 10, 1.0, 0.99),
    (7, 9, 0.0, 0.20),
    (8, 12, 1.0, 0.99),
    (8, 11, 0.0, 0.70),
    (9, 14, 0.0, 0.30),
    (10, 14, 1.0, 1.0),
    (10, 16, 0.0, 0.40),
    (11, 15, 0.0, 0.70),
    (11, 16, 0.0, 0.10),
    (12, 16, 0.0, 0.35),
]

LABELS: dict[str, list[str]] = {
    "SYN-A-001": ["SYN-B-002"],
    "SYN-A-002": ["SYN-B-003"],
    "SYN-A-003": ["SYN-B-005"],
    "SYN-A-004": ["SYN-B-007"],
    "SYN-A-005": ["SYN-B-013"],
    "SYN-A-006": ["SYN-B-008"],
    "SYN-A-008": ["SYN-B-011"],
    "SYN-A-009": ["SYN-B-013"],
    "SYN-A-010": ["SYN-B-014"],
    "SYN-A-011": ["SYN-B-015"],
    "SYN-A-012": ["SYN-B-016"],
}
"""Invented truth links; SYN-A-007 is unlabelled on purpose."""

CASES: list[tuple[str, int, str]] = [
    (
        "exact_tie_gap_zero",
        1,
        "Two identical B masters tie at the top: gap 0, review under any positive gap threshold; the lexically smaller B id is the chosen one.",
    ),
    (
        "near_gap_demotion",
        2,
        "Top value above accept_min but the runner-up is within the gap: demoted to review at gap 0.10; wide_gap_0.25 keeps it there.",
    ),
    (
        "regression_0_80_0_76",
        3,
        "The mandatory regression: values 0.80 and 0.76. Review at accept 0.95; lowering accept to 0.75 must still give review (gap 0.04 < 0.10); the legacy flag reuse would accept it.",
    ),
    (
        "single_candidate",
        4,
        "One candidate: null gap, never ambiguous; auto_accept on value alone.",
    ),
    (
        "no_candidate",
        5,
        "No blocked candidate: reject with reason no_candidate; the labelled truth SYN-B-013 is unreachable and the record still counts in the population.",
    ),
    (
        "value_exactly_at_accept",
        6,
        "Top value exactly at accept_min (0.95): inclusive bound, auto_accept; the runner-up is far away.",
    ),
    (
        "unlabelled_accept",
        7,
        "Unlabelled A record auto-accepted: counted by coverage and unverified accepts, invisible to precision.",
    ),
    (
        "labelled_wrong_accept",
        8,
        "Labelled record whose top candidate is not the truth link: an auto_accept that precision counts as wrong.",
    ),
    (
        "blocking_unreachable_truth",
        9,
        "The truth link SYN-B-013 is not among the blocked candidates: recall_labelled cannot count it, whatever the policy; the one candidate is rejected.",
    ),
    ("clean_accept", 10, "Exact hit with a clear gap: auto_accept under every preset."),
    (
        "review_by_value",
        11,
        "Value between review_min and accept_min with a wide gap: review by value, not by ambiguity; lowered_accept_0.75 does not lift 0.70 to accept.",
    ),
    (
        "reject_below_floor",
        12,
        "Value below review_min: reject; the ambiguity rule never lifts a reject.",
    ),
]


def _candidates_of(a_n: int, kind: str) -> list[tuple[str, float]]:
    idx = VALUE_KINDS.index(kind)
    return [(f"SYN-B-{b:03d}", (ex, ru)[idx]) for a, b, ex, ru in CANDIDATES if a == a_n]


def expected_for(a_n: int) -> dict[str, dict[str, Any]]:
    a_id = f"SYN-A-{a_n:03d}"
    truth = frozenset(LABELS.get(a_id, []))
    out: dict[str, dict[str, Any]] = {}
    for preset, pol in PRESETS:
        policy = Policy(**pol)
        per_kind: dict[str, Any] = {}
        for kind in VALUE_KINDS:
            chosen, row = row_from_candidates(
                _candidates_of(a_n, kind), labelled=a_id in LABELS, truth_b_ids=truth or None
            )
            d = decide_row(row, policy)
            per_kind[kind] = {
                "chosen_b_id": chosen,
                "tier": d.tier,
                "reason": d.reason,
                "gap": d.gap,
                "ambiguous": d.ambiguous,
                "demoted": d.demoted,
                "top1_correct": row.top1_correct,
                "truth_reachable": row.truth_reachable,
            }
        out[preset] = per_kind
    return out


def render() -> dict[str, Any]:
    tokens = set(VOCABULARY)
    for r in RECORDS_A + RECORDS_B:
        for word in (r["title"] + " " + r["artist_credit"]).split():
            if word not in tokens:
                raise ValueError(f"token {word!r} is not in the synthetic vocabulary")
    fact_rows = [{"b_id": r["id"], "units": 10 + 3 * i} for i, r in enumerate(RECORDS_B)]
    mapping = [
        {"a_id": "SYN-A-010", "b_id": "SYN-B-014"},
        {"a_id": "SYN-A-009", "b_id": "SYN-B-014"},
    ]
    doc = {
        "synthetic": True,
        "sandbox_version": "1.0",
        "badge": BADGE,
        "generated_by": "entity_resolution.decision_lab.synthetic",
        "vocabulary": list(VOCABULARY),
        "records": {"a": RECORDS_A, "b": RECORDS_B},
        "candidates": [
            {
                "a_id": f"SYN-A-{a:03d}",
                "b_id": f"SYN-B-{b:03d}",
                "values": {"synthetic_exact_like": ex, "synthetic_rules_like": ru},
            }
            for a, b, ex, ru in CANDIDATES
        ],
        "labels": LABELS,
        "score_kinds": {
            "synthetic_exact_like": (
                "fixture score chosen by hand to exercise the policy (0 or 1, like exact_v1); not "
                "a prediction of any fitted model; learned_v1 is omitted because no frozen model "
                "can score synthetic pairs"
            ),
            "synthetic_rules_like": (
                "fixture score chosen by hand to exercise the policy (a value in [0, 1], like the "
                "uncalibrated rules_v1 score); not a prediction of any fitted model; learned_v1 "
                "is omitted because no frozen model can score synthetic pairs"
            ),
        },
        "policies": [{"preset": name, "policy": dict(pol)} for name, pol in PRESETS],
        "cases": [
            {
                "case_id": f"SYN-CASE-{cid}",
                "a_id": f"SYN-A-{a:03d}",
                "purpose": purpose,
                "expected": expected_for(a),
            }
            for cid, a, purpose in CASES
        ],
        "downstream_fixture": {
            "note": (
                "fact_rows carries one row per synthetic B master with a unit count. Joining it "
                "through mapping_with_duplicate, where two A records map to SYN-B-014, inflates "
                "the joined row count above conserved_row_count: the duplicate-join distortion a "
                "one-to-many mapping causes downstream. The fact table itself is unchanged."
            ),
            "fact_rows": fact_rows,
            "mapping_with_duplicate": mapping,
            "conserved_row_count": len(fact_rows),
        },
    }
    contracts.validate(doc, "lab_synthetic_sandbox")
    return doc


def dumps() -> str:
    return contracts.dumps_canonical(render())


def write(path=SANDBOX_PATH) -> None:  # type: ignore[no-untyped-def]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(), encoding="utf-8")
