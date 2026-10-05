import numpy as np

from ml.models.autoencoder_branch import train_autoencoder_branch
from ml.models.xgboost_branch import train_xgboost_branch
from ml.training.diagnostics import analyze_curve, summarize_training, xgb_curves


def test_healthy_curves_are_reported_healthy():
    tr = [0.9, 0.5, 0.3, 0.25, 0.24]
    va = [0.95, 0.55, 0.33, 0.28, 0.27]
    r = analyze_curve(tr, va, best_epoch=5, stopped_early=False)
    assert r["verdict"] in ("SAIN", "SOUS_APPRENTISSAGE") and r["generalization_gap"] < 0.2


def test_validation_loss_far_above_training_is_a_net_overfit():
    r = analyze_curve([0.2, 0.1, 0.05, 0.02], [0.3, 0.28, 0.27, 0.26], best_epoch=4)
    assert r["verdict"] == "SURAPPRENTISSAGE_NET" and r["generalization_gap"] > 1


def test_rising_validation_with_falling_training_is_a_light_overfit():
    tr = [0.5, 0.4, 0.3, 0.2, 0.15, 0.12]
    va = [0.52, 0.45, 0.40, 0.41, 0.44, 0.47]
    r = analyze_curve(tr, va, best_epoch=3, stopped_early=True)
    assert r["verdict"] == "SURAPPRENTISSAGE_LEGER" and r["val_rise_after_best"] > 0.05


def test_tiny_losses_with_equal_pr_auc_are_not_a_net_overfit():
    # cas réel du jeu 2019-2025 : logloss 0,0009 (entraînement) contre 0,0046 (validation), PR-AUC 1,000 contre 0,994
    r = analyze_curve([0.01, 0.003, 0.0009], [0.012, 0.006, 0.0046], best_epoch=3,
                      train_metric=[0.98, 0.999, 1.0], val_metric=[0.97, 0.99, 0.994])
    assert r["verdict"] == "SURAPPRENTISSAGE_LEGER" and r["metric_gap"] < 0.01 and r["generalization_gap"] > 1


def test_large_pr_auc_gap_is_a_net_overfit():
    r = analyze_curve([0.1, 0.05], [0.12, 0.1], best_epoch=2, train_metric=[0.95, 0.99], val_metric=[0.9, 0.9])
    assert r["verdict"] == "SURAPPRENTISSAGE_NET"


def test_empty_or_inconsistent_curves_are_unknown():
    assert analyze_curve([], [])["verdict"] == "INCONNU"
    assert analyze_curve([1.0, 2.0], [1.0])["verdict"] == "INCONNU"


def test_xgboost_curves_are_recorded_only_on_demand():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(3000, 6)).astype(np.float32)
    y = (X[:, 0] + rng.normal(0, 0.5, 3000) > 1.5).astype(np.int8)
    plain = train_xgboost_branch(X[:2000], y[:2000], X[2000:], y[2000:], 30)
    assert xgb_curves(plain) is None
    rec = train_xgboost_branch(X[:2000], y[:2000], X[2000:], y[2000:], 30, record_curves=True)
    tr, va = xgb_curves(rec)
    assert len(tr) == len(va) >= 1 and tr[0] > tr[-1]                   # l'entraînement s'améliore


def test_autoencoder_history_and_summary():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(2000, 8)).astype(np.float32)
    ae = train_autoencoder_branch(X[:1500], X[1500:], epochs=5, log=lambda m: None)
    assert len(ae.history) >= 1 and {"epoch", "train_loss", "val_loss"} <= set(ae.history[0])
    s = summarize_training(None, None, ae)
    assert "autoencoder" in s and s["worst"] in ("SAIN", "SOUS_APPRENTISSAGE", "SURAPPRENTISSAGE_LEGER", "SURAPPRENTISSAGE_NET")
    assert s["overfit_net"] in (True, False) and summarize_training()["worst"] == "INCONNU"
