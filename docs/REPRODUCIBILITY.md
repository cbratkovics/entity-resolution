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

## Warehouse determinism

DuckDB's parallel aggregation order is not deterministic, so exported values can differ at the
1e-15 level between builds. Set `ENTITY_RESOLUTION_DUCKDB_THREADS=1` when comparing exports.

## Toolchain

`uv.lock` pins every Python package; `make setup` installs it frozen. `dbt-core`, `dbt-duckdb`
and `duckdb` are pinned exactly in `pyproject.toml` so local, CI and full builds run the same
engine.
