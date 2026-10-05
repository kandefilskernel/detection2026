import numpy as np

from ml.monitoring.drift_detector import novelty
from ml.retraining.scheduler import Config, decide, outcome

CFG = Config(new_labels=500, new_tx=20000, max_age_h=168, cooldown_h=6, min_labeled=2000, min_frauds=30)
BASE = dict(new_labels=0, new_fraud_labels=0, new_tx=0, labeled_total=5000, matured_unlabeled=0, frauds_total=100,
            age_h=10.0, since_last_run_h=None, drift_alarm=False, novelty_alarm=False, novelty_rate=0.01,
            drifted_features=0)


def sig(**kw):
    return {**BASE, **kw}


def test_nothing_to_do_without_signal():
    d = decide(sig(), CFG)
    assert d["reasons"] == [] and d["ready"] and not d["cooldown"]


def test_each_signal_gives_its_own_reason():
    assert "nouveaux comportements détectés" in decide(sig(novelty_alarm=True), CFG)["reasons"]
    assert "dérive des variables comportementales" in decide(sig(drift_alarm=True), CFG)["reasons"]
    assert any("nouvelles étiquettes" in r for r in decide(sig(new_labels=600), CFG)["reasons"])
    assert any("nouvelles transactions" in r for r in decide(sig(new_tx=25000), CFG)["reasons"])
    assert any("vieux" in r for r in decide(sig(age_h=200.0), CFG)["reasons"])
    assert len(decide(sig(novelty_alarm=True, drift_alarm=True, new_labels=900), CFG)["reasons"]) == 3


def test_not_ready_without_enough_labels_or_confirmed_frauds():
    d = decide(sig(labeled_total=1, matured_unlabeled=0, frauds_total=1, novelty_alarm=True), CFG)
    assert not d["ready"] and d["missing"] == {"etiquettes": 1999, "fraudes_confirmees": 29}
    # des transactions « mûres » comptent comme légitimes, mais jamais comme fraudes
    d = decide(sig(labeled_total=1, matured_unlabeled=4000, frauds_total=1), CFG)
    assert d["missing"] == {"etiquettes": 0, "fraudes_confirmees": 29} and not d["ready"]


def test_cooldown_after_a_recent_run():
    assert decide(sig(since_last_run_h=1.0, drift_alarm=True), CFG)["cooldown"]
    assert not decide(sig(since_last_run_h=7.0, drift_alarm=True), CFG)["cooldown"]


def test_outcome_keeps_the_useful_fields():
    status, detail = outcome({"status": "REJETE", "version": "v1", "champion": {"pr_auc": 0.9},
                              "challenger": {"pr_auc": 0.8}, "candidate_dir": "x", "junk": 1})
    assert status == "REJETE" and set(detail) == {"version", "champion", "challenger"}


def test_novelty_is_low_on_the_same_distribution_and_alarms_on_new_behaviors():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 10000)
    same = novelty(ref, rng.normal(0, 1, 2000))
    assert same["rate"] < 0.03 and not same["alarm"]
    # 10 % des transactions ont un comportement jamais vu (erreur de reconstruction très élevée)
    cur = np.concatenate([rng.normal(0, 1, 1800), rng.normal(5, 1, 200)])
    new = novelty(ref, cur)
    assert new["rate"] >= 0.09 and new["alarm"]
    assert not novelty(ref, cur[:100], min_window=500)["alarm"]       # fenêtre trop petite : pas d'alarme
