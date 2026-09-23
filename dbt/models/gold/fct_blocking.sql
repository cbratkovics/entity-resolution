-- Grain: one row per block key: the pairs each key produced, its own pair completeness, and
-- the union and cap figures of the run repeated on every row.
select
    cast(block_key as varchar) as block_key,
    cast(key_pairs as bigint) as key_pairs,
    cast(key_pair_completeness as double) as key_pair_completeness,
    cast(keys_emitted_a as bigint) as keys_emitted_a,
    cast(keys_emitted_b as bigint) as keys_emitted_b,
    cast(union_pairs as bigint) as union_pairs,
    cast(candidate_pairs_after_cap as bigint) as candidate_pairs_after_cap,
    cast(reduction_ratio as double) as reduction_ratio,
    cast(union_pair_completeness as double) as union_pair_completeness,
    cast(after_cap_pair_completeness as double) as after_cap_pair_completeness,
    cast(truth_pairs as bigint) as truth_pairs,
    cast(truth_pairs_lost_to_cap as bigint) as truth_pairs_lost_to_cap,
    cast(a_records_over_cap as bigint) as a_records_over_cap,
    cast(pairs_dropped as bigint) as pairs_dropped,
    cast(candidate_cap_per_a as integer) as candidate_cap_per_a,
    cast(feature_version as varchar) as feature_version
from {{ ref('brz_blocking_report') }}
