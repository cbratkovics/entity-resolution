-- The count metrics in the long table are whole numbers, so casting them to integers in the
-- wide mart loses nothing.
select
    method_version,
    metric,
    value
from {{ ref('slv_eval_metrics') }}
where
    metric in (
        'test_a', 'labelled_a', 'labelled_a_reachable', 'accepted', 'correct',
        'unverified_accepts', 'ambiguity_moved_to_review', 'review_queue'
    )
    and value != floor(value)
