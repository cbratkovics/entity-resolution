{{ config(materialized='table') }}

-- artifacts/manifest.json as one row. Always present: an empty tree still has a manifest.
select
    filename as source_file,
    cast(manifest_version as varchar) as manifest_version,
    cast(feature_version as varchar) as feature_version,
    cast(code_commit as varchar) as code_commit,
    cast(side_a as varchar) as side_a,
    cast(run_id as varchar) as run_id,
    cast(updated_at_utc as timestamp) as updated_at_utc,
    cast(len(sources) as integer) as n_sources
from {{ source('artifacts', 'manifest') }}
