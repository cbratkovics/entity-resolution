-- The rules macro must reproduce the source's own published target on every row to within 0.01
-- (the Python twin: tests/test_interfaces.py::test_target_spec_derives_and_reconciles).
select
    record_id,
    batch,
    batch,
    target_rules_value,
    ,
    abs(target_rules_value - ) as abs_diff
from {{ ref('slv_period_rows') }}
where  is not null and abs(target_rules_value - ) > 0.01
