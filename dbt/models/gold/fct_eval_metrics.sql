-- Grain: one row per method_version, every test-fold metric as a column (the results table).
-- Values are the evaluation artifacts verbatim, pivoted from slv_eval_metrics;
-- assert_marts_reconcile_to_eval_artifacts proves it. Empty until Phase 4.
{% set metrics = [
    'pair_completeness', 'precision_auto_accept', 'recall_labelled_auto_accept', 'f1_auto_accept',
    'precision_auto_accept_or_review', 'recall_labelled_auto_accept_or_review',
    'f1_auto_accept_or_review', 'recall_overall', 'coverage', 'coverage_all_folds',
    'tier_share_auto_accept', 'tier_share_review', 'tier_share_reject', 'ece', 'brier'
] %}

with long as (
    select * from {{ ref('slv_eval_metrics') }}
)

select
    cast(l.method_version as varchar) as method_version,
    {% for m in metrics %}
    cast(max(case when l.metric = '{{ m }}' then l.value end) as double) as {{ m }},
    {% endfor %}
    cast('test' as varchar) as fold
from long as l
group by l.method_version
