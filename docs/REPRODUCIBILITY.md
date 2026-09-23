# Reproducibility

## From a clean clone (no data)

```
git clone https://github.com/cbratkovics/entity-resolution
cd entity-resolution
make setup lint test dbt docs
```

`make smoke` does exactly this in a temporary directory, overlaying uncommitted changes, so a
step that depends on a file that exists only on one machine fails locally before it fails in
CI. Expected runtimes are measured in Phase 6 and recorded here.

## The full build

`make full` downloads the dumps recorded in `artifacts/manifest.json`, verifies their sha256,
and regenerates every artifact. It is not built before Phase 4; until then it exits with the
phase it is waiting for. The deterministic sample (`sha256(source || native_id)` against a
threshold in the manifest) and the hash-based fold split mean that a rerun on the same dumps
reproduces the artifacts byte for byte, apart from timestamps.

## The two-run gate

Phase 2 is accepted only when `make full` run twice, with the parquet caches deleted between
runs so the loaders execute again, produces `data/sample/a.parquet`, `b.parquet` and
`truth.parquet` that are identical both by file bytes and by content hash (rows sorted by every
column, list columns joined, hashed with pandas' row hasher; `manifest.json#sample.files`).
The manifest records both hashes; `tests/test_features_no_leakage.py` recomputes the content
hash and the membership thresholds from the files on disk, and
`scripts/check_reproducibility.py <snapshot_dir>` compares a saved run with the current one
(a byte difference with identical content is reported as writer metadata; a content
difference fails). Parquet is written with fixed
options (pyarrow, zstd, no index).

## Warehouse determinism

DuckDB's parallel aggregation order is not deterministic, so exported values can differ at the
1e-15 level between builds. Set `ENTITY_RESOLUTION_DUCKDB_THREADS=1` when comparing exports.

## Toolchain

`uv.lock` pins every Python package; `make setup` installs it frozen. `dbt-core`, `dbt-duckdb`
and `duckdb` are pinned exactly in `pyproject.toml` so local, CI and full builds run the same
engine.
