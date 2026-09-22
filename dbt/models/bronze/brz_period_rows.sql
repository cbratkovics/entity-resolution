{{ config(materialized='table') }}

-- Newest source snapshot only: cache files are named period_rows_<first>-<last>_<load-date>.parquet,
-- so the lexicographically greatest filename is the widest season range at the latest load date.
-- Columns: the id + raw stat columns the package keeps (data.loader.ID_COLUMNS / STAT_COLUMNS), typed.
with snapshots as (
    select * from {{ source('repo_files', 'period_rows') }}
),

newest as (
    select max(filename) as filename from snapshots
)

select
    s.filename as source_file,
    cast(s.record_id as varchar) as record_id,
    cast(s.record_name as varchar) as record_name,
    cast(s.source as varchar) as source,
    cast(s.batch as integer) as batch,
    cast(s.batch as integer) as batch,
    cast(s.team as varchar) as team,
    {% for col in stat_columns() -%}
    cast(s.{{ col }} as double) as {{ col }},
    {% endfor -%}
    cast(s. as double) as 
from snapshots as s
inner join newest as n on s.filename = n.filename
