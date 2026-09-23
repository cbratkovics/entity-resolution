-- The three tier shares of every method sum to one within 1e-9 (docs/BRIEF.md 2.11).
select
    method_version,
    tier_share_auto_accept + tier_share_review + tier_share_reject as total
from {{ ref('fct_eval_metrics') }}
where abs(tier_share_auto_accept + tier_share_review + tier_share_reject - 1) > 1e-9
