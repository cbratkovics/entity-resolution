{{ config(materialized='table') }}

-- The Decision Lab's curated case selection (artifacts/lab/case_selection.json, ADR 0006): one
-- row per selected test-fold A record with the deterministic reason codes that selected it.
-- Identifiers and controlled codes only. Empty until `make lab-export` has run.
{% set columns = [
    ['source_file', 'varchar'], ['case_id', 'varchar'], ['a_id', 'varchar'],
    ['reason_codes', 'varchar'], ['selection_rank', 'bigint']
] %}
{% if files_exist(var('artifacts_dir') ~ '/lab/case_selection.json') %}
select
    filename as source_file,
    cast(case_id as varchar) as case_id,
    cast(a_id as varchar) as a_id,
    array_to_string(reason_codes, '|') as reason_codes,
    cast(selection_rank as bigint) as selection_rank
from {{ source('artifacts', 'lab_case_selection') }}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
