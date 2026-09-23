-- Grain: one row per (method_version, level, bin_index): the reliability tables of every
-- evaluation artifact at decision level and pair level, with the level's ECE and Brier score.
with artifacts as (
    select * from {{ ref('brz_eval_artifacts') }}
    where metrics is not null
),

levels as (
    {% for level in ['decision_level', 'pair_level'] %}
    select
        a.method_version,
        '{{ level }}' as level,
        cast(json_extract(a.metrics, '$.calibration.{{ level }}.n') as integer) as n_total,
        cast(json_extract(a.metrics, '$.calibration.{{ level }}.ece') as double) as ece,
        cast(json_extract(a.metrics, '$.calibration.{{ level }}.brier') as double) as brier,
        json_extract(a.metrics, '$.calibration.{{ level }}.bins') as bins
    from artifacts as a
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

exploded as (
    select
        l.method_version,
        l.level,
        l.n_total,
        l.ece,
        l.brier,
        unnest(generate_series(0, 9)) as bin_index
    from levels as l
)

select
    e.method_version,
    e.level,
    e.bin_index,
    cast(json_extract(l.bins, '$[' || e.bin_index || '].lower') as double) as lower_bound,
    cast(json_extract(l.bins, '$[' || e.bin_index || '].upper') as double) as upper_bound,
    cast(json_extract(l.bins, '$[' || e.bin_index || '].n') as integer) as n,
    cast(json_extract(l.bins, '$[' || e.bin_index || '].mean_probability') as double) as mean_probability,
    cast(json_extract(l.bins, '$[' || e.bin_index || '].observed_rate') as double) as observed_rate,
    e.n_total,
    e.ece,
    e.brier
from exploded as e
inner join levels as l on e.method_version = l.method_version and e.level = l.level
