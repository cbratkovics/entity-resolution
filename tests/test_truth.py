"""Truth classification: the statuses partition the links in the documented precedence, the
audit carries counts and hashes only, and labelled ids come from in-sample pairs alone."""

from __future__ import annotations

import re

import pandas as pd

from entity_resolution.data import truth


def _links() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a_id": ["rg_one", "rg_one", "rg_two", "rg_three", "rg_four", "rg_five", "rg_five"],
            "b_id": ["m1", "m1", "m2", "m3", "m999", "m4", "m5"],
        }
    )


def _a_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "native_id": ["rg_one", "rg_two", "rg_three", "rg_four", "rg_five"],
            "primary_type": ["Album", "Album", "Single", "Album", "Album"],
        }
    )


def test_statuses_partition_with_dead_before_out_of_scope() -> None:
    t = truth.classify(_links(), _a_frame(), b_ids={"m1", "m2", "m3", "m4", "m5"})
    status = dict(zip(t.links["a_id"] + "|" + t.links["b_id"], t.links["status"], strict=True))
    assert status["rg_four|m999"] == "truth_dead"
    assert status["rg_three|m3"] == "truth_out_of_scope"
    assert status["rg_one|m1"] == "truth_in_sample" and len(t.links) == 6  # duplicate dropped
    t2 = truth.apply_sample(t, sampled_a={"rg_one", "rg_two"}, sampled_b={"m1", "m2", "m4", "m5"})
    status2 = dict(zip(t2.links["a_id"] + "|" + t2.links["b_id"], t2.links["status"], strict=True))
    assert status2["rg_five|m4"] == "truth_unsampled" and status2["rg_one|m1"] == "truth_in_sample"
    assert t2.labelled_a_ids() == {"rg_one", "rg_two"}


def test_audit_is_counts_rates_and_hashes_only() -> None:
    t = truth.classify(_links(), _a_frame(), b_ids={"m1", "m2", "m3", "m4", "m5"})
    t = truth.apply_sample(
        t, sampled_a={"rg_one", "rg_two", "rg_five"}, sampled_b={"m1", "m2", "m4", "m5"}
    )
    a = truth.audit(t, _links())
    assert a["links_raw"] == 7 and a["links_distinct"] == 6 and a["duplicate_links"] == 1
    assert a["truth_dead"] == 1 and a["truth_out_of_scope"] == 1 and a["truth_unsampled"] == 0
    assert a["truth_in_sample"] == 4 and a["in_sample"]["one_to_many_a"] == 1
    assert a["truth_out_of_scope_by_primary_type"] == {"Single": 1}
    for hashes in a["anomaly_samples"].values():
        assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes) and len(hashes) <= 20
    assert "rg_" not in str(a) and "m999" not in str(a)
