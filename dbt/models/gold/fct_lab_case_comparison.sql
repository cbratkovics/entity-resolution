-- Grain: one row per case_id: how the three methods' exported decisions for the case relate.
-- agreement_class is over exported rows only; methods_disagree means different chosen B ids
-- across methods, which is distinct from ambiguity between candidates inside one method
-- (that is a per-row gap, in fct_lab_case_evidence). Chosen B ids of different methods are not
-- a ranked candidate list.
with evidence as (
    select
        case_id,
        a_id,
        reason_codes,
        selection_rank,
        exported,
        b_id
    from {{ ref('fct_lab_case_evidence') }}
),

agg as (
    select
        case_id,
        any_value(a_id) as a_id,
        any_value(reason_codes) as reason_codes,
        any_value(selection_rank) as selection_rank,
        count(*) filter (where exported) as methods_exported,
        count(distinct b_id) filter (where exported) as distinct_chosen_b_ids
    from evidence
    group by case_id
)

select
    cast(case_id as varchar) as case_id,
    cast(a_id as varchar) as a_id,
    cast(reason_codes as varchar) as reason_codes,
    cast(selection_rank as bigint) as selection_rank,
    cast(methods_exported as bigint) as methods_exported,
    cast(distinct_chosen_b_ids as bigint) as distinct_chosen_b_ids,
    cast(
        case
            when methods_exported = 0 then 'none_exported'
            when methods_exported = 1 then 'single_method_exported'
            when distinct_chosen_b_ids = 1 then 'all_exported_agree'
            else 'methods_disagree'
        end as varchar
    ) as agreement_class
from agg
