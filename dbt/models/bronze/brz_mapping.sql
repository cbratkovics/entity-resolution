{{ config(materialized='table') }}

-- The committed mapping exhibits (test fold, non-reject decisions, ADR 0005), one row per
-- (a_id, method_version). Empty until the first full build reaches the methods stage.
{% set columns = [
    ['source_file', 'varchar'], ['a_id', 'varchar'], ['b_id', 'varchar'], ['method_version', 'varchar'],
    ['feature_version', 'varchar'], ['score', 'double'], ['probability', 'double'], ['tier', 'varchar'],
    ['block_keys', 'varchar'], ['top2_gap', 'double'], ['fold', 'varchar'], ['run_id', 'varchar'],
    ['decided_at_utc', 'timestamp']
] %}
{% if files_exist(var('artifacts_dir') ~ '/mapping/mapping_*.test.csv.gz') %}
select
    filename as source_file,
    cast(a_id as varchar) as a_id,
    cast(b_id as varchar) as b_id,
    cast(method_version as varchar) as method_version,
    cast(feature_version as varchar) as feature_version,
    cast(score as double) as score,
    cast(probability as double) as probability,
    cast(tier as varchar) as tier,
    cast(block_keys as varchar) as block_keys,
    try_cast(top2_gap as double) as top2_gap,
    cast(fold as varchar) as fold,
    cast(run_id as varchar) as run_id,
    cast(decided_at_utc as timestamp) as decided_at_utc
from {{ source('artifacts', 'mapping') }}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
