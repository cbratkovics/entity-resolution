-- Grain: one row per (a_id, method_version): the committed mapping exhibits, typed and
-- deduplicated. A duplicate (a_id, method_version), which the pipeline never writes, would
-- keep the row with the highest probability, then the lowest b_id, so the rule is stated.
with typed as (
    select
        a_id,
        b_id,
        method_version,
        feature_version,
        score,
        probability,
        tier,
        block_keys,
        top2_gap,
        fold,
        run_id,
        decided_at_utc,
        row_number() over (
            partition by a_id, method_version
            order by probability desc, b_id asc
        ) as rn
    from {{ ref('brz_mapping') }}
)

select
    a_id,
    b_id,
    method_version,
    feature_version,
    score,
    probability,
    tier,
    block_keys,
    top2_gap,
    fold,
    run_id,
    decided_at_utc
from typed
where rn = 1
