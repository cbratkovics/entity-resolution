"""The deterministic sample: membership is a pure function of (source, native_id), the solved
threshold is recomputable from the pool, the unlinked share is hit, and content hashes are
order-independent."""

from __future__ import annotations

import pandas as pd

from entity_resolution.data import sample


def _frame(n: int, source: str = "discogs") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": source,
            "native_id": [str(i) for i in range(1, n + 1)],
            "title": [f"t{i}" for i in range(1, n + 1)],
            "artist_credit": [f"a{i}" for i in range(1, n + 1)],
            "year": [1990 + (i % 30) for i in range(1, n + 1)],
        }
    )


def test_membership_hash_is_pure_and_source_specific() -> None:
    assert sample.membership_hash("discogs", "1") == sample.membership_hash("discogs", "1")
    assert sample.membership_hash("discogs", "1") != sample.membership_hash("musicbrainz", "1")
    assert len(sample.membership_hash("x", "y")) == 64


def test_n_unlinked_for_share() -> None:
    assert sample.n_unlinked_for(100, 0.5) == 100
    assert sample.n_unlinked_for(100, 0.25) == 33
    assert sample.n_unlinked_for(0, 0.5) == 0


def test_threshold_is_recomputable_and_selects_exactly_n() -> None:
    frame = _frame(1000)
    hashes = sample.hash_column("discogs", frame["native_id"])
    solved = sample.solve_threshold(hashes, 250)
    chosen = sample.select(hashes, solved["threshold_hex"])
    assert int(chosen.sum()) == 250 == solved["selected"] and solved["pool_size"] == 1000
    assert solved["threshold_hex"] == sorted(hashes)[249]
    assert 0 < solved["threshold_fraction"] < 1
    assert sample.solve_threshold(hashes, 0)["threshold_hex"] == "0" * 64


def test_build_side_keeps_every_linked_record_and_hits_the_share() -> None:
    frame = _frame(1000)
    linked = {str(i) for i in range(1, 101)}
    pool = pd.Series(True, index=frame.index)
    out, rec = sample.build_side(frame, source="discogs", linked_ids=linked, pool_mask=pool)
    assert set(out[out["is_linked"]]["native_id"]) == linked
    assert rec["linked"] == 100 and rec["selected"] == 100 and rec["sampled"] == 200
    assert rec["unlinked_share_actual"] == 0.5 and rec["pool_size"] == 900
    out2, rec2 = sample.build_side(frame, source="discogs", linked_ids=linked, pool_mask=pool)
    assert out.equals(out2) and rec == rec2


def test_pool_mask_excludes_records_from_selection() -> None:
    frame = _frame(200)
    linked = {"1", "2"}
    pool = frame["native_id"].astype(int) <= 50
    out, rec = sample.build_side(frame, source="musicbrainz", linked_ids=linked, pool_mask=pool)
    unlinked = out[~out["is_linked"]]
    assert unlinked["native_id"].astype(int).max() <= 50 and rec["pool_size"] == 48


def test_content_hash_ignores_row_order_and_normalised_columns_are_added() -> None:
    frame = _frame(20)
    normalised = sample.normalize_sample(frame)
    assert "title_norm" in normalised.columns and "title_tokens" in normalised.columns
    assert list(normalised.columns[: len(frame.columns)]) == list(frame.columns)
    h1 = sample.content_sha256(normalised)
    h2 = sample.content_sha256(normalised.iloc[::-1].reset_index(drop=True))
    assert h1 == h2
    changed = normalised.copy()
    changed.loc[0, "title"] = "different"
    assert sample.content_sha256(changed) != h1
