"""The committed lab export under artifacts/lab is complete, current and self-consistent: every
file validates, every hash matches, every snapshot value resolves to its source key, case
selection is deterministic, curated cases cannot leak into the snapshot, and the replay
bundles reconcile to the evaluation artifacts from the committed csv.gz alone
(docs/DECISION_LAB.md sections 4 to 6, 9). Real-data generation tests skip without data/."""

from __future__ import annotations

import csv
import dataclasses
import gzip
import json
import math
import random
import shutil
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from entity_resolution.config import (
    DATA_DIR,
    LAB_ARTIFACT_DIR,
    LAB_FIXTURES_DIR,
    METHOD_VERSIONS,
    REPO_ROOT,
    SCHEMAS_DIR,
)
from entity_resolution.decision_lab import cases, contracts, export, replay, snapshot, sources
from entity_resolution.decision_lab.policy import Policy, evaluate
from entity_resolution.models.tiering import SWEEP_THRESHOLDS
from entity_resolution.pipeline import methods as methods_stage

LAB = LAB_ARTIFACT_DIR
pytestmark = pytest.mark.skipif(
    not (LAB / "manifest.json").exists(), reason="artifacts/lab not exported"
)


@pytest.fixture(scope="module")
def committed() -> sources.Committed:
    return sources.load()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((LAB / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases_doc() -> dict:
    return json.loads((LAB / "cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snapshot_doc() -> dict:
    return json.loads((LAB / "snapshot.json").read_text(encoding="utf-8"))


# ---- schemas and files ----------------------------------------------------------------------


def test_lab_schemas_are_valid_json_schema() -> None:
    for name in contracts.SCHEMA_NAMES:
        jsonschema.Draft202012Validator.check_schema(contracts.load_schema(name))
        contracts.validator(name)  # cross-file refs resolve


def test_committed_lab_files_validate_and_hashes_match(manifest: dict) -> None:
    layout = export.Layout()
    for key, entry in manifest["files"].items():
        path = layout.resolve(key)
        data = path.read_bytes()
        assert contracts.sha256_bytes(data) == entry["sha256"], key
        assert len(data) == entry["bytes"], key
        if entry.get("schema"):
            contracts.validate(json.loads(data), entry["schema"])
    contracts.validate(manifest, "lab_manifest")
    assert not contracts.unlisted_files(LAB)


def test_no_forbidden_keys_in_lab_json() -> None:
    for p in LAB.rglob("*.json"):
        assert not contracts.forbidden_key_problems(json.loads(p.read_text(encoding="utf-8"))), p


def test_check_passes_on_the_committed_tree() -> None:
    result = export.check()
    assert result.ok, result.problems
    assert result.files >= 5 and result.checks >= 10


# ---- canonical writer, allowlist, forbidden keys --------------------------------------------


def test_canonical_writer_is_deterministic_and_rejects_non_finite() -> None:
    a = {"b": [1, 2.5, {"z": None, "y": "t"}], "a": True}
    b = {"a": True, "b": [1, 2.5, {"y": "t", "z": None}]}
    assert contracts.dumps_canonical(a) == contracts.dumps_canonical(b)
    assert contracts.dumps_canonical(a).endswith("\n")
    assert contracts.sha256_canonical(a) == contracts.sha256_canonical(b)
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(contracts.ContractError):
            contracts.dumps_canonical({"x": [bad]})


def test_allowlist_and_forbidden_keys(tmp_path: Path) -> None:
    lab = tmp_path / "lab"
    (lab / "replay").mkdir(parents=True)
    (lab / "manifest.json").write_text("{}")
    (lab / "replay" / "replay_rules_v1.json").write_text("{}")
    assert contracts.unlisted_files(lab) == []
    (lab / "notes.txt").write_text("x")
    (lab / "replay" / "scores.parquet").write_bytes(b"x")
    assert contracts.unlisted_files(lab) == ["notes.txt", "replay/scores.parquet"]
    assert contracts.forbidden_key_problems({"ok": {"title": 1}})
    assert contracts.forbidden_key_problems({"rows": [{"artist_credit": "x"}]})
    assert contracts.forbidden_key_problems({"a_id": "The Album Title"})
    assert not contracts.forbidden_key_problems(
        {"a_id": "03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2", "display_name": "x y"}
    )
    with pytest.raises(contracts.ContractError):
        contracts.assert_no_forbidden_keys({"label": "a b"})


def test_id_validators_and_link_builders() -> None:
    a = "03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2"
    assert (
        contracts.musicbrainz_release_group_url(a) == f"https://musicbrainz.org/release-group/{a}"
    )
    assert contracts.discogs_master_url("82406") == "https://www.discogs.com/master/82406"
    for bad in ("", "0123", "SYN-A-001", a.upper(), "../x", "82406 ", "<script>"):
        with pytest.raises(contracts.InvalidIdentifier):
            contracts.musicbrainz_release_group_url(bad)
        with pytest.raises(contracts.InvalidIdentifier):
            contracts.discogs_master_url(bad)


# ---- staleness -----------------------------------------------------------------------------


def test_altered_byte_is_detected(tmp_path: Path) -> None:
    lab = tmp_path / "lab"
    shutil.copytree(LAB, lab)
    fixtures_dir = tmp_path / "fixtures"
    shutil.copytree(LAB_FIXTURES_DIR, fixtures_dir)
    layout = export.Layout(lab_dir=lab, fixtures_dir=fixtures_dir)
    target = lab / "snapshot.json"
    data = bytearray(target.read_bytes())
    i = data.index(b'"value": 0.')
    data[i + 11] = ord("1") if data[i + 11] != ord("1") else ord("2")
    target.write_bytes(bytes(data))
    result = export.check(layout)
    assert not result.ok and any("snapshot.json" in p for p in result.problems)


def test_unlisted_file_fails_check(tmp_path: Path) -> None:
    lab = tmp_path / "lab"
    shutil.copytree(LAB, lab)
    fixtures_dir = tmp_path / "fixtures"
    shutil.copytree(LAB_FIXTURES_DIR, fixtures_dir)
    (lab / "extra.json").write_text('{"title": "a b"}')
    result = export.check(export.Layout(lab_dir=lab, fixtures_dir=fixtures_dir))
    assert not result.ok and any("extra.json" in p for p in result.problems)


# ---- snapshot ------------------------------------------------------------------------------


def _resolve(key: str):  # type: ignore[no-untyped-def]
    """Resolve a lab source key generically: ``path#dotted.key``, ``path#rows``,
    ``path#tier=<t> rows`` and ``A - B``."""
    if " - " in key:
        left, right = key.split(" - ", 1)
        return _resolve(left) - _resolve(right)
    path, _, frag = key.partition("#")
    file = REPO_ROOT / path
    if path.endswith(".csv.gz"):
        with gzip.open(file, "rt", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if frag == "rows":
            return len(rows)
        cond, _, _ = frag.partition(" rows")
        col, _, val = cond.partition("=")
        return sum(1 for r in rows if r[col] == val)
    cur = json.loads(file.read_text(encoding="utf-8"))
    for part in frag.split("."):
        cur = cur[part]
    return cur


def test_snapshot_values_resolve_to_their_source_keys(snapshot_doc: dict) -> None:
    for m, block in snapshot_doc["methods"].items():
        for name, metric in {
            **block["metrics"],
            **{k: v for k, v in block["calibration"].items() if k != "note"},
        }.items():
            assert metric["value"] == _resolve(metric["source_key"]), (m, name)
        for name, count in block["counts"].items():
            assert count["value"] == _resolve(count["source_key"]), (m, name)
        assert block["review_floor"]["points"] == _resolve(block["review_floor"]["source_key"])
        assert block["legacy_threshold_sweep"]["points"] == _resolve(
            block["legacy_threshold_sweep"]["source_key"]
        )
        pol = _resolve(block["policy_source"])
        assert block["policy"] == {
            "accept_min": pol["auto_accept_min"],
            "review_min": pol["review_min"],
            "ambiguity_gap": pol["ambiguity_gap"],
        }
    for key in snapshot_doc["population"]["source_keys"]:
        assert _resolve(key) in snapshot_doc["population"].values()


def test_snapshot_numerators_and_denominators_recompute(snapshot_doc: dict) -> None:
    for block in snapshot_doc["methods"].values():
        for name, metric in block["metrics"].items():
            if metric["numerator"] is None:
                assert name in ("f1", "f1_or_review")
                continue
            assert round(metric["numerator"] / metric["denominator"], 6) == metric["value"], name


def test_curated_cases_cannot_leak_into_the_snapshot(snapshot_doc: dict) -> None:
    assert "cases" not in snapshot_doc
    allowed = (
        "artifacts/eval_",
        "artifacts/methods/",
        "artifacts/review_sensitivity.json",
        "artifacts/mapping/",
        "artifacts/split.json",
    )

    def keys(obj):  # type: ignore[no-untyped-def]
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "source_key":
                    yield v
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    for k in keys(snapshot_doc):
        for part in k.split(" - "):
            assert part.startswith(allowed), k
    for k in snapshot_doc["population"]["source_keys"]:
        assert k.startswith(allowed)
    text = json.dumps(snapshot_doc)
    assert "cases.json" not in text and "case_selection" not in text


def test_snapshot_is_a_fresh_build(committed: sources.Committed, snapshot_doc: dict) -> None:
    assert snapshot.build(committed) == snapshot_doc


# ---- cases ---------------------------------------------------------------------------------


def _shuffled(c: sources.Committed, seed: int) -> sources.Committed:
    rng = random.Random(seed)
    exhibits = {}
    for m, ex in c.exhibits.items():
        items = list(ex.rows.items())
        rng.shuffle(items)
        exhibits[m] = dataclasses.replace(ex, rows=dict(items))
    return dataclasses.replace(c, exhibits=exhibits)


def test_case_selection_is_deterministic(committed: sources.Committed) -> None:
    first = cases.select(committed, None)
    second = cases.select(committed, None)
    third = cases.select(_shuffled(committed, 7), None)
    assert first == second == third
    doc1, flat1 = cases.build(committed, None)
    doc2, flat2 = cases.build(_shuffled(committed, 11), None)
    assert doc1 == doc2 and flat1 == flat2


def test_cases_are_valid_and_match_the_exhibits(
    committed: sources.Committed, cases_doc: dict
) -> None:
    assert 30 <= len(cases_doc["cases"]) <= 60
    assert cases_doc["snapshot_id"] == committed.snapshot_id
    counts: dict[str, int] = {}
    seen = set()
    for cs in cases_doc["cases"]:
        a = cs["a_id"]
        contracts.validate_a_id(a)
        assert cs["case_id"] == a and a not in seen
        seen.add(a)
        exported_any = any(a in committed.exhibits[m].rows for m in METHOD_VERSIONS)
        if not (set(cs["reason_codes"]) & {"no_candidate", "reject_all_methods"}):
            assert exported_any, a
        else:
            assert not exported_any, a
        assert [r["method_version"] for r in cs["evidence"]] == list(METHOD_VERSIONS)
        for r in cs["evidence"]:
            m = r["method_version"]
            ex = committed.exhibits[m].rows.get(a)
            if ex is None:
                assert r["exported"] is False
                continue
            assert r["exported"] and r["b_id"] == ex.b_id and r["score"] == ex.score
            assert r["probability"] == ex.probability and r["tier"] == ex.tier
            assert r["top2_gap"] == ex.top2_gap and r["block_keys"] == list(ex.block_keys)
            assert r["source"] == committed.exhibits[m].relpath
            pol = committed.policy_of(m)
            if ex.top2_gap is None:
                assert (
                    r["gap_state"] == "single_candidate" and r["ambiguity_demoted_derived"] is None
                )
            else:
                assert r["ambiguity_demoted_derived"] == (
                    ex.tier == "review"
                    and ex.probability >= pol["accept_min"]
                    and ex.top2_gap < pol["ambiguity_gap"]
                )
                assert r["gap_at_rounded_boundary"] == (
                    ex.top2_gap == round(pol["ambiguity_gap"], 6)
                )
        for t in cs["reason_codes"]:
            counts[t] = counts.get(t, 0) + 1
    assert cases_doc["selection"]["counts_by_reason"] == counts
    assert cases_doc["selection"]["total_cases"] == len(cases_doc["cases"])
    assert [cs["case_id"] for cs in cases_doc["cases"]] == sorted(seen)
    assert not cases.consistency_problems(cases_doc, committed)


def test_worked_examples_are_present_with_narrative(cases_doc: dict) -> None:
    by_id = {cs["a_id"]: cs for cs in cases_doc["cases"]}
    for a, note in cases.WORKED_EXAMPLES.items():
        cs = by_id[a]
        assert "worked_example" in cs["reason_codes"]
        assert cs["narrative"] == {
            "kind": "narrative",
            "source": cases.NARRATIVE_SOURCE,
            "note": note,
        }
    tie = by_id["03cf0b3d-48f1-3b04-a3be-5e4d5b7dcae2"]
    assert all(
        r["exported"] and r["tier"] == "review" and r["top2_gap"] == 0.0 for r in tie["evidence"]
    )
    assert "ambiguity_tie" in tie["reason_codes"]
    dis = by_id["ac8ca6a0-b24b-314c-ba05-c6b22c564ac9"]
    assert dis["comparison"]["agreement_class"] == "methods_disagree"
    boundary = by_id["41cb566c-8384-4a00-b944-e72280c673df"]
    rules_row = next(r for r in boundary["evidence"] if r["method_version"] == "rules_v1")
    assert rules_row["gap_at_rounded_boundary"] is True and rules_row["top2_gap"] == 0.1
    assert (
        next(r for r in boundary["evidence"] if r["method_version"] == "exact_v1")["exported"]
        is False
    )


def test_case_selection_file_matches_cases(cases_doc: dict) -> None:
    flat = json.loads((LAB / "case_selection.json").read_text(encoding="utf-8"))
    assert isinstance(flat, list) and len(flat) == len(cases_doc["cases"])
    for i, (row, cs) in enumerate(zip(flat, cases_doc["cases"], strict=True)):
        assert row == {
            "case_id": cs["case_id"],
            "a_id": cs["a_id"],
            "reason_codes": cs["reason_codes"],
            "selection_rank": i + 1,
        }


def test_local_labels_when_present(cases_doc: dict) -> None:
    if not cases_doc["selection"]["local_evidence"]["available"]:
        pytest.skip("export without local evidence")
    for cs in cases_doc["cases"]:
        lab = cs["labels"]
        assert lab["state"] == "verified_local"
        if "unverified_accept" in cs["reason_codes"]:
            assert not lab["labelled"]
        if "verified_wrong_accept" in cs["reason_codes"]:
            assert lab["labelled"] and any(
                pm["chosen_correct"] is False for pm in lab["per_method"].values()
            )
        assert lab["per_method"]["learned_v1"]["unrounded_gap"] is None
        for m in ("exact_v1", "rules_v1"):
            row = next(r for r in cs["evidence"] if r["method_version"] == m)
            gap = lab["per_method"][m]["unrounded_gap"]
            if row["exported"] and row["top2_gap"] is not None:
                assert gap is not None and round(gap, 6) == row["top2_gap"]
    boundary = next(
        cs for cs in cases_doc["cases"] if cs["a_id"] == "41cb566c-8384-4a00-b944-e72280c673df"
    )
    rules = boundary["labels"]["per_method"]["rules_v1"]
    assert rules["unrounded_gap"] < 0.10 and rules["unrounded_ambiguous"] is True


# ---- manifest ------------------------------------------------------------------------------


def test_manifest_digest_and_capabilities(
    manifest: dict, committed: sources.Committed, cases_doc: dict
) -> None:
    assert manifest["snapshot_id"] == committed.snapshot_id
    assert manifest["analytical_digest"] == export.analytical_digest(manifest["files"])
    assert manifest["selection"] == {
        k: v for k, v in cases_doc["selection"].items() if k != "local_evidence"
    }
    learned = manifest["capabilities"]["complete_replay"]["learned_v1"]
    if not learned["available"]:
        assert learned["note"] == replay.LEARNED_UNAVAILABLE_NOTE
        assert "replay_policy:learned_v1" not in manifest["supported_operations"]
    local_paths = {s["path"] for s in manifest["sources"] if s.get("local_only")}
    assert local_paths == {f"data/{rel}" for rel, _, _ in replay.LOCAL_INPUTS}
    assert manifest["evidence"]["lab_contract_version"] == "1.0"


# ---- replay bundles ------------------------------------------------------------------------


@pytest.mark.parametrize("method", METHOD_VERSIONS)
def test_replay_bundle_reconciles(
    method: str, committed: sources.Committed, manifest: dict, snapshot_doc: dict
) -> None:
    csv_path, meta_path = replay.bundle_paths(method)
    if not csv_path.exists():
        assert not manifest["capabilities"]["complete_replay"][method]["available"]
        pytest.skip(f"no replay bundle for {method}")
    rows = replay.read_bundle(csv_path)
    assert len(rows) == snapshot_doc["population"]["a_records"]
    assert replay.bundle_bytes(rows) == csv_path.read_bytes()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["rows"] == len(rows) and meta["completeness"]["conserved"]
    e = committed.evals[method]["metrics"]
    m = evaluate(rows, Policy(**committed.policy_of(method)))
    for label, path in replay.RECONCILED_METRICS:
        r, a = m, e
        for k in path:
            r, a = r[k], a[k]
        assert r == a, label
    assert replay.reconcile_floor_sweep(rows, committed, method)["all_equal"]
    div = replay.legacy_divergence(rows, committed, method)
    assert div == meta["legacy_sweep_divergence"]
    accept_min = committed.policy_of(method)["accept_min"]
    assert all(p["legacy_matches_artifact"] for p in div["points"])
    for p in div["points"]:
        if p["threshold"] >= accept_min:
            assert p["legacy_accepts"] == p["corrected_accepts"]
            assert p["legacy_review_queue"] == p["corrected_review_queue"]
    below = [t for t in SWEEP_THRESHOLDS if t < accept_min]
    if method == "rules_v1":
        differing = [p for p in div["points"] if p["legacy_accepts"] != p["corrected_accepts"]]
        assert differing and div["thresholds_differing"] == len(differing) <= len(below)
        assert div["max_accepts_difference"] > 0


def test_replay_reader_round_trip(tmp_path: Path) -> None:
    from entity_resolution.decision_lab.policy import ReplayRow

    rows = [
        ReplayRow(1.0, 0.09999999999999998, 3, True, True, True),
        ReplayRow(0.5, None, 1, False, None, None),
        ReplayRow(None, None, 0, True, None, False),
    ]
    data = replay.bundle_bytes(rows)
    path = tmp_path / "b.csv.gz"
    path.write_bytes(data)
    assert replay.read_bundle(path) == rows
    assert replay.bundle_bytes(rows) == data  # deterministic bytes (mtime 0)


# ---- real-data generation --------------------------------------------------------------------


@pytest.mark.skipif(not (DATA_DIR / "pairs" / "features.parquet").exists(), reason="data/ absent")
def test_rules_replay_regenerates_from_local_data(committed: sources.Committed) -> None:
    csv_path, _ = replay.bundle_paths("rules_v1")
    if not csv_path.exists():
        pytest.skip("no rules_v1 bundle committed")
    local = replay.load_local(committed)
    rep = replay.compute_method(committed, local, "rules_v1")
    assert rep is not None
    assert replay.bundle_bytes(rep.rows) == csv_path.read_bytes()
    boundary = rep.by_a_id()["41cb566c-8384-4a00-b944-e72280c673df"][1]
    assert boundary.v1 - boundary.v2 == 0.09999999999999998


# ---- methods stage hook ----------------------------------------------------------------------


def test_write_scored_pairs_writes_unrounded_values(tmp_path: Path) -> None:
    pairs = pd.DataFrame(
        {
            "a_id": ["a", "a", "b"],
            "b_id": ["1", "2", "3"],
            "fold": ["test", "test", "fit"],
            "score": [0.123456789, 0.5, 1.0],
            "probability": [0.987654321, 0.5, 1.0],
        }
    )
    rec = methods_stage.write_scored_pairs(
        pairs, "rules_v1", "run", "commit", tmp_path / "data" / "scored"
    )
    back = pd.read_parquet(tmp_path / "data" / "scored" / "scored_rules_v1.parquet")
    assert back["probability"].tolist() == [0.987654321, 0.5, 1.0]
    assert (
        rec["rows"] == 3
        and rec["run_id"] == "run"
        and rec["path"] == "data/scored/scored_rules_v1.parquet"
    )
    sidecar = json.loads((tmp_path / "data" / "scored" / "scored_rules_v1.json").read_text())
    assert sidecar["file_sha256"] == rec["file_sha256"]
    assert (SCHEMAS_DIR / "method_version.schema.json").exists()
