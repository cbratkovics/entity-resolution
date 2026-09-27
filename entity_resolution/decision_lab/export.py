"""Build and verify the lab export (docs/DECISION_LAB.md section 9; schema
``lab_manifest.schema.json``).

``export`` writes, under ``artifacts/lab/`` only, the snapshot, the curated cases and their
flat selection list, the replay bundles (owner-run, when the hash-verified ``data/`` inputs are
present) and finally ``manifest.json``: every input with its sha256, every generated file with
its hash and byte count, the capability declaration, the population, the selection strategy
and an analytical digest over the analytical files. The two app fixtures under
``apps/decision-lab/fixtures/`` are written by the same command. Without local data an export
refuses to overwrite owner-run outputs unless ``--no-local`` is passed, so a CI rebuild can
never silently downgrade the committed export.

``check`` rewrites nothing: it recomputes every file the committed artifacts determine and
compares bytes, verifies every hash and byte count in the manifest, validates every file
against its schema, rejects unknown files and forbidden keys, and re-verifies the replay
bundles from the committed csv.gz alone, so it runs in CI without ``data/``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from entity_resolution.config import (
    DATA_DIR,
    LAB_ARTIFACT_DIR,
    LAB_DATA_DIR,
    LAB_FIXTURES_DIR,
    METHOD_VERSIONS,
    REPO_ROOT,
    SCORED_DIR,
)
from entity_resolution.decision_lab import (
    LAB_CONTRACT_VERSION,
    cases,
    contracts,
    fixtures,
    replay,
    snapshot,
    sources,
    synthetic,
)
from entity_resolution.decision_lab.sources import SCORE_KIND, Committed
from entity_resolution.models import registry

FIXTURE_KEYS = {
    "policy_fixtures": "apps/decision-lab/fixtures/policy_fixtures.json",
    "synthetic_sandbox": "apps/decision-lab/fixtures/synthetic_sandbox.json",
}
"""Manifest keys of the two app fixtures (repository-relative); lab files are keyed relative to
``artifacts/lab/``."""

SUPPORTED_OPERATIONS_BASE = (
    "compare_methods_at_recorded_policies",
    "select_supported_review_floor",
    "queue_budget_feasibility",
    "inspect_curated_case",
    "record_local_review_event",
    "export_import_receipt",
    "synthetic_sandbox",
)


class ExportRefused(RuntimeError):
    """The export would overwrite owner-run outputs with a downgraded build."""


@dataclass
class Layout:
    lab_dir: Path = LAB_ARTIFACT_DIR
    fixtures_dir: Path = LAB_FIXTURES_DIR
    data_dir: Path = DATA_DIR
    lab_data_dir: Path = LAB_DATA_DIR
    scored_dir: Path = SCORED_DIR

    def resolve(self, key: str) -> Path:
        if key.startswith("apps/"):
            return self.fixtures_dir / Path(key).name
        return self.lab_dir / key


# ---- export --------------------------------------------------------------------------------


def _owner_run_outputs_present(layout: Layout) -> list[str]:
    present = [
        p.relative_to(layout.lab_dir).as_posix()
        for p in sorted((layout.lab_dir / "replay").glob("*"))
        if p.is_file()
    ]
    cases_path = layout.lab_dir / "cases.json"
    if cases_path.exists():
        try:
            doc = json.loads(cases_path.read_text(encoding="utf-8"))
            if doc.get("selection", {}).get("local_evidence", {}).get("available"):
                present.append("cases.json (verified_local labels)")
        except (ValueError, AttributeError):
            present.append("cases.json (unreadable)")
    return present


def _file_entry(
    path: Path,
    *,
    generated_from: str,
    recomputable: bool,
    analytical: bool,
    rows: int | None,
    schema: str | None,
) -> dict[str, Any]:
    data = path.read_bytes()
    entry: dict[str, Any] = {
        "sha256": contracts.sha256_bytes(data),
        "bytes": len(data),
        "generated_from": generated_from,
        "recomputable_without_local_data": recomputable,
        "analytical": analytical,
    }
    if rows is not None:
        entry["rows"] = rows
    if schema is not None:
        entry["schema"] = schema
    return entry


def analytical_digest(files: dict[str, dict[str, Any]]) -> str:
    pairs = sorted([k, v["sha256"]] for k, v in files.items() if v["analytical"])
    return contracts.sha256_canonical(pairs)


def _sources_block(c: Committed) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"path": c.manifest_ref.relpath, "sha256": c.manifest_ref.sha256, "role": "manifest"}
    ]
    for m in METHOD_VERSIONS:
        out.append(
            {
                "path": c.eval_refs[m].relpath,
                "sha256": c.eval_refs[m].sha256,
                "role": "eval_artifact",
            }
        )
        out.append(
            {
                "path": c.method_refs[m].relpath,
                "sha256": c.method_refs[m].sha256,
                "role": "method_record",
            }
        )
        out.append(
            {
                "path": c.exhibits[m].relpath,
                "sha256": c.exhibits[m].sha256,
                "role": "mapping_exhibit",
            }
        )
    out.append(
        {
            "path": c.sensitivity_ref.relpath,
            "sha256": c.sensitivity_ref.sha256,
            "role": "review_sensitivity",
        }
    )
    out.append({"path": c.split_ref.relpath, "sha256": c.split_ref.sha256, "role": "split"})
    out.append(
        {"path": c.blocking_ref.relpath, "sha256": c.blocking_ref.sha256, "role": "blocking_report"}
    )
    out.append(
        {
            "path": c.truth_audit_ref.relpath,
            "sha256": c.truth_audit_ref.sha256,
            "role": "truth_audit",
        }
    )
    if c.findings_ref is not None:
        out.append(
            {
                "path": c.findings_ref.relpath,
                "sha256": c.findings_ref.sha256,
                "role": "findings_narrative",
            }
        )
    for rel, key, role in replay.LOCAL_INPUTS:
        out.append(
            {
                "path": f"data/{rel}",
                "sha256": replay._manifest_get(c.manifest, key),
                "role": role,
                "local_only": True,
            }
        )
    return sorted(out, key=lambda s: s["path"])


def _capabilities(
    c: Committed, layout: Layout, cases_doc: dict[str, Any], replays: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    local_ok = bool(cases_doc["selection"]["local_evidence"]["available"])
    complete: dict[str, Any] = {}
    for m in METHOD_VERSIONS:
        meta = replays.get(m)
        if meta is None:
            complete[m] = {
                "available": False,
                "note": replay.capability_note(m, False, None),
                "decision_value_kind": "unavailable",
            }
        else:
            source = (
                "scored_pairs"
                if any(i["role"] == "local_scored_pairs" for i in meta["inputs"])
                else "recomputed_from_features"
            )
            complete[m] = {
                "available": True,
                "note": replay.capability_note(m, True, source),
                "decision_value_kind": SCORE_KIND[m],
                "file": f"replay/{meta['file']}",
                "meta_file": f"replay/replay_{m}.json",
                "reconciled_to_eval_artifact": bool(meta["reconciliation"]["all_equal"]),
                "population_conserved": bool(meta["completeness"]["conserved"]),
            }
    return {
        "evidence_comparison": {
            "available": True,
            "note": "snapshot.json: every figure copied from a committed artifact with its source key",
        },
        "supported_floor_control": {
            "available": True,
            "note": "only the exported review floors of review_sensitivity.json at the recorded accept threshold; anything else is a replay",
        },
        "case_explorer": {
            "available": True,
            "note": f"{cases_doc['selection']['total_cases']} curated cases from the committed test-fold exhibits; not a representative sample",
        },
        "decision_ledger": {
            "available": True,
            "note": "local, append-only review events and scenario receipts validated against lab_review_events and lab_receipt; never an upstream write",
        },
        "synthetic_sandbox": {"available": True, "note": synthetic.BADGE},
        "local_case_evidence": {
            "available": local_ok,
            "note": (
                "labels, full candidate counts and unrounded gaps verified against the hash-checked data/ inputs of the recorded run"
                if local_ok
                else "the owner-run local evidence stage did not run for this export; case labels are truth_unavailable"
            ),
        },
        "complete_replay": complete,
    }


def export(layout: Layout | None = None, *, no_local: bool = False, log=print) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Build the export; returns the manifest. Raises :class:`ExportRefused` when local data is
    absent, ``no_local`` is false and owner-run outputs would be overwritten."""
    layout = layout or Layout()
    c = sources.load()
    snap = snapshot.build(c)
    population = snap["population"]
    local_ev: cases.LocalEvidence | None = None
    replays: dict[str, dict[str, Any]] = {}
    if no_local:
        log("local stages skipped (--no-local)")
    else:
        status = replay.local_input_status(c.manifest, layout.data_dir)
        missing = [s for s in status if not s["verified"]]
        if missing:
            for s in missing:
                why = "missing" if not s["present"] else f"sha256 differs from {s['manifest_key']}"
                log(f"local input unavailable: {s['path']}: {why}")
            present = _owner_run_outputs_present(layout)
            if present:
                raise ExportRefused(
                    "owner-run outputs present; pass --no-local to rebuild committed-only files or "
                    f"provide data/ (present: {', '.join(present)})"
                )
            log("building committed-only files")
        else:
            local = replay.load_local(c, layout.data_dir)
            method_replays: dict[str, replay.MethodReplay] = {}
            for m in METHOD_VERSIONS:
                rep = replay.compute_method(c, local, m, layout.scored_dir)
                if rep is None:
                    log(f"{m}: complete replay unavailable ({replay.LEARNED_UNAVAILABLE_NOTE})")
                    continue
                method_replays[m] = rep
                replays[m] = replay.write_bundle(
                    rep, c, population, layout.lab_dir, layout.lab_data_dir
                )
                div = replays[m]["legacy_sweep_divergence"]
                log(
                    f"{m}: replay bundle written ({len(rep.rows)} rows, {rep.value_source}); "
                    f"reconciled; legacy sweep differs at {div['thresholds_differing']} thresholds, "
                    f"max accepts difference {div['max_accepts_difference']}"
                )
            local_ev = cases.LocalEvidence(local=local, replays=method_replays)
    # bundles kept from an earlier owner run (no local data now): re-verify from the csv.gz
    for m in replay.methods_with_bundles(layout.lab_dir):
        if m in replays:
            continue
        problems = replay.verify_bundle(m, c, population, layout.lab_dir)
        if problems:
            raise replay.ReplayError(f"existing bundle for {m} does not verify: {problems[:3]}")
        replays[m] = json.loads(
            replay.bundle_paths(m, layout.lab_dir)[1].read_text(encoding="utf-8")
        )
        log(f"{m}: existing replay bundle re-verified from the committed csv.gz")
    cases_doc, flat = cases.build(c, local_ev)
    layout.lab_dir.mkdir(parents=True, exist_ok=True)
    contracts.write_canonical(layout.lab_dir / "snapshot.json", snap)
    contracts.write_canonical(layout.lab_dir / "cases.json", cases_doc)
    contracts.write_canonical(layout.lab_dir / "case_selection.json", flat)
    fixtures.write(layout.fixtures_dir / "policy_fixtures.json")
    synthetic.write(layout.fixtures_dir / "synthetic_sandbox.json")
    manifest = build_manifest(c, layout, snap, cases_doc, flat, replays)
    contracts.write_canonical(layout.lab_dir / "manifest.json", manifest)
    log(f"wrote {layout.lab_dir / 'manifest.json'} ({len(manifest['files'])} files)")
    return manifest


