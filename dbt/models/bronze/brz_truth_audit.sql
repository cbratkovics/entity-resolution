{{ config(materialized='table') }}

-- artifacts/truth_audit.json as one row (the current run). Before the first full build there is
-- no audit and the model is an empty, typed relation.
{% set columns = [
    ['source_file', 'varchar'], ['audit_version', 'varchar'], ['generated_at_utc', 'timestamp'],
    ['feature_version', 'varchar'], ['code_commit', 'varchar'], ['scope_primary_type', 'varchar'],
    ['links_raw', 'integer'], ['links_distinct', 'integer'], ['duplicate_links', 'integer'],
    ['truth_dead', 'integer'], ['truth_out_of_scope', 'integer'], ['truth_unsampled', 'integer'],
    ['truth_in_sample', 'integer'], ['truth_dead_rate', 'double'],
    ['in_sample_pairs', 'integer'], ['in_sample_a_records', 'integer'], ['in_sample_b_records', 'integer'],
    ['one_to_many_a', 'integer'], ['one_to_many_a_rate', 'double'],
    ['one_to_many_b', 'integer'], ['one_to_many_b_rate', 'double']
] %}
{% if files_exist(var('artifacts_dir') ~ '/truth_audit.json') %}
select
    filename as source_file,
    cast(audit_version as varchar) as audit_version,
    cast(generated_at_utc as timestamp) as generated_at_utc,
    cast(feature_version as varchar) as feature_version,
    cast(code_commit as varchar) as code_commit,
    cast(scope_primary_type as varchar) as scope_primary_type,
    cast(links_raw as integer) as links_raw,
    cast(links_distinct as integer) as links_distinct,
    cast(duplicate_links as integer) as duplicate_links,
    cast(truth_dead as integer) as truth_dead,
    cast(truth_out_of_scope as integer) as truth_out_of_scope,
    cast(truth_unsampled as integer) as truth_unsampled,
    cast(truth_in_sample as integer) as truth_in_sample,
    cast(truth_dead_rate as double) as truth_dead_rate,
    cast(in_sample.pairs as integer) as in_sample_pairs,
    cast(in_sample.a_records as integer) as in_sample_a_records,
    cast(in_sample.b_records as integer) as in_sample_b_records,
    cast(in_sample.one_to_many_a as integer) as one_to_many_a,
    cast(in_sample.one_to_many_a_rate as double) as one_to_many_a_rate,
    cast(in_sample.one_to_many_b as integer) as one_to_many_b,
    cast(in_sample.one_to_many_b_rate as double) as one_to_many_b_rate
from {{ source('artifacts', 'truth_audit') }}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
