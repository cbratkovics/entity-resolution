"""PROJECT is the one source of the vocabulary; every mirror must agree."""

from __future__ import annotations

import yaml

from entity_resolution.config import PROJECT, REPO_ROOT, dbt_vars


def test_dbt_project_vars_mirror_the_config() -> None:
    project = yaml.safe_load((REPO_ROOT / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    assert {k: project["vars"][k] for k in dbt_vars()} == dbt_vars()
    assert project["name"] == PROJECT.dbt_project_name


def test_vocabulary_matches_the_brief() -> None:
    assert PROJECT.side_b == "discogs"
    assert PROJECT.side_a == "musicbrainz", "ADR 0001"
    assert PROJECT.side_a_candidates == ("musicbrainz", "wikidata")
    assert PROJECT.method_versions == ("exact_v1", "rules_v1", "learned_v1")
    assert PROJECT.folds == ("fit", "calibrate", "test")
    assert PROJECT.tiers == ("auto_accept", "review", "reject")


def test_no_frontend_or_serving_configuration() -> None:
    fields = set(PROJECT.as_dict())
    for forbidden in ("hf_space", "api_url", "site_url", "motherduck_database", "schedule_cron"):
        assert forbidden not in fields
