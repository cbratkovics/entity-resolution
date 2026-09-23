"""Every rule of docs/BRIEF.md 2.3 with its edge cases."""

from __future__ import annotations

import pytest

from entity_resolution.features import FEATURE_VERSION
from entity_resolution.features import normalize as n


def test_feature_version_is_set() -> None:
    assert FEATURE_VERSION == "0.2.0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Café Tacvba", "cafe tacvba"),
        ("Motörhead", "motorhead"),
        ("Simon & Garfunkel", "simon and garfunkel"),
        ("AC/DC", "ac dc"),
        ("Don't Look Back", "dont look back"),
        ("  Ｆull–width   dash ", "full width dash"),
        ("Sigur Rós: ( )", "sigur ros"),
        ("", ""),
    ],
)
def test_basic_pipeline(raw: str, expected: str) -> None:
    assert n.basic(raw) == expected


def test_numeric_disambiguator_is_stripped_but_other_brackets_are_kept() -> None:
    assert n.strip_disambiguator("Prince (2)") == "Prince"
    assert n.strip_disambiguator("Nirvana (US)") == "Nirvana (US)"
    assert n.normalize_artist("Prince (2)") == ("prince", "prince")


def test_comma_article_is_reordered_then_dropped_with_full_form_kept() -> None:
    assert n.reorder_comma_article("Beatles, The") == "The Beatles"
    assert n.normalize_artist("Beatles, The") == ("beatles", "the beatles")
    assert n.normalize_artist("The Beatles") == ("beatles", "the beatles")
    assert n.normalize_artist("Los Lobos") == ("lobos", "los lobos")
    assert n.normalize_artist("Die Ärzte") == ("arzte", "die arzte")


def test_bare_article_and_non_article_are_untouched() -> None:
    assert n.normalize_artist("The") == ("the", "the")
    assert n.normalize_artist("Theatre of Hate") == ("theatre of hate", "theatre of hate")
    assert n.normalize_artist("A") == ("a", "a")


def test_edition_qualifiers_move_to_title_qualifiers() -> None:
    title_norm, title_norm_full, quals = n.normalize_title("Abbey Road (2019 Remaster)")
    assert title_norm == "abbey road"
    assert title_norm_full == "abbey road 2019 remaster"
    assert quals == ("2019 remaster",)
    title_norm, _, quals = n.normalize_title("Kid A [Deluxe Edition] (Bonus Tracks)")
    assert title_norm == "kid a bonus tracks"
    assert quals == ("deluxe edition",)


def test_non_qualifier_brackets_stay_in_the_title() -> None:
    title_norm, _, quals = n.normalize_title("Live (At The Fillmore)")
    assert title_norm == "live at the fillmore" and quals == ()


@pytest.mark.parametrize("credit", ["Various", "Various Artists", "VA", "V/A", "various artists"])
def test_various_artists_flag(credit: str) -> None:
    assert n.is_various_artists(credit)


def test_various_is_not_matched_by_substring() -> None:
    assert not n.is_various_artists("Various Cruelties")
    assert n.normalize_artist("Various Cruelties") == ("various cruelties", "various cruelties")


@pytest.mark.parametrize("credit", ["Various", "Various Artists", "VA", "V/A"])
def test_various_artists_credits_canonicalise_to_one_token(credit: str) -> None:
    assert n.normalize_artist(credit) == (n.VA_CANONICAL, n.VA_CANONICAL)
    r = n.normalize_record("Now That's Music", credit, 2001)
    assert r.artist_tokens == (n.VA_CANONICAL,) and r.is_various_artists


def test_self_titled_compares_against_both_artist_forms() -> None:
    assert n.normalize_record("The Beatles", "The Beatles", 1968).is_self_titled
    assert n.normalize_record("Beatles", "Beatles, The", 1968).is_self_titled
    assert not n.normalize_record("Help!", "The Beatles", 1965).is_self_titled
    assert not n.normalize_record("", "", None).is_self_titled


def test_year_missing_and_tokens_and_metaphone() -> None:
    r = n.normalize_record("Sgt. Pepper's Lonely Hearts Club Band", "Beatles, The", None)
    assert r.year is None and r.year_missing
    assert r.title_tokens == ("band", "club", "hearts", "lonely", "peppers", "sgt")
    assert r.artist_tokens == ("beatles",)
    assert r.title_metaphone == "SKT" and r.artist_metaphone == "PTLS"
    assert n.normalize_record("x", "y", "1999").year == 1999
    assert n.normalize_record("x", "y", "").year_missing


def test_tokens_are_sorted_and_deduplicated() -> None:
    assert n.tokens("la la land") == ("la", "land")
    assert n.metaphone_first("") == "" and n.metaphone_first("2112") == ""


def test_normalisation_is_idempotent_on_its_own_output() -> None:
    for raw in ("Café Tacvba", "Simon & Garfunkel", "Beatles, The"):
        once = n.basic(raw)
        assert n.basic(once) == once
