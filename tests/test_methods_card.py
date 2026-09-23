"""The methods card is a pure function of the artifacts: byte-stable and placeholder-free."""

from __future__ import annotations

import sys
from pathlib import Path

from entity_resolution.eval import methods_card

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_model_card  # noqa: E402


def test_render_is_byte_stable_and_free_of_placeholders() -> None:
    first = methods_card.render_from_tree()
    second = methods_card.render_from_tree()
    assert first == second
    assert check_model_card.find_placeholders(first) == []


def test_empty_tree_renders_an_explicit_no_run_card(tmp_path) -> None:
    from entity_resolution.models import registry

    art = tmp_path / "artifacts"
    (art / "methods").mkdir(parents=True)
    registry.write_manifest(registry.empty_manifest("unknown"), art / "manifest.json")
    text = methods_card.render_from_tree(artifacts=art, methods_dir=art / "methods")
    assert "No run has been recorded" in text
    assert "artifacts/manifest.json#feature_version" in text


def test_real_tree_card_has_a_results_row_per_method() -> None:
    from entity_resolution.config import ARTIFACTS_DIR

    if not list(ARTIFACTS_DIR.glob("eval_*.json")):
        return
    text = methods_card.render_from_tree()
    for m in ("exact_v1", "rules_v1", "learned_v1"):
        assert f"| `{m}` |" in text
