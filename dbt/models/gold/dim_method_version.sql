-- Grain: one row per method_version. The method version records as a dimension; the site and
-- fct_eval_metrics join to it. Empty until Phase 4 writes the first record.
select
    cast(method_version as varchar) as method_version,
    cast(definition as varchar) as definition,
    cast(feature_version as varchar) as feature_version,
    cast(code_commit as varchar) as code_commit,
    cast(created_at_utc as timestamp) as created_at_utc,
    cast(auto_accept_min as double) as auto_accept_min,
    cast(review_min as double) as review_min,
    cast(ambiguity_gap as double) as ambiguity_gap
from {{ ref('brz_method_versions') }}
