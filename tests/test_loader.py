from __future__ import annotations

import pandas as pd
import pytest

from entity_resolution.data import loader


def test_fixture_rows_are_unique_at_the_grain(fixture_records: pd.DataFrame) -> None:
    assert not fixture_records.duplicated(["source", "native_id"]).any()
    assert set(fixture_records.columns) >= {"source", "native_id", "title", "artist_credit", "year"}


def test_registry_lookup_and_unknown_name() -> None:
    assert loader.adapter("fixture").NAME == "fixture"
    with pytest.raises(KeyError, match="no adapter registered"):
        loader.adapter("nope")


def test_side_a_adapter_refuses_while_undecided() -> None:
    with pytest.raises(RuntimeError, match="docs/adr"):
        loader.side_a_adapter()
