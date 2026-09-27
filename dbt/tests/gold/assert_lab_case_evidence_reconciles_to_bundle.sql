-- The Decision Lab case bundle (artifacts/lab/cases.json, read by brz_lab_cases) carries exactly
-- the evidence the warehouse projects from its own mapping (fct_lab_case_evidence) and the same
-- agreement class (fct_lab_case_comparison): every (case_id, method_version) must exist on both
-- sides with equal exported flag, b_id, tier, gap state, block keys, and score, probability and
-- gap equal to 1e-9. Empty result = pass; with no bundle there is nothing to reconcile.
with bundle as (
    select
        b.case_id,
        b.method_version,
        coalesce(b.exported, false) as exported,
        coalesce(b.b_id, '') as b_id,
        coalesce(b.score, -1) as score,
        coalesce(b.probability, -1) as probability,
        coalesce(b.tier, '') as tier,
        coalesce(b.top2_gap, -1) as top2_gap,
        coalesce(b.gap_state, '') as gap_state,
        coalesce(b.block_keys, '') as block_keys,
        coalesce(b.agreement_class, '') as agreement_class
    from {{ ref('brz_lab_cases') }} as b
),

mart as (
    select
        e.case_id,
        e.method_version,
        coalesce(e.exported, false) as exported,
        coalesce(e.b_id, '') as b_id,
        coalesce(e.score, -1) as score,
        coalesce(e.probability, -1) as probability,
        coalesce(e.tier, '') as tier,
        coalesce(e.top2_gap, -1) as top2_gap,
        coalesce(e.gap_state, '') as gap_state,
        coalesce(e.block_keys, '') as block_keys,
        coalesce(c.agreement_class, '') as agreement_class
    from {{ ref('fct_lab_case_evidence') }} as e
    inner join {{ ref('fct_lab_case_comparison') }} as c on e.case_id = c.case_id
)

select
    coalesce(b.case_id, m.case_id) as case_id,
    coalesce(b.method_version, m.method_version) as method_version,
    'bundle evidence and mart projection differ or one side is missing' as problem
from bundle as b
full outer join mart as m
    on b.case_id = m.case_id and b.method_version = m.method_version
where
    b.case_id is null
    or m.case_id is null
    or b.exported != m.exported
    or b.b_id != m.b_id
    or b.tier != m.tier
    or b.gap_state != m.gap_state
    or b.block_keys != m.block_keys
    or b.agreement_class != m.agreement_class
    or abs(b.score - m.score) > 1e-9
    or abs(b.probability - m.probability) > 1e-9
    or abs(b.top2_gap - m.top2_gap) > 1e-9
