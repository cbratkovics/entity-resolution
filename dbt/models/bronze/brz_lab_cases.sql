{{ config(materialized='table') }}

-- The evidence rows of the Decision Lab case bundle (artifacts/lab/cases.json#cases[].evidence),
-- flattened to one row per (case_id, method_version). This is the bundle the browser renders;
-- fct_lab_case_evidence rebuilds the same projection from the warehouse's own mapping and
-- assert_lab_case_evidence_reconciles_to_bundle proves the two agree. Read through the JSON
-- functions because exported and not-exported rows have different shapes. Empty until
-- `make lab-export` has run.
{% set columns = [
    ['source_file', 'varchar'], ['snapshot_id', 'varchar'], ['case_id', 'varchar'], ['a_id', 'varchar'],
    ['method_version', 'varchar'], ['exported', 'boolean'], ['not_exported_reason', 'varchar'],
    ['b_id', 'varchar'], ['score', 'double'], ['probability', 'double'], ['tier', 'varchar'],
    ['top2_gap', 'double'], ['gap_state', 'varchar'], ['block_keys', 'varchar'],
    ['agreement_class', 'varchar'], ['methods_exported', 'bigint'], ['distinct_chosen_b_ids', 'bigint'],
    ['labels_state', 'varchar']
] %}
{% if files_exist(var('artifacts_dir') ~ '/lab/cases.json') %}
with raw as (
    select
        filename as source_file,
        json
    from {{ source('artifacts', 'lab_cases') }}
),

cases as (
    select
        source_file,
        json_extract_string(json, '$.snapshot_id') as snapshot_id,
        unnest(json_extract(json, '$.cases[*]')) as c
    from raw
),

evidence as (
    select
        source_file,
        snapshot_id,
        c,
        unnest(json_extract(c, '$.evidence[*]')) as e
    from cases
)

select
    source_file,
    snapshot_id,
    json_extract_string(c, '$.case_id') as case_id,
    json_extract_string(c, '$.a_id') as a_id,
    json_extract_string(e, '$.method_version') as method_version,
    cast(json_extract(e, '$.exported') as boolean) as exported,
    json_extract_string(e, '$.reason') as not_exported_reason,
    json_extract_string(e, '$.b_id') as b_id,
    cast(json_extract(e, '$.score') as double) as score,
    cast(json_extract(e, '$.probability') as double) as probability,
    json_extract_string(e, '$.tier') as tier,
    cast(json_extract(e, '$.top2_gap') as double) as top2_gap,
    json_extract_string(e, '$.gap_state') as gap_state,
    array_to_string(from_json(json_extract(e, '$.block_keys'), '["VARCHAR"]'), '|') as block_keys,
    json_extract_string(c, '$.comparison.agreement_class') as agreement_class,
    cast(json_extract(c, '$.comparison.methods_exported') as bigint) as methods_exported,
    cast(json_extract(c, '$.comparison.distinct_chosen_b_ids') as bigint) as distinct_chosen_b_ids,
    json_extract_string(c, '$.labels.state') as labels_state
from evidence
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
