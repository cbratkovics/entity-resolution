{{ config(materialized='table') }}

-- One row per method version record. Before the first run there are no records and the model
-- is an empty, typed relation.
{% set columns = [
    ['source_file', 'varchar'], ['record_version', 'varchar'], ['method_version', 'varchar'],
    ['definition', 'varchar'], ['feature_version', 'varchar'], ['code_commit', 'varchar'],
    ['created_at_utc', 'timestamp'], ['auto_accept_min', 'double'], ['review_min', 'double'],
    ['ambiguity_gap', 'double']
] %}
{% if files_exist(var('artifacts_dir') ~ '/methods/*.json') %}
select
    filename as source_file,
    cast(record_version as varchar) as record_version,
    cast(method_version as varchar) as method_version,
    cast(definition as varchar) as definition,
    cast(feature_version as varchar) as feature_version,
    cast(code_commit as varchar) as code_commit,
    cast(created_at_utc as timestamp) as created_at_utc,
    cast(tier_policy.auto_accept_min as double) as auto_accept_min,
    cast(tier_policy.review_min as double) as review_min,
    cast(tier_policy.ambiguity_gap as double) as ambiguity_gap
from {{ source('artifacts', 'method_versions') }}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
