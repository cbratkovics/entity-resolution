{{ config(materialized='table') }}

-- One row per evaluation artifact; the nested metric blocks are flattened in silver. Before the
-- first run there are no artifacts and the model is an empty, typed relation.
{% set columns = [
    ['source_file', 'varchar'], ['artifact_version', 'varchar'], ['method_version', 'varchar'],
    ['generated_at_utc', 'timestamp'], ['manifest_sha256', 'varchar'],
    ['feature_version', 'varchar'], ['code_commit', 'varchar'], ['fold_counts', 'json'],
    ['metric_definitions', 'json'], ['metrics', 'json']
] %}
{% if files_exist(var('artifacts_dir') ~ '/eval_*.json') %}
select
    filename as source_file,
    cast(artifact_version as varchar) as artifact_version,
    cast(method_version as varchar) as method_version,
    cast(generated_at_utc as timestamp) as generated_at_utc,
    cast(input.manifest_sha256 as varchar) as manifest_sha256,
    cast(input.feature_version as varchar) as feature_version,
    cast(input.code_commit as varchar) as code_commit,
    to_json(fold_counts) as fold_counts,
    to_json(metric_definitions) as metric_definitions,
    to_json(metrics) as metrics
from {{ source('artifacts', 'eval_artifacts') }}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
