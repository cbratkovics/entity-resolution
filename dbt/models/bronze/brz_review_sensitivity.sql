{{ config(materialized='table') }}

-- artifacts/review_sensitivity.json flattened to one row per (method_version, threshold, cost_ratio).
-- Empty until the first full build reaches the methods stage.
{% set columns = [
    ['source_file', 'varchar'], ['generated_at_utc', 'timestamp'], ['feature_version', 'varchar'],
    ['code_commit', 'varchar'], ['method_version', 'varchar'], ['review_min', 'double'],
    ['chosen_accept_threshold', 'double'], ['threshold', 'double'], ['accepts', 'bigint'],
    ['review_queue', 'bigint'], ['precision_labelled', 'double'], ['expected_false_accepts', 'double'],
    ['cost_ratio', 'integer'], ['total_cost', 'double']
] %}
{% if files_exist(var('artifacts_dir') ~ '/review_sensitivity.json') %}
with report as (
    select * from {{ source('artifacts', 'review_sensitivity') }}
),

per_method as (
    {% for m in var('method_versions') %}
    select
        r.filename as source_file,
        cast(r.generated_at_utc as timestamp) as generated_at_utc,
        cast(r.feature_version as varchar) as feature_version,
        cast(r.code_commit as varchar) as code_commit,
        '{{ m }}' as method_version,
        cast(r.methods.{{ m }}.review_min as double) as review_min,
        cast(r.methods.{{ m }}.chosen_accept_threshold as double) as chosen_accept_threshold,
        unnest(r.methods.{{ m }}.points) as point
    from report as r
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

per_point as (
    select
        p.source_file,
        p.generated_at_utc,
        p.feature_version,
        p.code_commit,
        p.method_version,
        p.review_min,
        p.chosen_accept_threshold,
        cast(p.point.threshold as double) as threshold,
        cast(p.point.accepts as bigint) as accepts,
        cast(p.point.review_queue as bigint) as review_queue,
        cast(p.point.precision_labelled as double) as precision_labelled,
        cast(p.point.expected_false_accepts as double) as expected_false_accepts,
        p.point.total_cost as total_cost
    from per_method as p
)

{% for ratio in [1, 5, 20] %}
select
    q.source_file,
    q.generated_at_utc,
    q.feature_version,
    q.code_commit,
    q.method_version,
    q.review_min,
    q.chosen_accept_threshold,
    q.threshold,
    q.accepts,
    q.review_queue,
    q.precision_labelled,
    q.expected_false_accepts,
    {{ ratio }} as cost_ratio,
    cast(q.total_cost."{{ ratio }}" as double) as total_cost
from per_point as q
{% if not loop.last %}union all{% endif %}
{% endfor %}
{% else %}
{{ empty_typed_relation(columns) }}
{% endif %}
