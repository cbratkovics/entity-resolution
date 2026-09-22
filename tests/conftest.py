"""Shared fixtures. The stub loader is the fixture: ``rows`` is the synthetic source through the
test season, generated deterministically (no network, no cache dependency)."""

from __future__ import annotations

import pandas as pd
import pytest

from entity_resolution.config import PROJECT
from entity_resolution.data import loader


@pytest.fixture(scope="session")
def rows() -> pd.DataFrame:
    return loader.synthesize(range(PROJECT.min_season, PROJECT.test_season + 1))
