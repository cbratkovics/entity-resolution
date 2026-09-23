"""The seams the pipeline is built on (docs/BRIEF.md section 2).

* :class:`SourceAdapter` — one per catalogue. Discogs is side B; the side-A adapter is chosen by
  ADR 0001 and selected by ``PROJECT.side_a``, so the decision is a config value, not a rewrite.
  Adapters stream their dump into :class:`Record` values and cache them as parquet under
  ``data/``; nothing they yield ever enters git.
* :class:`Record` — one album-level work with its native identifier and the attributes every
  feature derives from.
* :class:`CandidatePair` — one ``(a_id, b_id)`` produced by blocking, with the keys that produced
  it. The truth table is never consulted to build one.
* :class:`Decision` — one method's verdict on an A record: the chosen B, its score, calibrated
  probability, tier and the fold the pair inherited from its B record.

The artifact shapes that flow between layers are JSON Schemas under ``artifacts/schemas/``;
``tests/test_artifact_schemas.py`` validates every committed artifact against them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Record:
    """One album-level work as loaded from a source, before normalisation."""

    source: str
    """Adapter name: ``discogs`` or the side-A source."""
    native_id: str
    """The source's own identifier as a string (Discogs ``master_id``, MusicBrainz ``gid``,
    Wikidata ``QID``)."""
    title: str
    artist_credit: str
    year: int | None
    extra: dict[str, str] = field(default_factory=dict)
    """Source-specific attributes kept for profiling (``primary_type``, ``genres``); never
    features."""


@dataclass(frozen=True)
class TruthLink:
    """One labelled pair: a side-A record that the side-A source itself links to a Discogs
    master. Loaded into its own table; never joined to the matcher's input."""

    a_id: str
    b_id: str


@dataclass(frozen=True)
class CandidatePair:
    """One pair produced by blocking. ``block_keys`` names every key that produced it."""

    a_id: str
    b_id: str
    block_keys: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    """One method's verdict for an A record (grain ``(a_id, method_version)``)."""

    a_id: str
    b_id: str
    method_version: str
    feature_version: str
    score: float
    probability: float | None
    tier: str
    fold: str
    top2_gap: float | None
    block_keys: tuple[str, ...]


@runtime_checkable
class SourceAdapter(Protocol):
    """A catalogue dump turned into :class:`Record` values, one adapter per source."""

    NAME: str
    """Registry key and the ``source`` value on every record."""
    SIDE: str
    """``"A"`` or ``"B"``."""
    LICENCE_URL: str
    """Where the licence text recorded in docs/DATA_SOURCES.md was read from."""

    def iter_records(self, dump_path: Path) -> Iterator[Record]:
        """Stream the dump; never materialise it whole."""

    def cache_path(self, data_dir: Path) -> Path:
        """The parquet cache this adapter reads or writes under ``data/``."""

    def truth_links(self, dump_path: Path) -> Iterator[TruthLink]:
        """Labelled links to Discogs masters. Side B yields nothing."""
