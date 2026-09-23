#!/usr/bin/env python
"""Compare two full runs (docs/REPRODUCIBILITY.md, the two-run gate): the sample, candidate and
feature parquet files by file bytes and by content hash, the manifest minus timestamps, run id
and runtime, and the truth audit, blocking report and split minus their timestamps.

    python scripts/check_reproducibility.py <snapshot_dir>
    python scripts/check_reproducibility.py --committed   # the committed artifacts alone (verify.yml)

``snapshot_dir`` holds the earlier run's manifest.json, truth_audit.json, contracts.json and
a.parquet / b.parquet / truth.parquet. Exit 0 when content is identical; a byte difference with
identical content is reported as writer metadata and still exits 0; a content difference exits
1, because that is a bug, not a tolerance.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import pandas as pd
import pyarrow.parquet as pq

from entity_resolution.config import (
    BLOCKING_REPORT_PATH,
    CONTRACTS_PATH,
    MANIFEST_PATH,
    PAIRS_DIR,
    SAMPLE_DIR,
    SPLIT_PATH,
    TRUTH_AUDIT_PATH,
)
from entity_resolution.data import acquire, sample

VOLATILE_MANIFEST = ("updated_at_utc", "run_id", "runtime", "manifest_sha256_at_evaluation")
VOLATILE_AUDIT = ("generated_at_utc",)


def _strip(obj: dict, keys: tuple[str, ...]) -> dict:
    return {k: v for k, v in obj.items() if k not in keys}


def _diff_keys(a: dict, b: dict, prefix: str = "") -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k), b.get(k)
        if isinstance(va, dict) and isinstance(vb, dict):
            out += _diff_keys(va, vb, f"{prefix}{k}.")
        elif va != vb:
            out.append(f"{prefix}{k}: {str(va)[:60]!r} != {str(vb)[:60]!r}")
    return out


def check_committed() -> int:
    """``--committed``: the committed artifacts are internally consistent. Every artifact
    validates against its schema; each mapping exhibit's sha256 equals the one in its method
    record; the manifest hash the evaluation ran against recomputes from the manifest; every
    artifact of the run carries the same feature version and code commit."""
    import hashlib

    import jsonschema

    from entity_resolution.config import ARTIFACTS_DIR, METHODS_DIR, REPO_ROOT, SCHEMAS_DIR

    problems: list[str] = []
    checked = 0

    def schema(name: str) -> dict:
        return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text())

    pairs = [
        (MANIFEST_PATH, "manifest"),
        (TRUTH_AUDIT_PATH, "truth_audit"),
        (CONTRACTS_PATH, "contracts"),
        (BLOCKING_REPORT_PATH, "blocking_report"),
        (SPLIT_PATH, "split"),
        (ARTIFACTS_DIR / "review_sensitivity.json", "review_sensitivity"),
    ]
    pairs += [(p, "eval_artifact") for p in sorted(ARTIFACTS_DIR.glob("eval_*.json"))]
    pairs += [(p, "method_version") for p in sorted(METHODS_DIR.glob("*.json"))]
    pairs += [(p, "profile") for p in sorted((ARTIFACTS_DIR / "profile").glob("*.json"))]
    for path, name in pairs:
        if not path.exists():
            continue
        try:
            jsonschema.validate(json.loads(path.read_text()), schema(name))
            checked += 1
        except jsonschema.ValidationError as e:
            problems.append(f"{path.relative_to(REPO_ROOT)}: {e.message[:120]}")
    manifest = json.loads(MANIFEST_PATH.read_text())
    if manifest.get("manifest_sha256_at_evaluation"):
        # the evaluation hashed the manifest as it stood before runtime, methods and the
        # final timestamp were added: every other key, with the placeholder timestamp of
        # registry.empty_manifest (pipeline/match.py, methods stage)
        before = {
            k: v
            for k, v in manifest.items()
            if k not in ("runtime", "methods", "manifest_sha256_at_evaluation")
        }
        before["updated_at_utc"] = "1970-01-01T00:00:00+00:00"
        recomputed = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
        if recomputed != manifest["manifest_sha256_at_evaluation"]:
            problems.append("manifest_sha256_at_evaluation does not recompute from the manifest")
        else:
            checked += 1
    versions: set[tuple[str, str]] = set()
    for rec in sorted(METHODS_DIR.glob("*.json")):
        r = json.loads(rec.read_text())
        versions.add((r["feature_version"], r["code_commit"]))
        exhibit = REPO_ROOT / r["parameters"]["mapping"]["test_exhibit"]
        if not exhibit.exists():
            problems.append(f"{rec.name}: exhibit {exhibit.name} missing")
            continue
        _, digest = acquire.file_sha256(exhibit)
        if digest != r["parameters"]["mapping"]["test_exhibit_sha256"]:
            problems.append(f"{rec.name}: exhibit sha256 differs from the record")
        else:
            checked += 1
    for ev in sorted(ARTIFACTS_DIR.glob("eval_*.json")):
        e = json.loads(ev.read_text())
        versions.add((e["input"]["feature_version"], e["input"]["code_commit"]))
    versions.add((manifest["feature_version"], manifest["code_commit"]))
    if len(versions) > 1:
        problems.append(f"artifacts disagree on feature version or code commit: {sorted(versions)}")
    for pr in problems:
        print("PROBLEM:", pr)
    print(
        f"{'FAIL' if problems else 'ok'}: {checked} checks on the committed artifacts, {len(problems)} problem(s)"
    )
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv == ["--committed"]:
        return check_committed()
    if len(argv) != 1:
        print(__doc__)
        return 2
    snap = Path(argv[0])
    problems: list[str] = []
    notes: list[str] = []
    files = [(n, SAMPLE_DIR / f"{n}.parquet") for n in ("a", "b", "truth")]
    files += [(n, PAIRS_DIR / f"{n}.parquet") for n in ("candidates", "features")]
    for name, new in files:
        old = snap / f"{name}.parquet"
        if not old.exists() or not new.exists():
            notes.append(f"{name}.parquet: not present in both runs; skipped")
            continue
        old_bytes, old_sha = acquire.file_sha256(old)
        new_bytes, new_sha = acquire.file_sha256(new)
        old_df, new_df = pd.read_parquet(old), pd.read_parquet(new)
        same_content = sample.content_sha256(old_df) == sample.content_sha256(new_df)
        same_frame = old_df.equals(new_df)
        if not same_content or not same_frame:
            problems.append(
                f"{name}.parquet: content differs (equals={same_frame}, hash match={same_content})"
            )
        elif old_sha != new_sha:
            om, nm = pq.read_metadata(old), pq.read_metadata(new)
            notes.append(
                f"{name}.parquet: bytes differ ({old_bytes} vs {new_bytes} bytes) but content is identical; "
                f"writer metadata: created_by {om.created_by!r} vs {nm.created_by!r}, "
                f"row groups {om.num_row_groups} vs {nm.num_row_groups}"
            )
        else:
            notes.append(
                f"{name}.parquet: identical bytes and content ({new_bytes} bytes, {len(new_df)} rows)"
            )
    old_m = _strip(json.loads((snap / "manifest.json").read_text()), VOLATILE_MANIFEST)
    new_m = _strip(json.loads(MANIFEST_PATH.read_text()), VOLATILE_MANIFEST)
    problems += [f"manifest {d}" for d in _diff_keys(old_m, new_m)]
    old_t = _strip(json.loads((snap / "truth_audit.json").read_text()), VOLATILE_AUDIT)
    new_t = _strip(json.loads(TRUTH_AUDIT_PATH.read_text()), VOLATILE_AUDIT)
    problems += [f"truth_audit {d}" for d in _diff_keys(old_t, new_t)]
    old_c = _strip(json.loads((snap / "contracts.json").read_text()), VOLATILE_AUDIT)
    new_c = _strip(json.loads(CONTRACTS_PATH.read_text()), VOLATILE_AUDIT)
    problems += [f"contracts {d}" for d in _diff_keys(old_c, new_c)]
    import gzip

    from entity_resolution.config import MAPPING_ARTIFACT_DIR

    for exhibit in sorted(MAPPING_ARTIFACT_DIR.glob("mapping_*.test.csv.gz")):
        old_e = snap / exhibit.name
        if not old_e.exists():
            notes.append(f"{exhibit.name}: not in the snapshot; skipped")
            continue
        with gzip.open(old_e, "rt") as fh:
            a_ = pd.read_csv(fh, dtype=str).drop(columns=["run_id", "decided_at_utc"])
        with gzip.open(exhibit, "rt") as fh:
            b_ = pd.read_csv(fh, dtype=str).drop(columns=["run_id", "decided_at_utc"])
        if a_.equals(b_):
            notes.append(
                f"{exhibit.name}: identical content ({len(b_)} rows; run_id and decided_at_utc ignored)"
            )
        else:
            problems.append(f"{exhibit.name}: content differs ({len(a_)} vs {len(b_)} rows)")
    from entity_resolution.config import ARTIFACTS_DIR, METHODS_DIR

    volatile_method = ("created_at_utc", "mapping")
    for rec in sorted(METHODS_DIR.glob("*.json")):
        old_r = snap / rec.name
        if old_r.exists():
            a_ = _strip(json.loads(old_r.read_text()), volatile_method)
            b_ = _strip(json.loads(rec.read_text()), volatile_method)
            # the exhibit's gzip hash changes with run_id and decided_at_utc inside the CSV;
            # the exhibit content itself is compared above
            a_["parameters"] = _strip(a_["parameters"], ("mapping",))
            b_["parameters"] = _strip(b_["parameters"], ("mapping",))
            problems += [f"method {rec.stem} {d}" for d in _diff_keys(a_, b_)]
    for ev in sorted(ARTIFACTS_DIR.glob("eval_*.json")):
        old_e = snap / ev.name
        if old_e.exists():
            a_ = _strip(json.loads(old_e.read_text()), VOLATILE_AUDIT)
            b_ = _strip(json.loads(ev.read_text()), VOLATILE_AUDIT)
            a_["input"] = {k: v for k, v in a_["input"].items() if k != "manifest_sha256"}
            b_["input"] = {k: v for k, v in b_["input"].items() if k != "manifest_sha256"}
            problems += [f"{ev.stem} {d}" for d in _diff_keys(a_, b_)]
    for label, path in (("blocking_report", BLOCKING_REPORT_PATH), ("split", SPLIT_PATH)):
        old_p = snap / path.name
        if old_p.exists() and path.exists():
            a_ = _strip(json.loads(old_p.read_text()), VOLATILE_AUDIT)
            b_ = _strip(json.loads(path.read_text()), VOLATILE_AUDIT)
            problems += [f"{label} {d}" for d in _diff_keys(a_, b_)]
    for n in notes:
        print("note:", n)
    for p in problems:
        print("PROBLEM:", p)
    print("FAIL: content differs" if problems else "ok: the two runs agree on content")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
