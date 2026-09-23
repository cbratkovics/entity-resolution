-- Every value in fct_eval_metrics equals the value in the evaluation artifact it came from, to
-- 1e-9. The mart cannot publish a number the artifacts do not already carry. Empty result =
-- pass; with no artifacts committed there is nothing to reconcile and the test passes.
{% set metrics = [
    'test_a', 'labelled_a', 'labelled_a_reachable', 'pair_completeness', 'accepted', 'correct',
    'precision_auto_accept', 'recall_labelled_auto_accept', 'f1_auto_accept',
    'precision_auto_accept_or_review', 'recall_labelled_auto_accept_or_review',
    'f1_auto_accept_or_review', 'recall_overall', 'coverage', 'coverage_all_folds',
    'unverified_accepts', 'unverified_accepts_share',
    'tier_share_auto_accept', 'tier_share_review', 'tier_share_reject',
    'ambiguity_moved_to_review', 'review_queue', 'ece', 'brier', 'ece_pair_level', 'brier_pair_level'
] %}

with long as (
    select
        method_version,
        metric,
        value
    from {{ ref('slv_eval_metrics') }}
),

wide as (
    select * from {{ ref('fct_eval_metrics') }}
),

unpivoted as (
    {% for m in metrics %}
    select
        method_version,
        '{{ m }}' as metric,
        {{ m }} as value
    from wide
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    coalesce(l.method_version, u.method_version) as method_version,
    coalesce(l.metric, u.metric) as metric,
    l.value as artifact_value,
    u.value as mart_value
from long as l
full outer join unpivoted as u
    on l.method_version = u.method_version and l.metric = u.metric
where
    l.method_version is null
    or u.method_version is null
    or (l.value is null) != (u.value is null)
    or abs(l.value - u.value) > 1e-9