def build_manifest(
    c: Committed,
    layout: Layout,
    snap: dict[str, Any],
    cases_doc: dict[str, Any],
    flat: list[dict[str, Any]],
    replays: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    local_ok = bool(cases_doc["selection"]["local_evidence"]["available"])
    files: dict[str, dict[str, Any]] = {
        "snapshot.json": _file_entry(
            layout.lab_dir / "snapshot.json",
            generated_from="committed_artifacts",
            recomputable=True,
            analytical=True,
            rows=len(snap["methods"]),
            schema="lab_snapshot",
        ),
        "cases.json": _file_entry(
            layout.lab_dir / "cases.json",
            generated_from="committed_artifacts_and_local_data"
            if local_ok
            else "committed_artifacts",
            recomputable=not local_ok,
            analytical=True,
            rows=len(cases_doc["cases"]),
            schema="lab_cases",
        ),
        "case_selection.json": _file_entry(
            layout.lab_dir / "case_selection.json",
            generated_from="committed_artifacts_and_local_data"
            if local_ok
            else "committed_artifacts",
            recomputable=not local_ok,
            analytical=True,
            rows=len(flat),
            schema=None,
        ),
        FIXTURE_KEYS["policy_fixtures"]: _file_entry(
            layout.fixtures_dir / "policy_fixtures.json",
            generated_from="synthetic_generator",
            recomputable=True,
            analytical=False,
            rows=None,
            schema=None,
        ),
        FIXTURE_KEYS["synthetic_sandbox"]: _file_entry(
            layout.fixtures_dir / "synthetic_sandbox.json",
            generated_from="synthetic_generator",
            recomputable=True,
            analytical=False,
            rows=None,
            schema="lab_synthetic_sandbox",
        ),
    }
    for m, meta in replays.items():
        csv_path, meta_path = replay.bundle_paths(m, layout.lab_dir)
        files[f"replay/{csv_path.name}"] = _file_entry(
            csv_path,
            generated_from="committed_artifacts_and_local_data",
            recomputable=False,
            analytical=True,
            rows=meta["rows"],
            schema=None,
        )
        files[f"replay/{meta_path.name}"] = _file_entry(
            meta_path,
            generated_from="committed_artifacts_and_local_data",
            recomputable=False,
            analytical=True,
            rows=None,
            schema="lab_replay_meta",
        )
    selection = {k: v for k, v in cases_doc["selection"].items() if k != "local_evidence"}
    ops = list(SUPPORTED_OPERATIONS_BASE) + [
        f"replay_policy:{m}" for m in METHOD_VERSIONS if m in replays
    ]
    manifest = {
        "lab_manifest_version": "1.0",
        "snapshot_id": c.snapshot_id,
        "analytical_digest": analytical_digest(files),
        "evidence": snap["evidence"],
        "sources": _sources_block(c),
        "files": files,
        "capabilities": _capabilities(c, layout, cases_doc, replays),
        "population": snap["population"],
        "selection": selection,
        "supported_operations": ops,
        "build": {
            "built_at_utc": registry.utc_now_iso(),
            "builder_code_commit": registry.code_commit(),
            "builder_version": LAB_CONTRACT_VERSION,
        },
    }
    contracts.validate(manifest, "lab_manifest")
    contracts.assert_no_forbidden_keys(manifest, "manifest.json")
    return manifest


# ---- check ---------------------------------------------------------------------------------


@dataclass
class CheckResult:
    problems: list[str]
    files: int
    checks: int

    @property
    def ok(self) -> bool:
        return not self.problems


def check(layout: Layout | None = None) -> CheckResult:
    """Verify the export in place; nothing is written."""
    layout = layout or Layout()
    problems: list[str] = []
    checks = 0
    lab = layout.lab_dir
    manifest_path = lab / "manifest.json"
    if not manifest_path.exists():
        return CheckResult([f"{manifest_path.relative_to(REPO_ROOT)} is missing"], 0, 0)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems += [
        f"manifest.json: {p}" for p in contracts.validation_errors(manifest, "lab_manifest")
    ]
    checks += 1
    unlisted = contracts.unlisted_files(lab)
    problems += [f"{u}: not in the public export allowlist" for u in unlisted]
    checks += 1
    files = manifest.get("files", {})
    for rel in contracts.PUBLIC_EXPORT_ALLOWLIST:
        if rel != "manifest.json" and (lab / rel).exists() and rel not in files:
            problems.append(f"{rel}: present but not listed in manifest.files")
    for key, entry in files.items():
        path = layout.resolve(key)
        if not path.exists():
            problems.append(f"{key}: listed in manifest.files but missing")
            continue
        data = path.read_bytes()
        if contracts.sha256_bytes(data) != entry["sha256"]:
            problems.append(f"{key}: sha256 differs from manifest.files")
        if len(data) != entry["bytes"]:
            problems.append(f"{key}: byte count differs from manifest.files")
        checks += 1
        if path.suffix == ".json":
            try:
                obj = json.loads(data)
            except ValueError:
                problems.append(f"{key}: not valid JSON")
                continue
            if not key.startswith("apps/"):
                problems += [f"{key}: {p}" for p in contracts.forbidden_key_problems(obj)]
                if data != contracts.dumps_canonical(obj).encode("utf-8"):
                    problems.append(f"{key}: not in canonical serialisation")
            schema_name = entry.get("schema")
            if schema_name:
                problems += [f"{key}: {p}" for p in contracts.validation_errors(obj, schema_name)]
                checks += 1
    problems += [f"manifest.json: {p}" for p in contracts.forbidden_key_problems(manifest)]
    if manifest_path.read_bytes() != contracts.dumps_canonical(manifest).encode("utf-8"):
        problems.append("manifest.json: not in canonical serialisation")
    if problems:
        return CheckResult(problems, len(files) + 1, checks)
    # recompute what the committed artifacts determine
    c = sources.load()
    snap = snapshot.build(c)
    if (lab / "snapshot.json").read_bytes() != contracts.dumps_canonical(snap).encode("utf-8"):
        problems.append("snapshot.json: differs from a fresh build from the committed artifacts")
    checks += 1
    if manifest["snapshot_id"] != c.snapshot_id:
        problems.append(f"manifest.json: snapshot_id {manifest['snapshot_id']} != {c.snapshot_id}")
    if manifest["evidence"] != snap["evidence"]:
        problems.append("manifest.json: evidence block differs from the snapshot")
    if manifest["population"] != snap["population"]:
        problems.append("manifest.json: population block differs from the snapshot")
    checks += 1
    if not fixtures.check(layout.fixtures_dir / "policy_fixtures.json"):
        problems.append(f"{FIXTURE_KEYS['policy_fixtures']}: stale (differs from a fresh render)")
    checks += 1
    syn_path = layout.fixtures_dir / "synthetic_sandbox.json"
    if not syn_path.exists() or syn_path.read_text(encoding="utf-8") != synthetic.dumps():
        problems.append(f"{FIXTURE_KEYS['synthetic_sandbox']}: stale (differs from a fresh render)")
    checks += 1
    cases_path = lab / "cases.json"
    if not cases_path.exists():
        problems.append("cases.json: missing")
    else:
        doc = json.loads(cases_path.read_text(encoding="utf-8"))
        if doc["snapshot_id"] != c.snapshot_id:
            problems.append("cases.json: snapshot_id differs from the committed artifacts")
        want_policies = {
            m: {
                **c.policy_of(m),
                "score_kind": SCORE_KIND[m],
                "source_key": f"artifacts/methods/{m}.json#tier_policy",
            }
            for m in METHOD_VERSIONS
        }
        if doc["policies"] != want_policies:
            problems.append("cases.json: policies differ from the method records")
        problems += [f"cases.json: {p}" for p in cases.consistency_problems(doc, c)]
        checks += 1
        flat = [
            {
                "case_id": cs["case_id"],
                "a_id": cs["a_id"],
                "reason_codes": cs["reason_codes"],
                "selection_rank": i + 1,
            }
            for i, cs in enumerate(doc["cases"])
        ]
        sel_path = lab / "case_selection.json"
        if not sel_path.exists() or sel_path.read_bytes() != contracts.dumps_canonical(flat).encode(
            "utf-8"
        ):
            problems.append("case_selection.json: differs from the cases")
        checks += 1
        sel = {k: v for k, v in doc["selection"].items() if k != "local_evidence"}
        if manifest["selection"] != sel:
            problems.append("manifest.json: selection block differs from cases.json")
        local_ok = bool(doc["selection"]["local_evidence"]["available"])
        if manifest["capabilities"]["local_case_evidence"]["available"] != local_ok:
            problems.append(
                "manifest.json: local_case_evidence capability disagrees with cases.json"
            )
        if files["cases.json"].get("rows") != len(doc["cases"]):
            problems.append("manifest.json: cases.json row count differs")
        checks += 1
    with_bundles = replay.methods_with_bundles(lab)
    for m in METHOD_VERSIONS:
        cap = manifest["capabilities"]["complete_replay"].get(m)
        if cap is None:
            problems.append(f"manifest.json: complete_replay.{m} missing")
            continue
        if cap["available"] != (m in with_bundles):
            problems.append(
                f"manifest.json: complete_replay.{m}.available disagrees with the bundle files"
            )
        if m in with_bundles:
            problems += [
                f"replay/{m}: {p}" for p in replay.verify_bundle(m, c, snap["population"], lab)
            ]
            csv_key = f"replay/replay_{m}.test.csv.gz"
            if csv_key in files and files[csv_key].get("rows") != snap["population"]["a_records"]:
                problems.append(f"manifest.json: {csv_key} row count differs from the population")
            if f"replay_policy:{m}" not in manifest["supported_operations"]:
                problems.append(
                    f"manifest.json: replay_policy:{m} missing from supported_operations"
                )
            checks += 1
        elif f"replay_policy:{m}" in manifest["supported_operations"]:
            problems.append(f"manifest.json: replay_policy:{m} claimed without a bundle")
    if manifest["analytical_digest"] != analytical_digest(files):
        problems.append("manifest.json: analytical_digest does not recompute from files")
    checks += 1
    return CheckResult(problems, len(files) + 1, checks)


def main_check(layout: Layout | None = None) -> int:
    result = check(layout)
    if result.ok:
        print(f"ok: {result.files} files, {result.checks} checks")
        return 0
    for p in result.problems:
        print(f"problem: {p}", file=sys.stderr)
    print(f"FAILED: {len(result.problems)} problem(s)", file=sys.stderr)
    return 1
