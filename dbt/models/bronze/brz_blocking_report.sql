{{ config(materialized='table') }}

-- artifacts/blocking_report.json as one row per block key, with the union figures repeated on
-- every row. Empty until the first full build reaches the blocking stage.
{% set keys = ['k_title3', 'k_artist_year', 'k_title_sorted', 'k_phonetic', 'k_self_titled'] %}
{% set columns = [
    ['source_file', 'varchar'], ['generated_at_utc', 'timestamp'], ['feature_version', 'varchar'],
    ['code_commit', 'varchar'], ['block_key', 'varchar'], ['key_pairs', 'bigint'],
    ['key_pair_completeness', 'double'], ['keys_emitted_a', 'bigint'], ['keys_emitted_b', 'bigint'],
    ['union_pairs', 'bigint'], ['candidate_pairs_after_cap', 'bigint'], ['reduction_ratio', 'double'],
    ['union_pair_completeness', 'double'], ['after_cap_pair_completeness', 'double'],
    ['truth_pairs', 'bigint'], ['truth_pairs_lost_to_cap', 'bigint'],
    ['a_records_over_cap', 'bigint'], ['pairs_dropped', 'bigint'], ['candidate_cap_per_a', 'integer']
] %}
{% if files_exist(var('artifacts_dir') ~ '/blocking_report.json') %}
with report as (
    select * from {{ source('artifacts', 'blocking_report') }}
)

{% for k in keys %}
select
    r.filename as source_file,
    cast(r.generated_at_utc as timestamp) as generated_at_utc,
    cast(r.feature_version as varchar) as feature_version,
    cast(r.code_commit as varchar) as code_commit,
    '{{ k }}' as block_key,
    cast(r.per_key_pairs.{{ k }} as bigint) as key_pairs,
    cast(r.pair_completeness.per_key.{{ k }} as double) as key_pair_completeness,
    cast(r.keys_emitted.a.{{ k }} as bigint) as keys_emitted_a,
    cast(r.keys_emitted.b.{{ k }} as bigint) as keys_emitted_b,
    cast(r.union_pairs as bigint) as union_pairs,
    cast(r.candidate_pairs_after_cap as bigint) as candidate_pairs_after_cap,
    cast(r.reduction_ratio as double) as reduction_ratio,
    cast(r.pair_completeness.union as double) as union_pair_completeness,
    cast(r.pair_completeness.after_cap as double) as after_cap_pair_completeness,
    cast(r.pair_completeness.truth_pairs as bigint) as truth_pairs,
    cast(r.pair_completeness.truth_pairs_lost_to_cap as bigint) as truth_pairs_lost_to_cap,
    cast(r.cap_overflow.a_records_over_cap as bigint) as a_records_over_cap,
    cast(r.cap_overflow.pairs_dropped as bigint) as pairs_dropped,
    cast(r.candidate_cap_per_a as integer) as candidate_cap_per_a
from report as r
{% if not loop.last %}union all{% endif %}
{% endfor %}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
