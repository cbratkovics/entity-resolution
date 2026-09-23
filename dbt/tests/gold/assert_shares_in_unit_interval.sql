-- Every share, rate and probability in the marts lies in [0, 1].
with metrics as (
    select
        method_version,
        unnest([
            'pair_completeness', 'precision_auto_accept', 'recall_labelled_auto_accept', 'f1_auto_accept',
            'precision_auto_accept_or_review', 'recall_labelled_auto_accept_or_review', 'f1_auto_accept_or_review',
            'recall_overall', 'coverage', 'coverage_all_folds', 'unverified_accepts_share',
            'tier_share_auto_accept', 'tier_share_review', 'tier_share_reject', 'ece', 'brier',
            'ece_pair_level', 'brier_pair_level'
        ]) as metric,
        unnest([
            pair_completeness, precision_auto_accept, recall_labelled_auto_accept, f1_auto_accept,
            precision_auto_accept_or_review, recall_labelled_auto_accept_or_review, f1_auto_accept_or_review,
            recall_overall, coverage, coverage_all_folds, unverified_accepts_share,
            tier_share_auto_accept, tier_share_review, tier_share_reject, ece, brier,
            ece_pair_level, brier_pair_level
        ]) as value
    from {{ ref('fct_eval_metrics') }}
),

mapping as (
    select
        method_version,
        'probability' as metric,
        probability as value
    from {{ ref('fct_mapping') }}
),

calibration as (
    select
        method_version,
        'observed_rate' as metric,
        observed_rate as value
    from {{ ref('fct_calibration') }}
),

everything as (
    select * from metrics
    union all
    select * from mapping
    union all
    select * from calibration
)

select *
from everything
where value is not null and (value < 0 or value > 1)
