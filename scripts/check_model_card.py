#!/usr/bin/env python
"""Regenerate docs/METHODS_CARD.md from the committed artifacts, or fail when it carries a
placeholder or differs from what the artifacts render.

    python scripts/check_model_card.py --write     # render the card from artifacts/
    python scripts/check_model_card.py             # check: no placeholder markers, byte-equal to a fresh render

The rendering is a pure function of the artifacts (entity_resolution.eval.methods_card), so the
check is exact: a hand edit or a stale card fails CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run without installing

import argparse
import re

from entity_resolution.eval import methods_card

MARKERS = (
    re.compile(r"\bTBD\b"),
    re.compile(r"\bXX\.?X*\b"),
    re.compile(r"PLACEHOLDER", re.IGNORECASE),
    re.compile(r"\{\{\s*[a-z_]+\s*\}\}"),  # unrendered template expression
    re.compile(r"<fill[^>]*>", re.IGNORECASE),
)


def find_placeholders(text: str) -> list[str]:
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in MARKERS:
            if m.search(line):
                hits.append(f"{i}: {line.strip()[:100]}")
                break
    return hits


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--path", type=Path, default=methods_card.CARD_PATH)
    p.add_argument("--write", action="store_true", help="render the card instead of checking it")
    a = p.parse_args(argv)
    rendered = methods_card.render_from_tree()
    if a.write:
        a.path.parent.mkdir(parents=True, exist_ok=True)
        a.path.write_text(rendered, encoding="utf-8")
        print(f"wrote {a.path}")
        return 0
    if not a.path.exists():
        print(f"{a.path}: missing; run with --write")
        return 1
    text = a.path.read_text(encoding="utf-8")
    hits = find_placeholders(text)
    for h in hits:
        print(f"{a.path}:{h}")
    if text != rendered:
        print(f"{a.path}: differs from a fresh render of the artifacts; run with --write")
        return 1
    if hits:
        print(f"{a.path}: {len(hits)} placeholder line(s)")
        return 1
    print(f"ok: {a.path} has no placeholders and matches the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
