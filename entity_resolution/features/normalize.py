"""Name normalisation (docs/BRIEF.md 2.3). Pure functions, no I/O, applied identically to both
sides. This is the only place a title or artist credit is normalised (rule 5): the profiler,
blocking, the methods, the evaluator and the dbt exports all call :func:`normalize_record`.

Pipeline for any string (:func:`basic`): Unicode NFKD, strip combining marks, casefold,
``&`` becomes ``and``, punctuation stripped (apostrophes removed, every other punctuation or
symbol character becomes a space), whitespace collapsed.

Artist credit: Discogs numeric disambiguators ``(2)`` are stripped, ``"Beatles, The"`` is
reordered to ``"the beatles"``, and a leading article from ``ARTICLES`` is dropped; the
pre-drop form is ``artist_norm_full``.

Title: bracketed groups whose text contains a word from ``QUALIFIERS`` are dropped into
``title_qualifiers``; the form with them kept is ``title_norm_full``.

Interpretation recorded for the checkpoint: ``is_self_titled`` compares ``title_norm`` with
both ``artist_norm`` and ``artist_norm_full``, so "The Beatles" by The Beatles is self-titled
whether or not the article was dropped.

Various-artists credits (``VA_CREDITS``) normalise to the single token ``VA_CANONICAL`` on
both sides (ADR 0004, feature version 0.2.0).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from metaphone import doublemetaphone

ARTICLES: tuple[str, ...] = ("the", "a", "an", "los", "las", "les", "die", "der", "das")
QUALIFIERS: tuple[str, ...] = (
    "remaster",
    "deluxe",
    "anniversary",
    "edition",
    "expanded",
    "reissue",
)
VA_CREDITS: frozenset[str] = frozenset({"various", "various artists", "va", "v/a"})
VA_CANONICAL = "various"
"""Every various-artists credit normalises to this one token (ADR 0004): MusicBrainz writes
"Various Artists" where Discogs writes "Various", and the credits must agree."""

_DISAMBIGUATOR_RE = re.compile(r"\s*\(\d+\)")
_COMMA_ARTICLE_RE = re.compile(
    r"^(?P<rest>.+?),\s*(?P<article>" + "|".join(ARTICLES) + r")\s*$", re.IGNORECASE
)
_BRACKET_RE = re.compile(r"\s*[(\[][^()\[\]]*[)\]]")
_APOSTROPHES = "'’‘ʼ"
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Normalized:
    """Every normalised form and flag of one record. Field names are the column names used
    everywhere downstream."""

    title_norm: str
    title_norm_full: str
    title_qualifiers: tuple[str, ...]
    artist_norm: str
    artist_norm_full: str
    is_various_artists: bool
    is_self_titled: bool
    year: int | None
    year_missing: bool
    title_tokens: tuple[str, ...] = field(default=())
    artist_tokens: tuple[str, ...] = field(default=())
    title_metaphone: str = ""
    artist_metaphone: str = ""


def strip_marks(text: str) -> str:
    """NFKD then drop combining marks, so ``é`` becomes ``e`` and ligatures expand."""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def strip_punctuation(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in _APOSTROPHES:
            continue
        cat = unicodedata.category(ch)
        out.append(" " if cat[0] in ("P", "S") else ch)
    return "".join(out)


def basic(text: str) -> str:
    """The shared string pipeline: marks, casefold, ampersand, punctuation, whitespace."""
    text = strip_marks(text or "").casefold().replace("&", " and ")
    return _WS_RE.sub(" ", strip_punctuation(text)).strip()


def strip_disambiguator(credit: str) -> str:
    """``"Prince (2)"`` -> ``"Prince"``. Only all-digit brackets are disambiguators."""
    return _DISAMBIGUATOR_RE.sub("", credit or "")


def reorder_comma_article(credit: str) -> str:
    """``"Beatles, The"`` -> ``"The Beatles"``."""
    m = _COMMA_ARTICLE_RE.match(credit or "")
    return f"{m.group('article')} {m.group('rest')}" if m else (credit or "")


def drop_leading_article(text: str) -> str:
    """Drop one leading article from ``ARTICLES`` on an already-normalised string. A string
    that is only an article is kept, so nothing normalises to empty."""
    parts = text.split(" ", 1)
    if len(parts) == 2 and parts[0] in ARTICLES:
        return parts[1]
    return text


def split_qualifiers(title: str) -> tuple[str, tuple[str, ...]]:
    """Remove bracketed groups that carry an edition qualifier; return the stripped title and
    the normalised qualifier texts, in order of appearance."""
    found: list[str] = []

    def keep_or_drop(m: re.Match[str]) -> str:
        inner = basic(m.group(0).strip()[1:-1])
        if any(q in inner.split(" ") for q in QUALIFIERS):
            found.append(inner)
            return ""
        return m.group(0)

    stripped = _BRACKET_RE.sub(keep_or_drop, title or "")
    return stripped, tuple(found)


def is_various_artists(credit: str) -> bool:
    raw = (credit or "").strip().casefold()
    return raw in VA_CREDITS or basic(credit) in {basic(v) for v in VA_CREDITS}


def tokens(text: str) -> tuple[str, ...]:
    """Sorted, deduplicated tokens of a normalised string."""
    return tuple(sorted(set(text.split()) - {""})) if text else ()


def metaphone_first(text: str) -> str:
    """Double metaphone (primary, else secondary) of the first token; empty when there is no
    alphabetic token to encode."""
    first = text.split(" ", 1)[0] if text else ""
    if not first:
        return ""
    primary, secondary = doublemetaphone(first)
    return primary or secondary or ""


def normalize_artist(credit: str) -> tuple[str, str]:
    """``(artist_norm, artist_norm_full)``; a various-artists credit is ``VA_CANONICAL`` in
    both forms."""
    if is_various_artists(credit):
        return VA_CANONICAL, VA_CANONICAL
    full = basic(reorder_comma_article(strip_disambiguator(credit)))
    return drop_leading_article(full), full


def normalize_title(title: str) -> tuple[str, str, tuple[str, ...]]:
    """``(title_norm, title_norm_full, title_qualifiers)``."""
    stripped, qualifiers = split_qualifiers(title)
    return basic(stripped), basic(title), qualifiers


def normalize_record(title: str, artist_credit: str, year: int | None) -> Normalized:
    title_norm, title_norm_full, qualifiers = normalize_title(title)
    artist_norm, artist_norm_full = normalize_artist(artist_credit)
    year_int = int(year) if year is not None and str(year).strip() != "" else None
    return Normalized(
        title_norm=title_norm,
        title_norm_full=title_norm_full,
        title_qualifiers=qualifiers,
        artist_norm=artist_norm,
        artist_norm_full=artist_norm_full,
        is_various_artists=is_various_artists(artist_credit),
        is_self_titled=bool(title_norm) and title_norm in (artist_norm, artist_norm_full),
        year=year_int,
        year_missing=year_int is None,
        title_tokens=tokens(title_norm),
        artist_tokens=tokens(artist_norm),
        title_metaphone=metaphone_first(title_norm),
        artist_metaphone=metaphone_first(artist_norm),
    )


NORMALIZED_COLUMNS: tuple[str, ...] = (
    "title_norm",
    "title_norm_full",
    "title_qualifiers",
    "artist_norm",
    "artist_norm_full",
    "is_various_artists",
    "is_self_titled",
    "year_missing",
    "title_tokens",
    "artist_tokens",
    "title_metaphone",
    "artist_metaphone",
)
"""Columns :func:`normalize_frame` adds, in this order (list columns hold tuples)."""


def normalize_frame(df):  # type: ignore[no-untyped-def]
    """Add every :class:`Normalized` field to a frame with ``title``, ``artist_credit`` and
    ``year`` columns. The only frame-level normalisation entry point (rule 5); the profiler,
    the sample and the pair features all call it."""
    import pandas as pd

    rows = [
        normalize_record(title or "", credit or "", None if pd.isna(year) else int(year))
        for title, credit, year in zip(df["title"], df["artist_credit"], df["year"], strict=True)
    ]
    out = df.copy()
    for col in NORMALIZED_COLUMNS:
        values = [getattr(r, col) for r in rows]
        if col in ("title_qualifiers", "title_tokens", "artist_tokens"):
            values = [list(v) for v in values]
        out[col] = values
    return out
