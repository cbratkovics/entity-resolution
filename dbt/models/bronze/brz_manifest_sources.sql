{{ config(materialized='table') }}

-- The sources block of artifacts/manifest.json, one row per dump. Empty on the empty manifest.
{% set columns = [
    ['source_file', 'varchar'], ['name', 'varchar'], ['side', 'varchar'], ['dump_filename', 'varchar'],
    ['dump_bytes', 'bigint'], ['dump_sha256', 'varchar'], ['dump_date', 'varchar'],
    ['download_url', 'varchar'], ['licence_url', 'varchar']
] %}
with manifest as (
    select * from {{ source('artifacts', 'manifest') }}
),

exploded as (
    select
        m.filename as source_file,
        unnest(m.sources) as src
    from manifest as m
)

select
    e.source_file,
    cast(e.src.name as varchar) as name,
    cast(e.src.side as varchar) as side,
    cast(e.src.dump_filename as varchar) as dump_filename,
    cast(e.src.dump_bytes as bigint) as dump_bytes,
    cast(e.src.dump_sha256 as varchar) as dump_sha256,
    cast(e.src.dump_date as varchar) as dump_date,
    cast(e.src.download_url as varchar) as download_url,
    cast(e.src.licence_url as varchar) as licence_url
from exploded as e
