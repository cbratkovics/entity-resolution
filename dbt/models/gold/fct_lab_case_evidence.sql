-- Grain: one row per (case_id, method_version) for the Decision Lab's curated cases (ADR 0006):
-- the evidence each method exported for the case, projected from the warehouse's own test-fold
-- mapping (fct_mapping) joined to the case selection, so the lab's case bundle is provable
-- against the marts rather than a second copy of the exhibits. A method that exported nothing
-- for the case (reject tier or no candidate, ADR 0005) has exported = false and null evidence.
-- ambiguity_demoted_derived is computed from the six-decimal exported values and is null when
-- the gap is null; a gap equal to the ambiguity threshold at six decimals cannot be classified
-- from the exhibit (gap_at_rounded_boundary).
with selection as (
    select
        case_id,
        a_id,
        reason_codes,
        selection_rank
    from {{ ref('brz_lab_case_selection') }}
),

methods as (
    select
        method_version,
        auto_accept_min,
        review_min,
        ambiguity_gap
    from {{ ref('dim_method_version') }}
),

grid as (
    select
        s.case_id,
        s.a_id,
        s.reason_codes,
        s.selection_rank,
        m.method_version,
        m.auto_accept_min,
        m.review_min,
        m.ambiguity_gap
    from selection as s
    cross join methods as m
),

joined as (
    select
        g.case_id,
        g.a_id,
        g.reason_codes,
        g.selection_rank,
        g.method_version,
        g.auto_accept_min,
        g.review_min,
        g.ambiguity_gap,
        f.b_id,
        f.score,
        f.probability,
        f.tier,
        f.top2_gap,
        f.block_keys,
        f.run_id,
        f.decided_at_utc,
        f.b_id is not null as exported
    from grid as g
    left join {{ ref('fct_mapping') }} as f
        on g.a_id = f.a_id and g.method_version = f.method_version
)

select
    cast(case_id as varchar) as case_id,
    cast(a_id as varchar) as a_id,
    cast(method_version as varchar) as method_version,
    cast(reason_codes as varchar) as reason_codes,
    cast(selection_rank as bigint) as selection_rank,
    cast(exported as boolean) as exported,
    cast(b_id as varchar) as b_id,
    cast(score as double) as score,
    cast(probability as double) as probability,
    cast(tier as varchar) as tier,
    cast(top2_gap as double) as top2_gap,
    cast(
        case
            when not exported then null
            when top2_gap is null then 'single_candidate'
            else 'exported'
        end as varchar
    ) as gap_state,
    cast(block_keys as varchar) as block_keys,
    cast(auto_accept_min as double) as accept_min,
    cast(review_min as double) as review_min,
    cast(ambiguity_gap as double) as ambiguity_gap,
    cast(
        case
            when not exported or top2_gap is null then null
            else tier = 'review' and probability >= auto_accept_min and top2_gap < ambiguity_gap
        end as boolean
    ) as ambiguity_demoted_derived,
    cast(
        case
            when not exported or top2_gap is null then null
            else top2_gap = ambiguity_gap
        end as boolean
    ) as gap_at_rounded_boundary,
    cast(run_id as varchar) as run_id,
    cast(decided_at_utc as timestamp) as decided_at_utc
from joined
