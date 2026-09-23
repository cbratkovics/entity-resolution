{{ config(materialized='table') }}

-- artifacts/split.json as one row per fold. Empty until the first full build reaches the split.
{% set columns = [
    ['source_file', 'varchar'], ['generated_at_utc', 'timestamp'], ['feature_version', 'varchar'],
    ['code_commit', 'varchar'], ['rule', 'varchar'], ['fold', 'varchar'], ['bucket_low', 'integer'],
    ['bucket_high', 'integer'], ['a_records', 'bigint'], ['labelled_a_records', 'bigint'],
    ['truth_pairs', 'bigint'], ['candidate_pairs', 'bigint']
] %}
{% if files_exist(var('artifacts_dir') ~ '/split.json') %}
with report as (
    select * from {{ source('artifacts', 'split') }}
)

{% for f in var('folds') %}
select
    r.filename as source_file,
    cast(r.generated_at_utc as timestamp) as generated_at_utc,
    cast(r.feature_version as varchar) as feature_version,
    cast(r.code_commit as varchar) as code_commit,
    cast(r.rule as varchar) as rule,
    '{{ f }}' as fold,
    cast(r.bounds.{{ f }}[1] as integer) as bucket_low,
    cast(r.bounds.{{ f }}[2] as integer) as bucket_high,
    cast(r.folds.{{ f }}.a_records as bigint) as a_records,
    cast(r.folds.{{ f }}.labelled_a_records as bigint) as labelled_a_records,
    cast(r.folds.{{ f }}.truth_pairs as bigint) as truth_pairs,
    cast(r.folds.{{ f }}.candidate_pairs as bigint) as candidate_pairs
from report as r
{% if not loop.last %}union all{% endif %}
{% endfor %}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
