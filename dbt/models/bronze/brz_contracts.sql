{{ config(materialized='table') }}

-- artifacts/contracts.json flattened to one row per (side, check). Before the first full build
-- there is no report and the model is an empty, typed relation.
{% set columns = [
    ['source_file', 'varchar'], ['contracts_version', 'varchar'], ['generated_at_utc', 'timestamp'],
    ['report_ok', 'boolean'], ['side', 'varchar'], ['side_ok', 'boolean'], ['rows', 'integer'],
    ['check_name', 'varchar'], ['check_ok', 'boolean']
] %}
{% if files_exist(var('artifacts_dir') ~ '/contracts.json') %}
with report as (
    select * from {{ source('artifacts', 'contracts') }}
),

sides as (
    {% for side in ['musicbrainz', 'discogs'] %}
    select
        r.filename as source_file,
        cast(r.contracts_version as varchar) as contracts_version,
        cast(r.generated_at_utc as timestamp) as generated_at_utc,
        cast(r.ok as boolean) as report_ok,
        '{{ side }}' as side,
        cast(r.sides.{{ side }}.ok as boolean) as side_ok,
        cast(r.sides.{{ side }}.summary.rows as integer) as rows,
        unnest(r.sides.{{ side }}.checks) as check_struct
    from report as r
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    s.source_file,
    s.contracts_version,
    s.generated_at_utc,
    s.report_ok,
    s.side,
    s.side_ok,
    s.rows,
    cast(s.check_struct.name as varchar) as check_name,
    cast(s.check_struct.ok as boolean) as check_ok
from sides as s
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
