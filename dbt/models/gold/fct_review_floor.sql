-- Grain: one row per (method_version, floor): what a review budget buys. The review queue and
-- its share of the test fold at each floor, and recall if every queued row were resolved.
select
    cast(method_version as varchar) as method_version,
    cast(floor as double) as floor,
    cast(accept_min as double) as accept_min,
    cast(queue_floor as bigint) as queue_floor,
    cast(queue_ambiguity as bigint) as queue_ambiguity,
    cast(queue_total as bigint) as queue_total,
    cast(queue_share_of_test_a as double) as queue_share_of_test_a,
    cast(recall_with_review as double) as recall_with_review,
    cast(n_test_a as bigint) as n_test_a,
    cast(n_labelled_reachable as bigint) as n_labelled_reachable
from {{ ref('brz_review_floor') }}
