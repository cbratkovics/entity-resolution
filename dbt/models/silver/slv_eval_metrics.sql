-- Grain: one row per (method_version, fold, metric). Long form of every scalar metric in the
-- evaluation artifacts, read verbatim from the metrics JSON block; every metric is on the test
-- fold by construction (docs/BRIEF.md 2.9). The gold reconciliation tests compare
-- fct_eval_metrics against this table. Empty until the first artifact is committed.
{% set metric_paths = [
    ['pair_completeness', '$.pair_completeness_test'],
    ['precision_auto_accept', '$.at_auto_accept.precision'],
    ['recall_labelled_auto_accept', '$.at_auto_accept.recall_labelled'],
    ['f1_auto_accept', '$.at_auto_accept.f1'],
    ['precision_auto_accept_or_review', '$.at_auto_accept_or_review.precision'],
    ['recall_labelled_auto_accept_or_review', '$.at_auto_accept_or_review.recall_labelled'],
    ['f1_auto_accept_or_review', '$.at_auto_accept_or_review.f1'],
    ['recall_overall', '$.recall_overall'],
    ['coverage', '$.coverage'],
    ['coverage_all_folds', '$.coverage_all_folds'],
    ['tier_share_auto_accept', '$.tier_shares.auto_accept'],
    ['tier_share_review', '$.tier_shares.review'],
    ['tier_share_reject', '$.tier_shares.reject'],
    ['ece', '$.calibration.decision_level.ece'],
    ['brier', '$.calibration.decision_level.brier']
] %}

with artifacts as (
    select * from {{ ref('brz_eval_artifacts') }}
    where metrics is not null
)

{% for name, path in metric_paths %}
select
    a.method_version,
    'test' as fold,
    '{{ name }}' as metric,
    cast(json_extract(a.metrics, '{{ path }}') as double) as value
from artifacts as a
{% if not loop.last %}union all{% endif %}
{% endfor %}
