"""Shared fixtures. Everything is offline: the fixture adapter's inline records and a scratch
artifact tree. Tests that need the real sample skip themselves when data/ is absent."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from entity_resolution.config import DATA_DIR
from entity_resolution.data import loader


@pytest.fixture(scope="session")
def fixture_records() -> pd.DataFrame:
    adapter = loader.adapter("fixture")
    rows = [
        {
            "source": r.source,
            "native_id": r.native_id,
            "title": r.title,
            "artist_credit": r.artist_credit,
            "year": r.year,
        }
        for r in adapter.iter_records(Path("unused"))
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def real_data_present() -> bool:
    return DATA_DIR.exists() and any(DATA_DIR.iterdir())
