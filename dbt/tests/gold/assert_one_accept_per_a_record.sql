-- One A record gets at most one accepted B per method (docs/BRIEF.md 2.8).
select
    a_id,
    method_version,
    count(*) as accepts
from {{ ref('fct_mapping') }}
where tier = 'auto_accept'
group by a_id, method_version
having count(*) > 1
