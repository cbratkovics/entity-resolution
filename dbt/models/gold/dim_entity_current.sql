-- Grain: one row per record_id — the current version from the snp_entity snapshot (SCD2).
-- Not exported (meta export=false); downstream marts pick this for "attributes now".
{{ config(materialized='view', meta={'export': false}) }}

select
    cast(record_id as varchar) as record_id,
    cast(record_name as varchar) as record_name,
    cast(source as varchar) as source,
    cast(team as varchar) as team,
    cast(as_of_period_key as integer) as version_from_period_key,
    cast(dbt_valid_from as timestamp) as version_valid_from_utc
from {{ ref('snp_entity') }}
where dbt_valid_to is null
