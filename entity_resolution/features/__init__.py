"""The one normalisation and pair-feature module (docs/BRIEF.md rule 5).

``normalize.py`` implements section 2.3; ``blocking.py`` and ``pairs.py`` are added in Phase 3.
``FEATURE_VERSION`` is bumped whenever any of them changes behaviour and travels into every
artifact.
"""

FEATURE_VERSION = "0.1.0"
"""0.1.0: normalisation (2.3) only; no blocking keys or pair features yet."""
