"""The committed inputs of the lab, loaded once: the manifest, the three evaluation artifacts,
the three method records, the review-sensitivity artifact, the split and the three test-fold
mapping exhibits (docs/DECISION_LAB.md section 2).

Everything is read from ``artifacts/`` exactly as committed; the exhibits are parsed with
identifier columns as strings and numeric columns as floats (``top2_gap`` empty means null).
The snapshot id ``<run_id>@<first 12 hex of manifest_sha256_at_evaluation>`` names the
evidence every lab file refers to.
"""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from entity_resolution.config import ARTIFACTS_DIR, METHOD_VERSIONS, REPO_ROOT
from entity_resolution.decision_lab import contracts

SCORE_KIND: dict[str, str] = {
    "exact_v1": "binary_score",
    "rules_v1": "uncalibrated_score",
    "learned_v1": "calibrated_probability",
}
FINDINGS_RELPATH = "docs/FINDINGS.md"


@dataclass(frozen=True)
class ExhibitRow:
    """One exported decision of a test-fold mapping exhibit (non-reject rows only)."""

    a_id: str
    b_id: str
    score: float
    probability: float
    tier: str
    block_keys: tuple[str, ...]
    top2_gap: float | None
    run_id: str
    decided_at_utc: str


@dataclass(frozen=True)
class Exhibit:
    method_version: str
    relpath: str
    sha256: str
    rows: dict[str, ExhibitRow]
    """Keyed by A id; every exhibit has exactly one row per A record."""

    def tier_count(self, tier: str) -> int:
        return sum(1 for r in self.rows.values() if r.tier == tier)


@dataclass(frozen=True)
class FileRef:
    relpath: str
    sha256: str

    @property
    def path(self) -> Path:
        return REPO_ROOT / self.relpath


@dataclass(frozen=True)
class Committed:
    artifacts_dir: Path
    manifest: dict[str, Any]
    manifest_ref: FileRef
    evals: dict[str, dict[str, Any]]
    eval_refs: dict[str, FileRef]
    methods: dict[str, dict[str, Any]]
    method_refs: dict[str, FileRef]
    sensitivity: dict[str, Any]
    sensitivity_ref: FileRef
    split: dict[str, Any]
    split_ref: FileRef
    blocking_ref: FileRef
    truth_audit_ref: FileRef
    findings_ref: FileRef | None
    exhibits: dict[str, Exhibit]

    @property
    def run_id(self) -> str:
        return str(self.manifest["run_id"])

    @property
    def snapshot_id(self) -> str:
        return f"{self.run_id}@{self.manifest['manifest_sha256_at_evaluation'][:12]}"

    def policy_of(self, method_version: str) -> dict[str, float]:
        tp = self.methods[method_version]["tier_policy"]
        return {
            "accept_min": float(tp["auto_accept_min"]),
            "review_min": float(tp["review_min"]),
            "ambiguity_gap": float(tp["ambiguity_gap"]),
        }

    def rel(self, path: Path) -> str:
        return path.relative_to(REPO_ROOT).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ref(path: Path) -> FileRef:
    return FileRef(path.relative_to(REPO_ROOT).as_posix(), contracts.sha256_file(path))


def _parse_float(s: str) -> float:
    return float(s)


def read_exhibit(path: Path, method_version: str) -> Exhibit:
    rows: dict[str, ExhibitRow] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for rec in reader:
            if rec["method_version"] != method_version:
                raise contracts.ContractError(
                    f"{path.name}: row for {rec['method_version']} in the {method_version} exhibit"
                )
            if rec["fold"] != "test":
                raise contracts.ContractError(f"{path.name}: non-test row for {rec['a_id']}")
            a_id = contracts.validate_a_id(rec["a_id"])
            if a_id in rows:
                raise contracts.ContractError(f"{path.name}: duplicate A record {a_id}")
            gap = rec["top2_gap"]
            rows[a_id] = ExhibitRow(
                a_id=a_id,
                b_id=contracts.validate_b_id(rec["b_id"]),
                score=_parse_float(rec["score"]),
                probability=_parse_float(rec["probability"]),
                tier=rec["tier"],
                block_keys=tuple(k for k in rec["block_keys"].split("|") if k),
                top2_gap=None if gap == "" else _parse_float(gap),
                run_id=rec["run_id"],
                decided_at_utc=rec["decided_at_utc"],
            )
    return Exhibit(
        method_version=method_version,
        relpath=path.relative_to(REPO_ROOT).as_posix(),
        sha256=contracts.sha256_file(path),
        rows=rows,
    )


