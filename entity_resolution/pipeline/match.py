"""Entry point of the full build (``make full`` -> ``python -m entity_resolution.pipeline.match``).

Phase 2 stages (docs/BRIEF.md section 3): acquire (download once, verify against the manifest,
stream-extract), load both sides, classify the truth links, draw the deterministic sample,
run the contracts, write ``artifacts/manifest.json``, ``artifacts/truth_audit.json`` and
``artifacts/contracts.json``. Every stage is timed and the size of ``data/`` and the free disk
are measured after it (``manifest.json#runtime``), so the question whether a hosted runner can
run this is answered by numbers. Phases 3 and 4 add blocking, features, methods and evaluation
after the ``sample`` stage; until then :func:`run` stops after Phase 2 and says so.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from entity_resolution.config import (
    A_SCOPE_PRIMARY_TYPE,
    BLOCKING_REPORT_PATH,
    CONTRACTS_PATH,
    DATA_DIR,
    MANIFEST_PATH,
    PAIRS_DIR,
    PROJECT,
    RAW_DIR,
    SAMPLE_DIR,
    SPLIT_PATH,
    TRUTH_AUDIT_PATH,
    UNLINKED_SHARE,
)
from entity_resolution.data import acquire, contracts, loader, sample, truth
from entity_resolution.data.discogs import DiscogsAdapter
from entity_resolution.data.musicbrainz import MusicBrainzAdapter
from entity_resolution.eval import split
from entity_resolution.features import FEATURE_VERSION, blocking, pairs
from entity_resolution.models import registry

PHASE_STATUS = "Phase 3 complete; methods, tiering and evaluation arrive in Phase 4"
UNION_PAIR_GATE = 30_000_000
"""Stop and present before pair features if the blocking union exceeds this (owner's ruling)."""
SAMPLE_RULE = (
    "membership = sha256(source || '|' || native_id) as 64 hex chars <= threshold_hex; the "
    "threshold is the hash of the n-th smallest record of the unlinked pool with n chosen so that "
    "unlinked / sampled = unlinked_share; every alive in-scope truth pair is included"
)


def dir_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except FileNotFoundError:
                pass
    return total


class Runtime:
    """Per-stage wall time, data/ size and free disk; peak RSS of the process."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.stages: list[dict[str, Any]] = []
        self.t_start = time.monotonic()
        self.free_start = shutil.disk_usage(data_dir).free
        self.data_start = dir_bytes(data_dir)

    def stage(self, name: str):  # type: ignore[no-untyped-def]
        runtime = self

        class _Stage:
            def __enter__(self_inner):  # type: ignore[no-untyped-def]
                self_inner.t0 = time.monotonic()
                print(f"== {name}")
                return self_inner

            def __exit__(self_inner, *exc):  # type: ignore[no-untyped-def]
                seconds = round(time.monotonic() - self_inner.t0, 1)
                runtime.stages.append(
                    {
                        "name": name,
                        "seconds": seconds,
                        "data_dir_bytes_after": dir_bytes(runtime.data_dir),
                        "free_disk_bytes_after": shutil.disk_usage(runtime.data_dir).free,
                        "peak_rss_bytes_so_far": peak_rss_bytes(),
                    }
                )
                print(f"   {name}: {seconds}s")
                return False

        return _Stage()

    def block(self) -> dict[str, Any]:
        peak_data = max([self.data_start, *(s["data_dir_bytes_after"] for s in self.stages)])
        min_free = min([self.free_start, *(s["free_disk_bytes_after"] for s in self.stages)])
        return {
            "stages": self.stages,
            "total_seconds": round(time.monotonic() - self.t_start, 1),
            "data_dir_bytes_start": self.data_start,
            "data_dir_bytes_peak": peak_data,
            "free_disk_bytes_start": self.free_start,
            "free_disk_bytes_min": min_free,
            "disk_used_peak_bytes": max(0, self.free_start - min_free),
            "peak_rss_bytes": peak_rss_bytes(),
            "platform": sys.platform,
        }


def peak_rss_bytes() -> int:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if sys.platform == "darwin" else rss * 1024)


def file_hash(path: Path) -> str:
    return acquire.file_sha256(path)[1]


def write_parquet(df: pd.DataFrame, path: Path) -> dict[str, Any]:
    """Fixed writer options so two runs produce identical bytes; both hashes recorded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow", compression="zstd")
    # the content hash is taken from the file as read back, so a reader recomputes the same
    # value from disk (list columns and nullable ints round-trip with different Python types)
    read_back = pd.read_parquet(path)
    return {
        "path": path.relative_to(DATA_DIR).as_posix(),
        "rows": int(len(read_back)),
        "file_sha256": file_hash(path),
        "content_sha256": sample.content_sha256(read_back),
    }


def run(argv: list[str] | None = None) -> int:
    del argv
    side_a = PROJECT.require_side_a()
    a_adapter = loader.adapter(side_a)
    b_adapter = loader.adapter(PROJECT.side_b)
    assert isinstance(a_adapter, MusicBrainzAdapter) and isinstance(b_adapter, DiscogsAdapter)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rt = Runtime(DATA_DIR)
    manifest: dict[str, Any] = registry.empty_manifest(registry.code_commit())
    manifest["side_a"] = side_a
    manifest["run_id"] = registry.utc_now_iso().replace(":", "").replace("-", "")

    with rt.stage("acquire"):
        b_meta = acquire.download(b_adapter.SPEC, RAW_DIR)
        a_meta = acquire.download(a_adapter.SPEC, RAW_DIR)
        extract_meta = a_adapter.extract(
            RAW_DIR / a_adapter.SPEC.filename, a_adapter.mbdump_dir(RAW_DIR)
        )
        manifest["sources"] = [
            _source_block(b_meta),
            {
                **_source_block(a_meta),
                "extract": {
                    "tables": {t: v["bytes"] for t, v in extract_meta["tables"].items()},
                    "extract_seconds": extract_meta["extract_seconds"],
                    "extract_passes": extract_meta["extract_passes"],
                    "extracted_bytes": extract_meta["extracted_bytes"],
                },
            },
        ]

    with rt.stage("load_b"):
        b_all = b_adapter.load_frame(RAW_DIR / b_adapter.SPEC.filename, b_adapter.cache_path())
    with rt.stage("load_a"):
        a_all = a_adapter.load_frame(a_adapter.mbdump_dir(RAW_DIR), a_adapter.cache_path())
        raw_links = a_adapter.load_truth(
            a_adapter.mbdump_dir(RAW_DIR), a_adapter.truth_cache_path()
        )

    with rt.stage("truth"):
        t = truth.classify(raw_links, a_all, set(b_all["native_id"]))
        alive = t.alive_in_scope()
        linked_a = set(alive["a_id"])
        linked_b = set(alive["b_id"])
        any_link_a = set(raw_links["a_id"])
        out_of_scope_b = set(t.links[t.links["status"] == "truth_out_of_scope"]["b_id"]) - linked_b

    with rt.stage("sample"):
        a_scope = a_all[a_all["primary_type"] == A_SCOPE_PRIMARY_TYPE]
        a_pool = ~a_scope["native_id"].isin(any_link_a)
        a_sample, a_thr = sample.build_side(
            a_scope.drop(columns=["n_links"]), source=side_a, linked_ids=linked_a, pool_mask=a_pool
        )
        b_pool = pd.Series(True, index=b_all.index)
        b_sample, b_thr = sample.build_side(
            b_all, source=PROJECT.side_b, linked_ids=linked_b, pool_mask=b_pool
        )
        b_sample["b_linked_out_of_scope"] = b_sample["native_id"].isin(out_of_scope_b)
        # a year outside [1900, next year] is a data error in the source (a handful per side);
        # it becomes missing here and the count is recorded so the contract stays strict
        a_year_nulled = _null_wild_years(a_sample)
        b_year_nulled = _null_wild_years(b_sample)
        t = truth.apply_sample(t, set(a_sample["native_id"]), set(b_sample["native_id"]))
        a_sample = sample.normalize_sample(a_sample)
        b_sample = sample.normalize_sample(b_sample)
        truth_frame = t.links.copy()
        files = {
            "a": write_parquet(a_sample, SAMPLE_DIR / "a.parquet"),
            "b": write_parquet(b_sample, SAMPLE_DIR / "b.parquet"),
            "truth": write_parquet(truth_frame, SAMPLE_DIR / "truth.parquet"),
        }
        manifest["sample"] = {
            "rule": SAMPLE_RULE,
            "unlinked_share": UNLINKED_SHARE,
            "scope": {"a_primary_type": A_SCOPE_PRIMARY_TYPE, "b": "all masters"},
            "all_truth_pairs_in_scope": True,
            "thresholds": {"a": a_thr, "b": b_thr},
            "pools": {
                "a": "release groups of the scope primary type with no Discogs master link of any status",
                "b": "every master not in an alive in-scope link (masters linked only from out-of-scope release groups included, flagged b_linked_out_of_scope)",
            },
            "files": files,
        }
        manifest["counts"] = {
            side_a: {
                "loaded": int(len(a_all)),
                "in_scope": int(len(a_scope)),
                "sampled": int(len(a_sample)),
                "labelled": int(len(t.labelled_a_ids())),
                "year_out_of_range_nulled": a_year_nulled,
            },
            PROJECT.side_b: {
                "loaded": int(len(b_all)),
                "in_scope": int(len(b_all)),
                "sampled": int(len(b_sample)),
                "labelled": int(len(set(t.in_sample()["b_id"]))),
                "linked_out_of_scope_in_sample": int(b_sample["b_linked_out_of_scope"].sum()),
                "year_out_of_range_nulled": b_year_nulled,
            },
        }

    with rt.stage("contracts"):
        report = {
            "contracts_version": "1.0",
            "generated_at_utc": registry.utc_now_iso(),
            "sides": {
                side_a: contracts.run_contracts(
                    a_sample,
                    source=side_a,
                    max_null_rates={"title": 0.0, "artist_credit": 0.0, "year": 0.10},
                ),
                PROJECT.side_b: contracts.run_contracts(
                    b_sample,
                    source=PROJECT.side_b,
                    max_null_rates={"title": 0.0, "artist_credit": 0.0, "year": 0.10},
                ),
            },
        }
        report["ok"] = all(s["ok"] for s in report["sides"].values())
        registry.validate_and_write(report, "contracts", CONTRACTS_PATH)
        if not report["ok"]:
            print("contracts failed:", json.dumps(report, indent=1)[:2000], file=sys.stderr)
            return 1

    with rt.stage("truth_audit"):
        audit = {
            "audit_version": "1.0",
            "generated_at_utc": registry.utc_now_iso(),
            "feature_version": FEATURE_VERSION,
            "code_commit": manifest["code_commit"],
            **truth.audit(t, raw_links),
        }
        registry.validate_and_write(audit, "truth_audit", TRUTH_AUDIT_PATH)

    # ---- Phase 3: blocking, split, pair features -------------------------------------------
    in_sample = t.in_sample()[["a_id", "b_id"]].astype("string")
    with rt.stage("block"):
        candidates, block_report = blocking.build_candidates(a_sample, b_sample, in_sample)
        print(
            f"   union pairs {block_report['union_pairs']:,}; after cap "
            f"{block_report['candidate_pairs_after_cap']:,}; per key "
            f"{block_report['per_key_pairs']}; cap overflow {block_report['cap_overflow']}; "
            f"pair completeness union {block_report['pair_completeness']['union']} "
            f"per key {block_report['pair_completeness']['per_key']}"
        )
        block_artifact = {
            "report_version": "1.0",
            "generated_at_utc": registry.utc_now_iso(),
            "feature_version": FEATURE_VERSION,
            "code_commit": manifest["code_commit"],
            **block_report,
        }
        registry.validate_and_write(block_artifact, "blocking_report", BLOCKING_REPORT_PATH)
        if block_report["union_pairs"] > UNION_PAIR_GATE:
            manifest["runtime"] = rt.block()
            registry.write_manifest(manifest, MANIFEST_PATH, validate=True)
            print(
                f"make full: STOP: blocking union {block_report['union_pairs']:,} exceeds the "
                f"{UNION_PAIR_GATE:,} gate; pair features not computed (present before continuing)",
                file=sys.stderr,
            )
            return 3

    with rt.stage("split"):
        candidates["fold"] = split.assign(candidates["a_id"])
        split_artifact = {
            "split_version": "1.0",
            "generated_at_utc": registry.utc_now_iso(),
            "feature_version": FEATURE_VERSION,
            "code_commit": manifest["code_commit"],
            **split.report(a_sample["native_id"], t.labelled_a_ids(), in_sample, candidates),
        }
        registry.validate_and_write(split_artifact, "split", SPLIT_PATH)

    with rt.stage("features"):
        feats = pairs.pair_features(candidates, a_sample, b_sample)
        manifest["pairs"] = {
            "candidates": write_parquet(candidates, PAIRS_DIR / "candidates.parquet"),
            "features": write_parquet(feats, PAIRS_DIR / "features.parquet"),
            "pair_features": list(pairs.PAIR_FEATURES),
        }

    manifest["runtime"] = rt.block()
    manifest["feature_version"] = FEATURE_VERSION
    registry.write_manifest(manifest, MANIFEST_PATH, validate=True)
    print(
        f"wrote {MANIFEST_PATH}, {TRUTH_AUDIT_PATH}, {CONTRACTS_PATH}, "
        f"{BLOCKING_REPORT_PATH}, {SPLIT_PATH}"
    )
    print(f"make full: {PHASE_STATUS}")
    return 0


def _null_wild_years(df: pd.DataFrame) -> int:
    """Set years outside [YEAR_MIN, next year] to missing in place; return how many."""
    hi = contracts.year_max()
    years = pd.to_numeric(df["year"], errors="coerce")
    wild = years.notna() & ((years < contracts.YEAR_MIN) | (years > hi))
    df.loc[wild, "year"] = pd.NA
    df["year"] = df["year"].astype("Int64")
    return int(wild.sum())


def _source_block(meta: dict[str, Any]) -> dict[str, Any]:
    """Manifest source entry from a download record; the spec fills what an older record
    (written by the Phase 1 profiler) does not carry."""
    spec = acquire.DUMPS[meta.get("name") or meta["source"]]
    return {
        "name": spec.name,
        "side": spec.side,
        "dump_filename": meta["filename"],
        "dump_bytes": meta["bytes"],
        "dump_sha256": meta["sha256"],
        "download_url": meta["url"],
        "licence_url": spec.licence_url,
        "dump_date": meta["dump_date"],
        "download_seconds": meta["download_seconds"],
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    return run(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
