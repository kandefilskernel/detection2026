import numpy as np
import pytest

from ml.training.train_fraud_type import TYPES_BY_CHANNEL, restrict


def test_restrict_zeroes_types_impossible_for_the_channel():
    classes = sorted(t for ts in TYPES_BY_CHANNEL.values() for t in ts)
    proba = np.full((2, len(classes)), 1 / len(classes))
    out = restrict(proba, classes, np.array(["MOBILE_MONEY", "VISA_VIRTUAL"]))
    assert np.allclose(out.sum(axis=1), 1.0)
    for row, ch in zip(out, ("MOBILE_MONEY", "VISA_VIRTUAL")):
        assert {c for c, p in zip(classes, row) if p > 0} == set(TYPES_BY_CHANNEL[ch])


def test_scorer_returns_channel_consistent_type():
    from pathlib import Path

    from ml.serving.scorer import HybridScorer
    if not Path("ml/artifacts/fraud_type_xgb.pkl").exists():
        pytest.skip("classifieur de typologie non entraîné")
    s = HybridScorer("ml/artifacts")
    x = np.zeros(len(s.feature_names), dtype=np.float32)
    for ch, allowed in TYPES_BY_CHANNEL.items():
        t, p, cands = s.classify_fraud_type(x, ch)
        assert t in allowed and 0 < p <= 1 and all(c["type"] in allowed for c in cands)