def load(artifacts_dir: Path = ARTIFACTS_DIR) -> Committed:
    """Load and cross-check the committed inputs; raises :class:`contracts.ContractError` when
    the artifacts of one run disagree with each other."""
    manifest_path = artifacts_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    evals, eval_refs, methods, method_refs, exhibits = {}, {}, {}, {}, {}
    for m in METHOD_VERSIONS:
        ep = artifacts_dir / f"eval_{m}.json"
        mp = artifacts_dir / "methods" / f"{m}.json"
        evals[m] = _read_json(ep)
        eval_refs[m] = _ref(ep)
        methods[m] = _read_json(mp)
        method_refs[m] = _ref(mp)
        mapping = methods[m]["parameters"]["mapping"]
        xp = REPO_ROOT / mapping["test_exhibit"]
        exhibits[m] = read_exhibit(xp, m)
        if exhibits[m].sha256 != mapping["test_exhibit_sha256"]:
            raise contracts.ContractError(
                f"{mapping['test_exhibit']}: sha256 {exhibits[m].sha256} differs from "
                f"artifacts/methods/{m}.json#parameters.mapping.test_exhibit_sha256"
            )
        if len(exhibits[m].rows) != mapping["test_rows"]:
            raise contracts.ContractError(
                f"{mapping['test_exhibit']}: {len(exhibits[m].rows)} rows, record says "
                f"{mapping['test_rows']}"
            )
    sensitivity_path = artifacts_dir / "review_sensitivity.json"
    split_path = artifacts_dir / "split.json"
    findings = REPO_ROOT / FINDINGS_RELPATH
    committed = Committed(
        artifacts_dir=artifacts_dir,
        manifest=manifest,
        manifest_ref=_ref(manifest_path),
        evals=evals,
        eval_refs=eval_refs,
        methods=methods,
        method_refs=method_refs,
        sensitivity=_read_json(sensitivity_path),
        sensitivity_ref=_ref(sensitivity_path),
        split=_read_json(split_path),
        split_ref=_ref(split_path),
        blocking_ref=_ref(artifacts_dir / "blocking_report.json"),
        truth_audit_ref=_ref(artifacts_dir / "truth_audit.json"),
        findings_ref=_ref(findings) if findings.exists() else None,
        exhibits=exhibits,
    )
    _cross_check(committed)
    return committed


def _cross_check(c: Committed) -> None:
    run_id = c.run_id
    msha = c.manifest["manifest_sha256_at_evaluation"]
    commits = {c.evals[m]["input"]["code_commit"] for m in METHOD_VERSIONS}
    commits |= {c.methods[m]["code_commit"] for m in METHOD_VERSIONS}
    commits.add(c.sensitivity["code_commit"])
    if len(commits) != 1:
        raise contracts.ContractError(f"artifacts carry several code commits: {sorted(commits)}")
    for m in METHOD_VERSIONS:
        e = c.evals[m]
        if e["input"]["manifest_sha256"] != msha:
            raise contracts.ContractError(f"eval_{m}.json was evaluated against another manifest")
        if e["metrics"]["test_a"] != c.split["folds"]["test"]["a_records"]:
            raise contracts.ContractError(f"eval_{m}.json#metrics.test_a differs from split.json")
        if e["metrics"]["labelled_a"] != c.split["folds"]["test"]["labelled_a_records"]:
            raise contracts.ContractError(
                f"eval_{m}.json#metrics.labelled_a differs from split.json"
            )
        for r in c.exhibits[m].rows.values():
            if r.run_id != run_id:
                raise contracts.ContractError(
                    f"{c.exhibits[m].relpath}: run_id {r.run_id} differs from the manifest"
                )
            break
        tp = c.methods[m]["tier_policy"]
        th = e["thresholds"]
        if (tp["auto_accept_min"], tp["review_min"], tp["ambiguity_gap"]) != (
            th["auto_accept_min"],
            th["review_min"],
            th["ambiguity_gap"],
        ):
            raise contracts.ContractError(f"{m}: method record and eval artifact policies differ")
    reach = {c.evals[m]["metrics"]["labelled_a_reachable"] for m in METHOD_VERSIONS}
    if len(reach) != 1:
        raise contracts.ContractError(f"labelled_a_reachable differs across methods: {reach}")
    gen = {c.evals[m]["generated_at_utc"] for m in METHOD_VERSIONS}
    if len(gen) != 1:
        raise contracts.ContractError(f"eval artifacts carry several generation times: {gen}")
