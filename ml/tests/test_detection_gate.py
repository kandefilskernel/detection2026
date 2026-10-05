import pytest

from ml.features.feature_engineering import PROCESSED_DIR


@pytest.mark.skipif(not (PROCESSED_DIR / "features.csv").exists(), reason="données de test absentes (python -m ml.features.feature_engineering)")
def test_deployed_model_holds_the_detection_floors():
    from ml.training.detection_gate import check
    r = check()
    assert r["ok"], r["failures"]
