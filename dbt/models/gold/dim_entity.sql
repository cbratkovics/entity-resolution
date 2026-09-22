-- Grain: one row per record_id. Current (latest-seen) attributes, no history (history:
-- snapshot snp_entity, views dim_entity_current / dim_entity_asof). Newest source row wins;
-- entities known only from a prediction file fall back to it.
with from_rows as (
    select
        record_id,
        record_name,
        source,
        team,
        min(batch) over (partition by record_id) as first_season,
        batch as last_season,
        batch as last_period,
        count(*) over (partition by record_id) as rows_played,
        row_number() over (partition by record_id order by period_key desc) as rn
    from {{ ref('slv_period_rows') }}
),

from_predictions as (
    select
        record_id,
        record_name,
        source,
        team,
        row_number() over (partition by record_id order by period_key desc, candidate asc) as rn
    from {{ ref('slv_predictions') }}
),

ids as (
    select record_id from from_rows
    union
    select record_id from from_predictions
)

select
    cast(i.record_id as varchar) as record_id,
    cast(coalesce(r.record_name, p.record_name) as varchar) as record_name,
    cast(coalesce(r.source, p.source) as varchar) as source,
    cast(coalesce(r.team, p.team) as varchar) as team,
    cast(r.first_season as integer) as first_season,
    cast(r.last_season as integer) as last_season,
    cast(r.last_period as integer) as last_period,
    cast(coalesce(r.rows_played, 0) as integer) as rows_played,
    cast(case when r.record_id is not null then 'rows' else 'predictions' end as varchar) as attribute_source
from ids as i
left join from_rows as r on i.record_id = r.record_id and r.rn = 1
left join from_predictions as p on i.record_id = p.record_id and p.rn = 1
