-- Grain: one row per method_version: the tier policy each mapping was decided under, from the
-- method version records.
select
    method_version,
    auto_accept_min,
    review_min,
    ambiguity_gap,
    feature_version,
    code_commit
from {{ ref('brz_method_versions') }}
