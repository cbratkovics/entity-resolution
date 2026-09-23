{{ config(materialized='table') }}

-- The review-floor sweep of artifacts/review_sensitivity.json, one row per (method_version,
-- floor). Empty until the first full build reaches the methods stage.
{% set columns = [
    ['source_file', 'varchar'], ['method_version', 'varchar'], ['accept_min', 'double'],
    ['n_test_a', 'bigint'], ['n_labelled_reachable', 'bigint'], ['floor', 'double'],
    ['queue_floor', 'bigint'], ['queue_ambiguity', 'bigint'], ['queue_total', 'bigint'],
    ['queue_share_of_test_a', 'double'], ['recall_with_review', 'double']
] %}
{% if files_exist(var('artifacts_dir') ~ '/review_sensitivity.json') %}
with report as (
    select * from {{ source('artifacts', 'review_sensitivity') }}
),

per_method as (
    {% for m in var('method_versions') %}
    select
        r.filename as source_file,
        '{{ m }}' as method_version,
        cast(r.methods.{{ m }}.review_floor_sweep.accept_min as double) as accept_min,
        cast(r.methods.{{ m }}.review_floor_sweep.n_test_a as bigint) as n_test_a,
        cast(r.methods.{{ m }}.review_floor_sweep.n_labelled_reachable as bigint) as n_labelled_reachable,
        unnest(r.methods.{{ m }}.review_floor_sweep.points) as point
    from report as r
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    p.source_file,
    p.method_version,
    p.accept_min,
    p.n_test_a,
    p.n_labelled_reachable,
    cast(p.point.floor as double) as floor,
    cast(p.point.queue_floor as bigint) as queue_floor,
    cast(p.point.queue_ambiguity as bigint) as queue_ambiguity,
    cast(p.point.queue_total as bigint) as queue_total,
    cast(p.point.queue_share_of_test_a as double) as queue_share_of_test_a,
    cast(p.point.recall_with_review as double) as recall_with_review
from per_method as p
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
