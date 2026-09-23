"""The seams are satisfied by the project's implementations and the registry enforces them."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from entity_resolution import interfaces
from entity_resolution.config import PROJECT
from entity_resolution.data import loader


def test_fixture_adapter_satisfies_the_protocol() -> None:
    adapter = loader.adapter("fixture")
    assert isinstance(adapter, interfaces.SourceAdapter)
    records = list(adapter.iter_records(Path("unused")))
    assert records and all(isinstance(r, interfaces.Record) for r in records)
    assert all(r.source == adapter.NAME for r in records)
    links = list(adapter.truth_links(Path("unused")))
    assert all(isinstance(t, interfaces.TruthLink) for t in links)
    assert adapter.cache_path(Path("/x")).suffix == ".parquet"


def test_records_and_decisions_are_frozen() -> None:
    r = interfaces.Record("fixture", "1", "t", "a", None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.title = "x"  # type: ignore[misc]
    d = interfaces.Decision(
        "a", "b", "exact_v1", "0.0.0", 1.0, None, "auto_accept", "test", None, ()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.tier = "review"  # type: ignore[misc]
    assert d.method_version in PROJECT.method_versions and d.tier in PROJECT.tiers


def test_registry_rejects_non_adapters_and_bad_sides() -> None:
    with pytest.raises(TypeError):
        loader.register(object())  # type: ignore[arg-type]

    class Sideways(loader.FixtureAdapter):
        NAME = "sideways"
        SIDE = "C"

    with pytest.raises(ValueError):
        loader.register(Sideways())
    assert "sideways" not in loader.registered()
