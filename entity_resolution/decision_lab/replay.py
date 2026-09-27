"""Complete-replay bundles: ``artifacts/lab/replay/replay_<method>.test.csv.gz`` and its metadata
``replay_<method>.json`` (docs/DECISION_LAB.md section 5; schema ``lab_replay_meta.schema.json``).

Owner-run: the frozen local outputs under ``data/`` are hash-verified against
``artifacts/manifest.json`` (never substituted), the decision values of every test-fold A
record are taken from ``data/scored/scored_<method>.parquet`` when the methods stage of the
same run wrote it, and otherwise recomputed for ``exact_v1`` and ``rules_v1`` from the frozen
features (``exact.score`` and ``rules.score`` are pure functions of the feature columns, so
this is not a refit). ``learned_v1`` has no frozen model binary: without a scored-pairs file
of the recorded run its complete replay is unavailable, and nothing here reconstructs it.

The bundle holds one identifier-free row per test-fold A record, including no-candidate and
reject-tier records, so a policy can be re-applied to the whole population. Before it is
written, :func:`policy.evaluate` at the recorded policy must reproduce every metric of the
evaluation artifact and the review-floor sweep of the sensitivity artifact exactly; a bundle
that does not reconcile is an error, not a warning. ``read_bundle`` loads a committed bundle
back without local data, which is how ``check`` re-verifies it in CI.
"""

from __future__ import annotations

import gzip
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from entity_resolution.config import (
    DATA_DIR,
    LAB_ARTIFACT_DIR,
    LAB_DATA_DIR,
    METHOD_VERSIONS,
    REPO_ROOT,
    SCORED_DIR,
)
from entity_resolution.decision_lab import contracts
from entity_resolution.decision_lab.policy import (
    Policy,
    ReplayRow,
    accept_sweep,
    evaluate,
    floor_sweep,
    legacy_accept_sweep,
)
from entity_resolution.decision_lab.sources import SCORE_KIND, Committed
from entity_resolution.eval import split
from entity_resolution.eval.review_cost import REVIEW_FLOORS
from entity_resolution.models import exact, rules
from entity_resolution.models.tiering import SWEEP_THRESHOLDS

COLUMNS: tuple[str, ...] = (
    "v1",
    "v2",
    "n_candidates",
    "labelled",
    "top1_correct",
    "truth_reachable",
)

LEARNED_UNAVAILABLE_NOTE = (
    "no frozen model; committed and local mappings are rounded to six decimals and omit "
    "reject-tier and no-candidate records; refitting would be a new versioned run, not the "
    "historical snapshot"
)

RECONCILED_METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("test_a", ("test_a",)),
    ("labelled_a", ("labelled_a",)),
    ("labelled_a_reachable", ("labelled_a_reachable",)),
    ("pair_completeness_test", ("pair_completeness_test",)),
    ("at_auto_accept.accepted", ("at_auto_accept", "accepted")),
    ("at_auto_accept.correct", ("at_auto_accept", "correct")),
    ("at_auto_accept.precision", ("at_auto_accept", "precision")),
    ("at_auto_accept.recall_labelled", ("at_auto_accept", "recall_labelled")),
    ("at_auto_accept.f1", ("at_auto_accept", "f1")),
    ("at_auto_accept_or_review.accepted", ("at_auto_accept_or_review", "accepted")),
    ("at_auto_accept_or_review.correct", ("at_auto_accept_or_review", "correct")),
    ("at_auto_accept_or_review.precision", ("at_auto_accept_or_review", "precision")),
    ("at_auto_accept_or_review.recall_labelled", ("at_auto_accept_or_review", "recall_labelled")),
    ("at_auto_accept_or_review.f1", ("at_auto_accept_or_review", "f1")),
    ("recall_overall", ("recall_overall",)),
    ("coverage", ("coverage",)),
    ("unverified_accepts.count", ("unverified_accepts", "count")),
    ("unverified_accepts.share_of_accepts", ("unverified_accepts", "share_of_accepts")),
    ("ambiguity_rule.review_queue", ("ambiguity_rule", "review_queue")),
    ("ambiguity_rule.decisions_moved_to_review", ("ambiguity_rule", "decisions_moved_to_review")),
    ("tier_shares.auto_accept", ("tier_shares", "auto_accept")),
    ("tier_shares.review", ("tier_shares", "review")),
    ("tier_shares.reject", ("tier_shares", "reject")),
)
"""Every metric of ``eval_<method>.json#metrics`` a replay reproduces, as (label, path)."""

