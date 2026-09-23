-- Grain: one row per (method_version, fold). The fold counts of each evaluation artifact,
-- flattened from the fold_counts JSON block. Empty until the first artifact is committed.
with artifacts as (
    select * from {{ ref('brz_eval_artifacts') }}
)

{% for fold in var('folds') %}
select
    a.method_version,
    '{{ fold }}' as fold,
    cast(json_extract(a.fold_counts, '$.{{ fold }}.a_records') as integer) as a_records,
    cast(json_extract(a.fold_counts, '$.{{ fold }}.labelled_a_records') as integer) as labelled_a_records,
    cast(json_extract(a.fold_counts, '$.{{ fold }}.candidate_pairs') as integer) as candidate_pairs,
    cast(json_extract(a.fold_counts, '$.{{ fold }}.decisions') as integer) as decisions
from artifacts as a
{% if not loop.last %}union all{% endif %}
{% endfor %}
