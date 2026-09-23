"""Entry point of the full build (``make full`` -> ``python -m entity_resolution.pipeline.match``).

The stages are filled in by the phases of docs/BRIEF.md section 3: adapters and the sample
(Phase 2), normalisation, blocking, pair features and the split (Phase 3), the three methods,
calibration, tiering, mapping and evaluation (Phase 4). Until then :func:`run` refuses to run
and says which phase it is waiting for, so the entry point exists and nothing pretends to work.
"""

from __future__ import annotations

import sys

from entity_resolution.config import PROJECT

PHASE_STATUS = "Phase 0: chassis only; the pipeline is built in Phases 2 to 4"


class NotBuiltYet(RuntimeError):
    pass


def run(argv: list[str] | None = None) -> int:
    """Run the full build. Raises :class:`NotBuiltYet` until Phase 4 is complete."""
    del argv
    if PROJECT.side_a is None:
        raise NotBuiltYet(
            "side A is undecided (ADR 0001 pending after the Phase 1 profile); " + PHASE_STATUS
        )
    raise NotBuiltYet(PHASE_STATUS)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    try:
        return run(argv)
    except NotBuiltYet as e:
        print(f"make full: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
