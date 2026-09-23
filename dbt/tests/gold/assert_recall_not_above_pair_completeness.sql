-- recall_overall cannot exceed pair completeness: a method cannot recover a truth pair
-- blocking never produced (docs/BRIEF.md 2.9).
select
    method_version,
    recall_overall,
    pair_completeness
from {{ ref('fct_eval_metrics') }}
where recall_overall > pair_completeness + 1e-9
