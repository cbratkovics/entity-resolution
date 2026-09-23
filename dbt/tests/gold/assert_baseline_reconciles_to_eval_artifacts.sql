-- The two baselines (exact_v1, rules_v1) have a reconciled row in fct_eval_metrics whenever any
-- evaluation artifact is committed, so the learned method is never published without the
-- comparison it is judged against. Empty result = pass; with no artifacts at all there is
-- nothing to compare and the test passes.
with artifacts as (
    select method_version from {{ ref('brz_eval_artifacts') }}
),

expected as (
    select unnest(['exact_v1', 'rules_v1']) as method_version
    where (select count(*) from artifacts) > 0
),

marts as (
    select method_version from {{ ref('fct_eval_metrics') }}
)

select
    e.method_version,
    'baseline row missing from fct_eval_metrics or artifacts' as problem
from expected as e
left join artifacts as a on e.method_version = a.method_version
left join marts as m on e.method_version = m.method_version
where a.method_version is null or m.method_version is null
