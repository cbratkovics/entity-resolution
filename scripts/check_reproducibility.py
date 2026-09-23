#!/usr/bin/env python
"""Compare two full runs (docs/REPRODUCIBILITY.md, the two-run gate): the sample, candidate and
feature parquet files by file bytes and by content hash, the manifest minus timestamps, run id
and runtime, and the truth audit, blocking report and split minus their timestamps.

    python scripts/check_reproducibility.py <snapshot_dir>

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


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
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
