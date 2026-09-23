-- The artifact's total cost equals the cost recomputed in SQL from its own columns.
select
    method_version,
    threshold,
    cost_ratio,
    total_cost,
    total_cost_recomputed
from {{ ref('fct_review_queue') }}
where total_cost is not null and abs(total_cost - total_cost_recomputed) > 1e-6
