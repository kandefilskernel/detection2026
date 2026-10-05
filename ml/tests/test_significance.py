import numpy as np

from ml.training.significance import cluster_resample, mcnemar_exact, paired_bootstrap


def _data(n_users=400, per_user=10, seed=0):
    rng = np.random.default_rng(seed)
    users = np.repeat(np.arange(n_users), per_user)
    y = (rng.random(len(users)) < 0.05).astype(int)
    good = y * 2.0 + rng.normal(size=len(users))      # modèle informatif
    noise = rng.normal(size=len(users))               # modèle aléatoire
    return y, users, good, noise


def test_cluster_resample_keeps_whole_users():
    users = np.repeat(np.arange(50), 4)
    idx = cluster_resample(users, np.random.default_rng(1))
    counts = np.bincount(users[idx], minlength=50)
    assert set(counts) <= {0, 4, 8, 12, 16, 20}      # un usager est toujours repris en entier
    assert len(idx) == 200


def test_paired_bootstrap_detects_real_difference():
    y, users, good, noise = _data()
    r = paired_bootstrap(y, {"good": good, "noise": noise}, users, reference="good", n_boot=60, seed=3)
    assert r["noise"]["pr_auc"]["diff_vs_reference"] < 0
    assert r["noise"]["pr_auc"]["significant_95"] is True
    lo, hi = r["good"]["pr_auc"]["ci95"]
    assert lo <= r["good"]["pr_auc"]["point"] <= hi


def test_paired_bootstrap_identical_models_not_significant():
    y, users, good, _ = _data()
    r = paired_bootstrap(y, {"a": good, "b": good.copy()}, users, reference="a", n_boot=40, seed=3)
    assert r["b"]["pr_auc"]["diff_vs_reference"] == 0
    assert r["b"]["pr_auc"]["significant_95"] is False


def test_mcnemar():
    y = np.array([1] * 40 + [0] * 60)
    a = y.copy()
    b = y.copy()
    b[:20] = 0                                         # b se trompe 20 fois de plus, a jamais
    assert mcnemar_exact(y, a, b)["significant_95"] is True
    assert mcnemar_exact(y, a, a)["p_value"] == 1.0
