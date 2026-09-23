-- Grain: one row per (method_version, threshold, cost_ratio): the review-cost curve on the
-- test fold, from the committed sensitivity artifact, with the chosen threshold beside it.
select
    cast(method_version as varchar) as method_version,
    cast(threshold as double) as threshold,
    cast(cost_ratio as integer) as cost_ratio,
    cast(review_min as double) as review_min,
    cast(chosen_accept_threshold as double) as chosen_accept_threshold,
    cast(accepts as bigint) as accepts,
    cast(queue_floor as bigint) as queue_floor,
    cast(queue_ambiguity as bigint) as queue_ambiguity,
    cast(review_queue as bigint) as review_queue,
    cast(precision_labelled as double) as precision_labelled,
    cast(expected_false_accepts as double) as expected_false_accepts,
    cast(total_cost as double) as total_cost,
    cast(review_queue + expected_false_accepts * cost_ratio as double) as total_cost_recomputed,
    cast(threshold = chosen_accept_threshold as boolean) as is_chosen
from {{ ref('brz_review_sensitivity') }}