LOCAL_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("pairs/features.parquet", "pairs.features.file_sha256", "local_features"),
    ("pairs/candidates.parquet", "pairs.candidates.file_sha256", "local_candidates"),
    ("sample/truth.parquet", "sample.files.truth.file_sha256", "local_truth"),
    ("sample/a.parquet", "sample.files.a.file_sha256", "local_sample_a"),
)
"""(path under data/, manifest key of its file sha256, source role)."""


class LocalInputError(RuntimeError):
    """A local input is missing or does not hash to the manifest's value."""


class ReplayError(RuntimeError):
    """A replay bundle does not reconcile to the committed artifacts."""


def _manifest_get(manifest: dict[str, Any], dotted: str) -> Any:
    cur: Any = manifest
    for k in dotted.split("."):
        cur = cur[k]
    return cur


def local_input_status(manifest: dict[str, Any], data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    """For each local input: path, expected sha256, whether present and whether it matches."""
    out = []
    for rel, key, role in LOCAL_INPUTS:
        path = data_dir / rel
        expected = _manifest_get(manifest, key)
        present = path.exists()
        actual = contracts.sha256_file(path) if present else None
        out.append(
            {
                "path": f"data/{rel}",
                "role": role,
                "manifest_key": f"artifacts/manifest.json#{key}",
                "expected_sha256": expected,
                "present": present,
                "sha256": actual,
                "verified": present and actual == expected,
            }
        )
    return out


def verify_local_inputs(
    manifest: dict[str, Any], data_dir: Path = DATA_DIR
) -> list[dict[str, Any]]:
    status = local_input_status(manifest, data_dir)
    problems = [
        f"{s['path']}: "
        + (
            "missing"
            if not s["present"]
            else f"sha256 {s['sha256']} != {s['expected_sha256']} ({s['manifest_key']})"
        )
        for s in status
        if not s["verified"]
    ]
    if problems:
        raise LocalInputError(
            "local inputs do not match artifacts/manifest.json: " + "; ".join(problems)
        )
    return [
        {
            "path": s["path"],
            "sha256": s["sha256"],
            "role": s["role"],
            "manifest_key": s["manifest_key"],
        }
        for s in status
    ]


@dataclass(frozen=True)
class LocalInputs:
    """The verified frozen local outputs restricted to the test fold."""

    features_test: pd.DataFrame
    """Every test-fold candidate pair with the feature columns the two rule methods read."""
    truth_sets: dict[str, frozenset[str]]
    test_a_ids: list[str]
    """Every test-fold A record of the sample, ascending."""
    candidate_counts: dict[str, int]
    """Full blocked candidate count per test-fold A record with at least one candidate."""
    inputs: list[dict[str, Any]]
    """Path, sha256, role and manifest key of every verified local file."""


FEATURE_COLUMNS = (
    "title_exact_norm",
    "artist_full_exact",
    "year_diff",
    "title_token_set",
    "artist_token_set",
)


def load_local(c: Committed, data_dir: Path = DATA_DIR) -> LocalInputs:
    inputs = verify_local_inputs(c.manifest, data_dir)
    feats = pd.read_parquet(
        data_dir / "pairs" / "features.parquet",
        columns=["a_id", "b_id", "fold", *FEATURE_COLUMNS],
        filters=[("fold", "==", "test")],
    )
    feats["a_id"] = feats["a_id"].astype(str)
    feats["b_id"] = feats["b_id"].astype(str)
    cands = pd.read_parquet(
        data_dir / "pairs" / "candidates.parquet",
        columns=["a_id", "fold"],
        filters=[("fold", "==", "test")],
    )
    counts = cands["a_id"].astype(str).value_counts()
    candidate_counts = {str(a): int(n) for a, n in counts.items()}
    feat_counts = feats["a_id"].value_counts()
    if {str(a): int(n) for a, n in feat_counts.items()} != candidate_counts:
        raise LocalInputError("features.parquet and candidates.parquet disagree on test-fold pairs")
    truth = pd.read_parquet(
        data_dir / "sample" / "truth.parquet", columns=["a_id", "b_id", "status"]
    )
    truth = truth[truth["status"] == "truth_in_sample"]
    sets: dict[str, set[str]] = {}
    for a, b in zip(truth["a_id"].astype(str), truth["b_id"].astype(str), strict=True):
        sets.setdefault(a, set()).add(b)
    a_ids = pd.read_parquet(data_dir / "sample" / "a.parquet", columns=["native_id"])[
        "native_id"
    ].astype(str)
    folds = split.assign(a_ids)
    test_a_ids = sorted(a_ids[folds.to_numpy() == "test"].tolist())
    expected = int(c.split["folds"]["test"]["a_records"])
    if len(test_a_ids) != expected:
        raise LocalInputError(
            f"{len(test_a_ids)} test-fold A records in a.parquet, split.json says {expected}"
        )
    if len(set(test_a_ids)) != len(test_a_ids):
        raise LocalInputError("duplicate A ids in a.parquet")
    unknown = set(candidate_counts) - set(test_a_ids)
    if unknown:
        raise LocalInputError(f"{len(unknown)} test-fold candidate A ids are not sampled A records")
    return LocalInputs(
        features_test=feats,
        truth_sets={a: frozenset(v) for a, v in sets.items()},
        test_a_ids=test_a_ids,
        candidate_counts=candidate_counts,
        inputs=inputs,
    )


@dataclass(frozen=True)
class MethodReplay:
    method_version: str
    decision_value_kind: str
    value_source: str
    """``recomputed_from_features`` or ``scored_pairs``."""
    a_ids: list[str]
    chosen_b: list[str | None]
    rows: list[ReplayRow]
    inputs: list[dict[str, Any]]

    def by_a_id(self) -> dict[str, tuple[str | None, ReplayRow]]:
        return dict(zip(self.a_ids, zip(self.chosen_b, self.rows, strict=True), strict=True))


def scored_pairs_available(
    c: Committed, method_version: str, scored_dir: Path = SCORED_DIR
) -> Path | None:
    """The unrounded scored-pairs parquet of the recorded run, when the methods stage wrote it
    for this run and the file hashes to the recorded value; otherwise ``None``."""
    import json

    path = scored_dir / f"scored_{method_version}.parquet"
    sidecar = scored_dir / f"scored_{method_version}.json"
    if not path.exists() or not sidecar.exists():
        return None
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    if meta.get("run_id") != c.run_id or meta.get("method_version") != method_version:
        return None
    digest = contracts.sha256_file(path)
    if meta.get("file_sha256") != digest:
        return None
    recorded = c.methods[method_version].get("parameters", {}).get("scored_pairs")
    if recorded is not None and recorded.get("file_sha256") != digest:
        return None
    return path


def _rows_from_values(
    pairs: pd.DataFrame, values: np.ndarray, local: LocalInputs, method_version: str, source: str
) -> MethodReplay:
    """``pairs`` has ``a_id``/``b_id`` strings aligned with ``values``; the rest of the
    population (A records without candidates) comes from ``local.test_a_ids``."""
    frame = pd.DataFrame(
        {"a_id": pairs["a_id"].to_numpy(), "b_id": pairs["b_id"].to_numpy(), "v": values}
    )
    if not np.isfinite(frame["v"].to_numpy()).all():
        raise ReplayError(f"{method_version}: non-finite decision values")
    ordered = frame.sort_values(
        ["a_id", "v", "b_id"], ascending=[True, False, True], kind="mergesort"
    )
    g = ordered.groupby("a_id", sort=True)
    first = g.nth(0).set_index("a_id")
    second = g.nth(1).set_index("a_id")["v"]
    sizes = g.size()
    truth = local.truth_sets
    truth_hit = np.fromiter(
        (b in truth.get(a, frozenset()) for a, b in zip(frame["a_id"], frame["b_id"], strict=True)),
        dtype=bool,
        count=len(frame),
    )
    reachable = set(frame["a_id"].to_numpy()[truth_hit].tolist())
    v1 = first["v"].to_dict()
    b1 = first["b_id"].to_dict()
    v2 = second.to_dict()
    n = sizes.to_dict()
    a_ids, chosen, rows = [], [], []
    for a in local.test_a_ids:
        labelled = a in truth
        if a in v1:
            b = str(b1[a])
            row = ReplayRow(
                v1=float(v1[a]),
                v2=float(v2[a]) if a in v2 else None,
                n_candidates=int(n[a]),
                labelled=labelled,
                top1_correct=(b in truth[a]) if labelled else None,
                truth_reachable=(a in reachable) if labelled else None,
            )
        else:
            b = None
            row = ReplayRow(None, None, 0, labelled, None, False if labelled else None)
        a_ids.append(a)
        chosen.append(b)
        rows.append(row)
    return MethodReplay(
        method_version=method_version,
        decision_value_kind=SCORE_KIND[method_version],
        value_source=source,
        a_ids=a_ids,
        chosen_b=chosen,
        rows=rows,
        inputs=list(local.inputs),
    )


def compute_method(
    c: Committed, local: LocalInputs, method_version: str, scored_dir: Path = SCORED_DIR
) -> MethodReplay | None:
    """The replay rows of ``method_version`` over the test population, or ``None`` when no
    frozen decision values exist for it (learned_v1 without a scored-pairs file)."""
    scored = scored_pairs_available(c, method_version, scored_dir)
    if scored is not None:
        sp = pd.read_parquet(
            scored,
            columns=["a_id", "b_id", "fold", "probability"],
            filters=[("fold", "==", "test")],
        )
        sp["a_id"] = sp["a_id"].astype(str)
        sp["b_id"] = sp["b_id"].astype(str)
        if len(sp) != len(local.features_test):
            raise ReplayError(
                f"{method_version}: scored pairs do not cover the test-fold candidate pairs"
            )
        replay = _rows_from_values(
            sp, sp["probability"].to_numpy(dtype="float64"), local, method_version, "scored_pairs"
        )
        return MethodReplay(
            **{
                **replay.__dict__,
                "inputs": replay.inputs
                + [
                    {
                        "path": scored.relative_to(REPO_ROOT).as_posix(),
                        "sha256": contracts.sha256_file(scored),
                        "role": "local_scored_pairs",
                    }
                ],
            }
        )
    feats = local.features_test
    if method_version == "exact_v1":
        values = exact.score(feats)
    elif method_version == "rules_v1":
        values = rules.score(feats)
    else:
        return None
    return _rows_from_values(feats, values, local, method_version, "recomputed_from_features")


# ---- bundle files ------------------------------------------------------------------------


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def bundle_bytes(rows: list[ReplayRow]) -> bytes:
    """The csv.gz bytes of a bundle: fixed header, ``repr`` floats, empty nulls, ``true``/
    ``false`` booleans, gzip level 9 with mtime 0 and no filename, so identical rows give
    identical bytes."""
    text = io.StringIO()
    text.write(",".join(COLUMNS) + "\n")
    for r in rows:
        text.write(
            ",".join(
                (
                    _cell(r.v1),
                    _cell(r.v2),
                    str(r.n_candidates),
                    _cell(r.labelled),
                    _cell(r.top1_correct),
                    _cell(r.truth_reachable),
                )
            )
            + "\n"
        )
    raw = text.getvalue().encode("ascii")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    return buf.getvalue()


def _parse_float(s: str) -> float | None:
    return None if s == "" else float(s)


def _parse_bool(s: str) -> bool | None:
    if s == "":
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    raise ReplayError(f"bad boolean cell {s!r}")


def read_bundle(path: Path) -> list[ReplayRow]:
    """Load a committed bundle back into replay rows (no local data needed)."""
    with gzip.open(path, "rt", encoding="ascii", newline="") as fh:
        header = fh.readline().rstrip("\n")
        if header != ",".join(COLUMNS):
            raise ReplayError(f"{path.name}: unexpected header {header!r}")
        rows = []
        for line in fh:
            cells = line.rstrip("\n").split(",")
            if len(cells) != len(COLUMNS):
                raise ReplayError(f"{path.name}: bad row {line!r}")
            rows.append(
                ReplayRow(
                    v1=_parse_float(cells[0]),
                    v2=_parse_float(cells[1]),
                    n_candidates=int(cells[2]),
                    labelled=_parse_bool(cells[3]) or False,
                    top1_correct=_parse_bool(cells[4]),
                    truth_reachable=_parse_bool(cells[5]),
                )
            )
    return rows


def bundle_paths(method_version: str, lab_dir: Path = LAB_ARTIFACT_DIR) -> tuple[Path, Path]:
    return (
        lab_dir / "replay" / f"replay_{method_version}.test.csv.gz",
        lab_dir / "replay" / f"replay_{method_version}.json",
    )


# ---- reconciliation ------------------------------------------------------------------------


def _get(d: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = d
    for k in path:
        cur = cur[k]
    return cur


def reconcile(rows: list[ReplayRow], c: Committed, method_version: str) -> dict[str, Any]:
    """Every metric of the evaluation artifact against a replay at the recorded policy."""
    e = c.evals[method_version]
    m = evaluate(rows, Policy(**c.policy_of(method_version)))
    checks = []
    for label, path in RECONCILED_METRICS:
        r, a = _get(m, path), _get(e["metrics"], path)
        checks.append({"metric": label, "replay": r, "artifact": a, "equal": r == a})
    return {
        "eval_artifact": c.eval_refs[method_version].relpath,
        "eval_artifact_sha256": c.eval_refs[method_version].sha256,
        "all_equal": all(ch["equal"] for ch in checks),
        "checks": checks,
    }


def reconcile_floor_sweep(
    rows: list[ReplayRow], c: Committed, method_version: str
) -> dict[str, Any]:
    policy = c.policy_of(method_version)
    artifact = c.sensitivity["methods"][method_version]["review_floor_sweep"]["points"]
    replay = floor_sweep(
        rows,
        accept_min=policy["accept_min"],
        ambiguity_gap=policy["ambiguity_gap"],
        floors=list(REVIEW_FLOORS),
    )
    equal = len(replay) == len(artifact) and all(
        r == a for r, a in zip(replay, artifact, strict=True)
    )
    return {"all_equal": equal, "points_compared": len(artifact)}


def legacy_divergence(rows: list[ReplayRow], c: Committed, method_version: str) -> dict[str, Any]:
    policy = Policy(**c.policy_of(method_version))
    artifact = {p["threshold"]: p for p in c.sensitivity["methods"][method_version]["points"]}
    thresholds = list(SWEEP_THRESHOLDS)
    legacy = legacy_accept_sweep(rows, baseline=policy, thresholds=thresholds)
    corrected = {
        p["threshold"]: p
        for p in accept_sweep(
            rows,
            review_min=policy.review_min,
            ambiguity_gap=policy.ambiguity_gap,
            thresholds=thresholds,
        )
    }
    points = []
    differing = 0
    max_diff = 0
    for lp in legacy:
        t = lp["threshold"]
        cp = corrected[t]
        ap = artifact.get(t)
        matches = (
            ap is not None
            and ap["accepts"] == lp["accepts"]
            and ap["review_queue"] == lp["review_queue"]
        )
        diff = abs(lp["accepts"] - cp["accepts"])
        if lp["accepts"] != cp["accepts"] or lp["review_queue"] != cp["review_queue"]:
            differing += 1
        max_diff = max(max_diff, diff)
        points.append(
            {
                "threshold": t,
                "legacy_accepts": lp["accepts"],
                "corrected_accepts": cp["accepts"],
                "legacy_review_queue": lp["review_queue"],
                "corrected_review_queue": cp["review_queue"],
                "legacy_matches_artifact": bool(matches),
            }
        )
    return {
        "note": (
            "The legacy sweep (review_sensitivity.json#points) computed the ambiguity-demotion "
            "flag once at the recorded accept threshold and reused it at every swept threshold. "
            "Below the recorded accept_min a record with a top-2 gap under ambiguity_gap and a "
            "value between the threshold and accept_min is accepted by the legacy calculation "
            "but must be review under a faithful replay; at or above the recorded accept_min the "
            "two coincide. legacy_matches_artifact confirms the restated legacy calculation "
            "reproduces the committed points; the corrected columns are the full replay."
        ),
        "thresholds_differing": differing,
        "max_accepts_difference": max_diff,
        "points": points,
    }


def a_id_order_sha256(a_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(a_ids).encode("ascii")).hexdigest()


def build_meta(replay: MethodReplay, c: Committed, population: dict[str, Any]) -> dict[str, Any]:
    rows = replay.rows
    rec = reconcile(rows, c, replay.method_version)
    if not rec["all_equal"]:
        bad = [ch for ch in rec["checks"] if not ch["equal"]]
        raise ReplayError(
            f"{replay.method_version}: replay does not reconcile to the eval artifact: {bad[:5]}"
        )
    fl = reconcile_floor_sweep(rows, c, replay.method_version)
    if not fl["all_equal"]:
        raise ReplayError(
            f"{replay.method_version}: replay floor sweep differs from review_sensitivity.json"
        )
    div = legacy_divergence(rows, c, replay.method_version)
    if not all(p["legacy_matches_artifact"] for p in div["points"]):
        raise ReplayError(
            f"{replay.method_version}: restated legacy sweep does not reproduce review_sensitivity.json"
        )
    expected = int(c.split["folds"]["test"]["a_records"])
    labelled = sum(1 for r in rows if r.labelled)
    reach = sum(1 for r in rows if r.labelled and r.truth_reachable)
    with_c = sum(1 for r in rows if r.n_candidates > 0)
    completeness = {
        "a_records_expected": expected,
        "a_records_in_file": len(rows),
        "with_candidates": with_c,
        "without_candidates": len(rows) - with_c,
        "labelled": labelled,
        "labelled_reachable": reach,
        "conserved": len(rows) == expected == population["a_records"]
        and labelled == population["labelled_a"]
        and reach == population["labelled_a_reachable"],
    }
    if not completeness["conserved"]:
        raise ReplayError(f"{replay.method_version}: population not conserved: {completeness}")
    csv_path, _ = bundle_paths(replay.method_version)
    meta = {
        "lab_replay_version": "1.0",
        "snapshot_id": c.snapshot_id,
        "method_version": replay.method_version,
        "decision_value_kind": replay.decision_value_kind,
        "file": csv_path.name,
        "columns": list(COLUMNS),
        "rows": len(rows),
        "population": population,
        "completeness": completeness,
        "inputs": replay.inputs,
        "native_policy": c.policy_of(replay.method_version),
        "reconciliation": rec,
        "floor_sweep_reconciliation": fl,
        "legacy_sweep_divergence": div,
        "a_id_order_sha256": a_id_order_sha256(replay.a_ids),
        "note": (
            f"Decision values {replay.value_source.replace('_', ' ')} of the recorded run "
            f"({replay.decision_value_kind}); unrounded; one row per test-fold A record in "
            "ascending A id order, identifiers omitted. The full-fidelity table with A and "
            "chosen B ids stays local under data/lab/ and is tied to this file by "
            "a_id_order_sha256."
        ),
    }
    contracts.validate(meta, "lab_replay_meta")
    contracts.assert_no_forbidden_keys(meta, f"replay_{replay.method_version}.json")
    return meta


def write_bundle(
    replay: MethodReplay,
    c: Committed,
    population: dict[str, Any],
    lab_dir: Path = LAB_ARTIFACT_DIR,
    lab_data_dir: Path = LAB_DATA_DIR,
) -> dict[str, Any]:
    """Write the csv.gz, the metadata and the local full-fidelity parquet; return the meta."""
    meta = build_meta(replay, c, population)
    csv_path, meta_path = bundle_paths(replay.method_version, lab_dir)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(bundle_bytes(replay.rows))
    contracts.write_canonical(meta_path, meta)
    lab_data_dir.mkdir(parents=True, exist_ok=True)
    full = pd.DataFrame(
        {
            "a_id": replay.a_ids,
            "b_id": pd.array(replay.chosen_b, dtype="string"),
            "v1": pd.array([r.v1 for r in replay.rows], dtype="Float64"),
            "v2": pd.array([r.v2 for r in replay.rows], dtype="Float64"),
            "n_candidates": [r.n_candidates for r in replay.rows],
            "labelled": [r.labelled for r in replay.rows],
            "top1_correct": pd.array([r.top1_correct for r in replay.rows], dtype="boolean"),
            "truth_reachable": pd.array([r.truth_reachable for r in replay.rows], dtype="boolean"),
        }
    )
    full.to_parquet(
        lab_data_dir / f"replay_{replay.method_version}.parquet",
        index=False,
        engine="pyarrow",
        compression="zstd",
    )
    return meta


def verify_bundle(
    method_version: str, c: Committed, population: dict[str, Any], lab_dir: Path = LAB_ARTIFACT_DIR
) -> list[str]:
    """Re-verify a committed bundle without local data: row count, reconciliation to the
    evaluation artifact, floor sweep and legacy divergence, all against its metadata."""
    import json

    csv_path, meta_path = bundle_paths(method_version, lab_dir)
    problems: list[str] = []
    if not csv_path.exists() or not meta_path.exists():
        return [f"replay bundle for {method_version} incomplete"]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    problems += [
        f"{meta_path.name}: {p}" for p in contracts.validation_errors(meta, "lab_replay_meta")
    ]
    if problems:
        return problems
    rows = read_bundle(csv_path)
    if meta["rows"] != len(rows):
        problems.append(f"{csv_path.name}: {len(rows)} rows, metadata says {meta['rows']}")
    if len(rows) != population["a_records"]:
        problems.append(
            f"{csv_path.name}: {len(rows)} rows, population has {population['a_records']}"
        )
    if meta["snapshot_id"] != c.snapshot_id:
        problems.append(f"{meta_path.name}: snapshot_id {meta['snapshot_id']} != {c.snapshot_id}")
    if meta["population"] != population:
        problems.append(f"{meta_path.name}: population block differs from the snapshot")
    if meta["native_policy"] != c.policy_of(method_version):
        problems.append(f"{meta_path.name}: native policy differs from the method record")
    rec = reconcile(rows, c, method_version)
    if not rec["all_equal"]:
        problems.append(
            f"{csv_path.name}: replay at the native policy does not reconcile to eval_{method_version}.json"
        )
    if rec != meta["reconciliation"]:
        problems.append(
            f"{meta_path.name}: reconciliation block differs from a fresh reconciliation"
        )
    fl = reconcile_floor_sweep(rows, c, method_version)
    if not fl["all_equal"] or fl != meta["floor_sweep_reconciliation"]:
        problems.append(
            f"{csv_path.name}: floor sweep does not reconcile to review_sensitivity.json"
        )
    div = legacy_divergence(rows, c, method_version)
    if div != meta["legacy_sweep_divergence"]:
        problems.append(
            f"{meta_path.name}: legacy sweep divergence differs from a fresh computation"
        )
    if bundle_bytes(rows) != csv_path.read_bytes():
        problems.append(f"{csv_path.name}: bytes are not the canonical serialisation of its rows")
    return problems


def capability_note(method_version: str, available: bool, value_source: str | None) -> str:
    if not available:
        return (
            LEARNED_UNAVAILABLE_NOTE
            if method_version == "learned_v1"
            else "replay bundle not exported"
        )
    if value_source == "scored_pairs":
        return "unrounded decision values of the recorded run from data/scored/, one row per test-fold A record"
    return (
        f"{method_version} decision values are a pure function of the frozen features "
        "(recomputed, not refitted); one row per test-fold A record including no-candidate and "
        "reject-tier records; reconciled exactly to the evaluation artifact at the recorded policy"
    )


def methods_with_bundles(lab_dir: Path = LAB_ARTIFACT_DIR) -> list[str]:
    return [m for m in METHOD_VERSIONS if all(p.exists() for p in bundle_paths(m, lab_dir))]
