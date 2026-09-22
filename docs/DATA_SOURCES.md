# Data sources

## Source

**STUB.** `entity_resolution/data/loader.py` synthesises a deterministic world (60 entities, cohorts
A,B, seasons 2019–2024, 12 periods each, three stats and a rules-based target). Replace it
following docs/TEMPLATE_GUIDE.md and rewrite this file: client and version, the datasets and
columns used, grain, refresh cadence, licence, and what is deliberately not used.

## Grain, seasons, refresh

One row per (`record_id`, `batch`, `batch`). Split: train
2019–2021, validation 2022, test 2023 (whole seasons, forward in time). The scheduled job pulls
through the last completed period on every run.

## Licence

TODO(domain): the source's licence and any attribution it requires.

## What is deliberately not used

TODO(domain).
