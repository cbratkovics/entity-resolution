{{ config(meta={'export': false}) }}

-- Not exported to docs/site/data: the page never reads it and the JSON would be tens of
-- megabytes on Pages; the audited exhibit is committed under artifacts/mapping/ (ADR 0005).
-- Grain: one row per (a_id, method_version). The auditable mapping: test-fold A records with a
-- non-reject decision per method, from the committed exhibits (ADR 0005). The full mapping over
-- every fold is a `make full` output under data/ and is not in the warehouse.
select
    cast(m.a_id as varchar) as a_id,
    cast(m.b_id as varchar) as b_id,
    cast(m.method_version as varchar) as method_version,
    cast(m.feature_version as varchar) as feature_version,
    cast(m.score as double) as score,
    cast(m.probability as double) as probability,
    cast(m.tier as varchar) as tier,
    cast(m.block_keys as varchar) as block_keys,
    cast(m.top2_gap as double) as top2_gap,
    cast(m.fold as varchar) as fold,
    cast(m.run_id as varchar) as run_id,
    cast(m.decided_at_utc as timestamp) as decided_at_utc
from {{ ref('slv_mapping') }} as m
