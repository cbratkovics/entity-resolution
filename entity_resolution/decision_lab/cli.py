"""``python -m entity_resolution.decision_lab.cli <command>`` (docs/DECISION_LAB.md section 9).

- ``export [--out artifacts/lab] [--no-local]``: build the export (see :mod:`export`).
- ``check [--out artifacts/lab]``: verify the export in place; exit 1 on any problem.
- ``fixtures``: write ``apps/decision-lab/fixtures/policy_fixtures.json``.
- ``synthetic``: write ``apps/decision-lab/fixtures/synthetic_sandbox.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from entity_resolution.config import LAB_ARTIFACT_DIR, LAB_FIXTURES_DIR, REPO_ROOT
from entity_resolution.decision_lab import export, fixtures, synthetic


def _layout(out: str | None) -> export.Layout:
    layout = export.Layout()
    if out:
        layout.lab_dir = Path(out).resolve()
    return layout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m entity_resolution.decision_lab.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export", help="build artifacts/lab and the app fixtures")
    p_export.add_argument("--out", default=str(LAB_ARTIFACT_DIR), help="lab output directory")
    p_export.add_argument("--no-local", action="store_true", help="skip the owner-run local stages")
    p_check = sub.add_parser("check", help="verify the export without writing")
    p_check.add_argument("--out", default=str(LAB_ARTIFACT_DIR), help="lab directory to check")
    sub.add_parser("fixtures", help="write the shared policy fixtures")
    sub.add_parser("synthetic", help="write the synthetic sandbox fixture")
    args = parser.parse_args(argv)
    if args.command == "export":
        try:
            export.export(_layout(args.out), no_local=args.no_local)
        except (
            export.ExportRefused,
            export.replay.LocalInputError,
            export.replay.ReplayError,
        ) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        result = export.check(_layout(args.out))
        if not result.ok:
            for p in result.problems:
                print(f"problem: {p}", file=sys.stderr)
            print("error: the export did not pass its own check", file=sys.stderr)
            return 1
        print(f"ok: {result.files} files, {result.checks} checks")
        return 0
    if args.command == "check":
        return export.main_check(_layout(args.out))
    if args.command == "fixtures":
        print(f"wrote {fixtures.write().relative_to(REPO_ROOT)}")
        return 0
    if args.command == "synthetic":
        synthetic.write()
        print(f"wrote {(LAB_FIXTURES_DIR / 'synthetic_sandbox.json').relative_to(REPO_ROOT)}")
        return 0
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
