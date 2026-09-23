-- Every decided pair came from blocking: it carries at least one block key, and its A record
-- appears at most once per method (one decision per A). The candidate table itself lives under
-- data/ and is not in the warehouse, so the block keys are the evidence.
select
    a_id,
    method_version,
    block_keys
from {{ ref('fct_mapping') }}
where block_keys is null or block_keys = ''
