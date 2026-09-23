"""Adapter registry, the two real adapters (Discogs masters on side B, MusicBrainz release
groups on side A per ADR 0001) and the offline fixture adapter. ``FixtureAdapter`` is an in-memory :class:`SourceAdapter` that
tests use to exercise the seams offline; its records are inline synthetic values, never rows
from a real dump, and nothing about it is written under ``artifacts/``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from entity_resolution.config import DATA_DIR, PROJECT
from entity_resolution.interfaces import Record, SourceAdapter, TruthLink

FIXTURE_RECORDS: tuple[Record, ...] = (
    Record("fixture", "1", "Album One", "Artist One", 1991),
    Record("fixture", "2", "Album Two", "Artist Two", None),
    Record("fixture", "3", "Album Three", "Various Artists", 2003, {"primary_type": "Album"}),
)
FIXTURE_TRUTH: tuple[TruthLink, ...] = (TruthLink("1", "101"), TruthLink("3", "103"))


class FixtureAdapter:
    """``interfaces.SourceAdapter`` over a handful of inline records (tests only)."""

    NAME = "fixture"
    SIDE = "A"
    LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

    def __init__(
        self,
        records: tuple[Record, ...] = FIXTURE_RECORDS,
        truth: tuple[TruthLink, ...] = FIXTURE_TRUTH,
    ) -> None:
        self._records = records
        self._truth = truth

    def iter_records(self, dump_path: Path) -> Iterator[Record]:
        yield from self._records

    def cache_path(self, data_dir: Path = DATA_DIR) -> Path:
        return data_dir / "cache" / f"{self.NAME}.parquet"

    def truth_links(self, dump_path: Path) -> Iterator[TruthLink]:
        yield from self._truth


_REGISTRY: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> SourceAdapter:
    if not isinstance(adapter, SourceAdapter):
        raise TypeError(f"{adapter!r} does not satisfy SourceAdapter")
    if adapter.SIDE not in ("A", "B"):
        raise ValueError(f"adapter {adapter.NAME!r} has side {adapter.SIDE!r}, expected 'A' or 'B'")
    _REGISTRY[adapter.NAME] = adapter
    return adapter


def adapter(name: str) -> SourceAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"no adapter registered as {name!r}; known: {sorted(_REGISTRY)}") from None


def registered() -> dict[str, SourceAdapter]:
    return dict(_REGISTRY)


def side_a_adapter() -> SourceAdapter:
    """The adapter ADR 0001 selected; raises while side A is undecided."""
    return adapter(PROJECT.require_side_a())


register(FixtureAdapter())


def _register_real_adapters() -> None:
    from entity_resolution.data.discogs import DiscogsAdapter
    from entity_resolution.data.musicbrainz import MusicBrainzAdapter

    register(DiscogsAdapter())
    register(MusicBrainzAdapter())


_register_real_adapters()
