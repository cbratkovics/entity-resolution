-- Grain: one row per (method_version, level, bin_index): the reliability tables the site plots.
select
    cast(method_version as varchar) as method_version,
    cast(level as varchar) as level,
    cast(bin_index as integer) as bin_index,
    cast(lower_bound as double) as lower_bound,
    cast(upper_bound as double) as upper_bound,
    cast(n as bigint) as n,
    cast(mean_probability as double) as mean_probability,
    cast(observed_rate as double) as observed_rate,
    cast(n_total as bigint) as n_total,
    cast(ece as double) as ece,
    cast(brier as double) as brier
from {{ ref('slv_calibration') }}
