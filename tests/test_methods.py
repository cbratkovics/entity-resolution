"""The methods' arithmetic: the exact rule, the rules score and its threshold search on
decisions, the learned model's fold discipline on a synthetic frame."""

from __future__ import annotations

import numpy as np
import pandas as pd

from entity_resolution.features.pairs import PAIR_FEATURES
from entity_resolution.models import exact, labels, learned, rules


def _features(rows: list[dict]) -> pd.DataFrame:
    base = {f: 0.0 for f in PAIR_FEATURES}
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["year_diff"] = out["year_diff"].astype("Int64")
    return out


def test_exact_rule() -> None:
    f = _features(
        [
            {"title_exact_norm": 1, "artist_full_exact": 1, "year_diff": 0},
            {"title_exact_norm": 1, "artist_full_exact": 1, "year_diff": pd.NA},
            {"title_exact_norm": 1, "artist_full_exact": 1, "year_diff": 1},
            {"title_exact_norm": 1, "artist_full_exact": 0, "year_diff": 0},
        ]
    )
    assert list(exact.score(f)) == [1.0, 1.0, 0.0, 0.0]


def test_rules_score_arithmetic() -> None:
    f = _features(
        [
            {"title_token_set": 1.0, "artist_token_set": 1.0, "year_diff": 0},
            {"title_token_set": 0.5, "artist_token_set": 1.0, "year_diff": 1},
            {"title_token_set": 1.0, "artist_token_set": 0.0, "year_diff": pd.NA},
            {"title_token_set": 0.0, "artist_token_set": 0.0, "year_diff": 7},
        ]
    )
    s = rules.score(f)
    assert s[0] == 1.0
    assert abs(s[1] - (0.45 * 0.5 + 0.35 * 1.0 + 0.20 * 0.5)) < 1e-12
    assert abs(s[2] - (0.45 + 0.20 * 0.25)) < 1e-12
    assert s[3] == 0.0


def test_rules_threshold_search_on_decisions() -> None:
    decisions = pd.DataFrame(
        {
            "score": [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2],
            "correct": [True, True, True, True, False, False, True, False],
        }
    )
    fitted = rules.fit_thresholds(decisions, n_recall_base=8)
    # F1 by cut: k=4 -> P=1, R=0.5, F1=0.667; k=7 -> P=5/7, R=5/8, F1=0.667; k=8 -> 5/8,5/8 -> 0.625
    assert fitted["t_accept"] == 0.6  # ties go to the higher threshold
    # cumulative precision first drops below 0.5? never: min precision is 5/8 -> t_review = last score
    assert fitted["t_review"] == 0.2
    assert fitted["decisions_searched"] == 8 and fitted["recall_base"] == 8
    d2 = pd.DataFrame({"score": [0.9, 0.8, 0.7, 0.6], "correct": [True, False, False, False]})
    f2 = rules.fit_thresholds(d2, n_recall_base=1)
    assert f2["t_accept"] == 0.9 and f2["t_review"] == 0.7  # precision 1/3 < 0.5 at score 0.7


def test_labels_and_learned_fold_discipline() -> None:
    truth = pd.DataFrame({"a_id": ["a1", "a1", "a2"], "b_id": ["1", "2", "3"]})
    lab = labels.from_truth(truth)
    assert lab.is_correct("a1", "2") and not lab.is_correct("a2", "1")
    pairs = pd.DataFrame({"a_id": ["a1", "a1", "a2", "a9"], "b_id": ["1", "5", "3", "7"]})
    got = lab.pair_labels(pairs)
    assert list(got[:3]) == [1, 0, 1] and pd.isna(got[3])
    rng = np.random.default_rng(0)
    n = 400
    f = _features([{"title_ratio": float(x), "artist_ratio": float(x)} for x in rng.random(n)])
    f["a_id"] = [f"a{i}" for i in range(n)]
    f["b_id"] = [f"b{i}" for i in range(n)]
    y = (f["title_ratio"] > 0.5).to_numpy(dtype="int64")
    model = learned.fit(f.iloc[:300], y[:300], f.iloc[300:], y[300:])
    assert model.n_fit == 300 and model.n_calibrate == 100
    assert model.fit_index_sha256 == learned.index_sha256(f.iloc[:300])
    assert model.fit_index_sha256 != model.calibrate_index_sha256
    p = model.probability(model.raw(f))
    assert p.min() >= 0.0 and p.max() <= 1.0
    assert p[f["title_ratio"] > 0.9].mean() > p[f["title_ratio"] < 0.1].mean()
