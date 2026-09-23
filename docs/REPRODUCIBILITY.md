# Reproducibility

## From a clean clone (no data)

```
git clone https://github.com/cbratkovics/entity-resolution
cd entity-resolution
make setup lint test dbt docs
```

`make smoke` does exactly this in a temporary directory, overlaying uncommitted changes, so a
step that depends on a file that exists only on one machine fails locally before it fails in
CI.

## The full build (owner-run)

`make full` runs `entity_resolution.pipeline.match`: download the dumps recorded in
`artifacts/manifest.json` (free disk is checked and printed first), stream-extract the ten
MusicBrainz tables, load both sides, classify the truth links, draw the deterministic sample,
run the contracts, block, split, compute pair features, fit and evaluate the three methods, and
write every artifact. It is owner-run on a machine with at least `20 GiB` of free disk and
`12 GiB` of memory (measured figures below); the repository's `verify` workflow checks the
committed artifacts without running it.

```
make setup
make full                 # exits 4 when the too-good-to-be-true rule fires; the audit is `make test`
make test                 # the real-sample leakage checks run once data/ exists
make dbt docs             # warehouse, exports, cards and number checks against the new artifacts
```

The deterministic sample (`sha256(source || native_id)` against a threshold in the manifest) and
the hash-based fold split mean that a rerun on the same dumps reproduces the artifacts byte for
byte, apart from timestamps and the run id.

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
options (pyarrow, zstd, no index). `code_commit` in the manifest is the HEAD the run started
from; the run's own code lands in the next commit, so the tree that produced a set of artifacts
is the commit after the one they name.

## Can a hosted runner run the full build? (measured; owner-run)

The committed manifest's run recorded a peak `data/` size of 14,784,312,081 bytes
(`13.77 GiB`) and a peak resident set of 9,929,076,736 bytes (`9.25 GiB`), the
latter reached in the pair-feature stage. <!-- cite: artifacts/manifest.json#runtime.data_dir_bytes_peak; artifacts/manifest.json#runtime.peak_rss_bytes -->
Of the disk, the MusicBrainz archive is 7,542,238,956 bytes and its ten extracted tables
4,795,695,166 bytes. <!-- cite: artifacts/manifest.json#sources[1].dump_bytes; artifacts/manifest.json#sources[1].extract.extracted_bytes -->
That run took 780.8 seconds with the loaders' parquet caches already present; the sample
stage took 170.1 seconds, blocking 67.2 seconds, pair features
297.9 seconds and the three methods together 186.4 seconds.
<!-- cite: artifacts/manifest.json#runtime.total_seconds; artifacts/manifest.json#runtime.stages[4].seconds; artifacts/manifest.json#runtime.stages[7].seconds; artifacts/manifest.json#runtime.stages[9].seconds; artifacts/manifest.json#runtime.stages[10].seconds -->
A cold run adds the Discogs parse and the MusicBrainz load (about two minutes on this machine).
At the time of writing GitHub's standard hosted Linux runner for public repositories offers
about `14 GB` of SSD and `16 GB` of memory (older specifications had `7 GB` of memory); disk
is the binding constraint either way, since the extracted tables alone approach it. The full
build is therefore owner-run on a machine with at least `20 GiB` free and `12 GiB` of memory;
the `verify` workflow checks the committed artifacts instead, and the extraction change that
would fit a runner is on the roadmap.

## Warehouse determinism

DuckDB's parallel aggregation order is not deterministic, so exported values can differ at the
1e-15 level between builds. Set `ENTITY_RESOLUTION_DUCKDB_THREADS=1` when comparing exports.

## Toolchain

`uv.lock` pins every Python package; `make setup` installs it frozen. `dbt-core`, `dbt-duckdb`
and `duckdb` are pinned exactly in `pyproject.toml` so local, CI and full builds run the same
engine.
