{% docs __overview__ %}

# entity_resolution_dbt — warehouse over the committed artifacts

Record linkage between open music catalogues, measured against labelled ground truth. This is
the analytics layer: a bronze / silver / gold medallion built with dbt Core and dbt-duckdb on a
local DuckDB file. Every source is a committed artifact under `artifacts/` (identifiers, hashes,
parameters, metrics; never a title or an artist credit), so the warehouse builds in CI with no
download and no secret.

## Layers

**Bronze** (`brz_*`) — typed one-to-one copies of the artifact files; every row carries
`source_file`. Families that do not exist yet build as empty, typed relations.

**Silver** (`slv_*`) — grain-enforced long tables: fold counts and metrics per method.

**Gold** — contracted marts the docs site reads: `dim_method_version` and `fct_eval_metrics`
(the results table). Phase 5 adds the mapping, review-queue and blocking marts
(docs/BRIEF.md 2.10).

## How trust is established

- **Artifact reconciliation.** `assert_marts_reconcile_to_eval_artifacts` compares every value
  of `fct_eval_metrics` with the evaluation artifact it came from and fails the build on any
  disagreement above 1e-9. The warehouse cannot publish a number the artifacts do not carry.
- **Baselines present.** `assert_baseline_reconciles_to_eval_artifacts` refuses a build in which
  the learned method is evaluated without `exact_v1` and `rules_v1` beside it.
- **Contracts** on every gold model; every model and column described
  (`scripts/check_dbt_descriptions.py`).

- Repository: https://github.com/cbratkovics/entity-resolution

{% enddocs %}
