"""The site reads only data/<gold model>.json files that export_gold produces, and never
types a number of its own (the number checker covers docs/site; this test covers the wiring)."""

from __future__ import annotations

import json
import re

from entity_resolution.config import REPO_ROOT, SITE_DATA_DIR

GOLD_DIR = REPO_ROOT / "dbt" / "models" / "gold"
SITE = REPO_ROOT / "docs" / "site" / "index.html"


def _gold_models() -> set[str]:
    return {p.stem for p in GOLD_DIR.glob("*.sql")}


def test_every_data_file_the_site_loads_is_a_gold_model() -> None:
    html = SITE.read_text(encoding="utf-8")
    loaded = set(re.findall(r"load\('([a-z_]+)'\)", html))
    assert loaded, "the site loads nothing"
    assert loaded <= _gold_models(), loaded - _gold_models()


def test_exported_json_when_present_is_a_list_of_rows() -> None:
    if not SITE_DATA_DIR.exists():
        return
    for p in SITE_DATA_DIR.glob("fct_*.json"):
        rows = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(rows, list), p.name
        if rows:
            assert isinstance(rows[0], dict), p.name


def test_site_has_no_build_step_or_external_script() -> None:
    html = SITE.read_text(encoding="utf-8")
    assert "<script src=" not in html and "import " not in html.split("<script>")[1]


def test_every_field_the_page_reads_exists_in_the_export() -> None:
    """For each data file the page loads, every `r.<field>` the script reads is a column of the
    exported rows (checked only when the export is present)."""
    html = SITE.read_text(encoding="utf-8")
    script = html.split("<script>")[1]
    if not SITE_DATA_DIR.exists():
        return
    fields = set(re.findall(r"\br\.([a-z_]+)\b", script)) - {"json", "ok"}  # fetch response
    exported: dict[str, set[str]] = {}
    for name in re.findall(r"load\('([a-z_]+)'\)", html):
        path = SITE_DATA_DIR / f"{name}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if rows:
            exported[name] = set(rows[0])
    if not exported:
        return
    known = set().union(*exported.values())
    unknown = {f for f in fields if f not in known}
    assert not unknown, f"fields read by the page but exported by no model: {sorted(unknown)}"
