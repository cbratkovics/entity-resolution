"""``exact_v1`` (docs/BRIEF.md 2.7): accept iff the normalised titles are equal, the full artist
credits are equal and the year difference is 0 or unknown. Nothing is fitted; the score is 0
or 1 and is used as the probability, so its calibration table shows what an uncalibrated rule
looks like."""

from __future__ import annotations

import numpy as np
import pandas as pd

METHOD_VERSION = "exact_v1"
DEFINITION = (
    "accept iff title_exact_norm and artist_full_exact and year_diff in {0, missing}; score in "
    "{0, 1} used as the probability; nothing fitted"
)


def score(features: pd.DataFrame) -> np.ndarray:
    year_ok = features["year_diff"].isna() | (features["year_diff"] == 0)
    hit = (features["title_exact_norm"] == 1) & (features["artist_full_exact"] == 1) & year_ok
    return hit.to_numpy(dtype="float64")
