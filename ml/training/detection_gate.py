"""
Garde-fou de non-régression de la DÉTECTION : le modèle en place tient-il encore ses planchers sur le jeu de test
(période jamais vue à l'entraînement) ? À lancer après tout changement de code ou de modèle ; code de sortie 1 si un
plancher n'est plus tenu.

Planchers (volontairement en dessous des résultats mesurés, pour ne bloquer que de vraies dégradations) :
    PR-AUC globale ≥ 0,975 ; PR-AUC Mobile Money ≥ 0,97 ; rappel à 1 % de faux positifs ≥ 0,98 ;
    taux de faux positifs ≤ 0,2 % ; rappel par typologie ≥ 0,95 (0,90 pour le fractionnement, 0,55 pour
    l'ingénierie sociale, typologie la plus difficile).

Usage : python -m ml.training.detection_gate
"""
from __future__ import annotations

import json
import sys

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_engineering import FEATURE_NAMES, PROCESSED_DIR
from ml.models.hybrid_ensemble import HybridEnsemble
from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR, CLIP, build_sequence_index, temporal_split
from ml.training.evaluation import evaluate, recall_by_fraud_type

FLOORS = {"pr_auc": 0.975, "pr_auc_mobile_money": 0.97, "recall_at_1pct_fpr": 0.98, "false_positive_rate_max": 0.002,
          "recall_by_type": {"default": 0.95, "SMURFING": 0.90, "SOCIAL_ENGINEERING": 0.55}}


def check() -> dict:
    table = pd.read_csv(PROCESSED_DIR / "features.csv", parse_dates=["timestamp"], low_memory=False)
    split, _ = temporal_split(table["timestamp"])
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    X = np.clip(scaler.transform(table[FEATURE_NAMES].to_numpy(np.float32)), -CLIP, CLIP).astype(np.float32)
    y = table["is_fraud"].to_numpy()
    seq = build_sequence_index(table["user_id"], 10)
    model = HybridEnsemble.load(ARTIFACTS_DIR)
    test = np.flatnonzero(split == 3)
    p = model.predict_proba(X, seq, test)
    thr = float(model.threshold)
    allm = evaluate(y[test], p, thr)
    mm = test[table["channel"].to_numpy()[test] == "MOBILE_MONEY"]
    mmm = evaluate(y[mm], model.predict_proba(X, seq, mm), thr)
    by_type = recall_by_fraud_type(y[test], p, thr, table["fraud_type"].to_numpy()[test])
    fails = []
    def need(name, value, floor, upper=False):
        ok = value <= floor if upper else value >= floor
        if not ok:
            fails.append(f"{name} = {value} ({'plafond' if upper else 'plancher'} {floor})")
    need("PR-AUC", allm["pr_auc"], FLOORS["pr_auc"])
    need("PR-AUC Mobile Money", mmm["pr_auc"], FLOORS["pr_auc_mobile_money"])
    need("rappel à 1 % de faux positifs", allm["recall_at_1pct_fpr"], FLOORS["recall_at_1pct_fpr"])
    need("taux de faux positifs", allm["false_positive_rate"], FLOORS["false_positive_rate_max"], upper=True)
    for t, v in by_type.items():
        need(f"rappel {t}", v["recall"], FLOORS["recall_by_type"].get(t, FLOORS["recall_by_type"]["default"]))
    return {"ok": not fails, "failures": fails, "threshold": thr, "global": allm, "mobile_money": mmm, "recall_by_type": by_type}


if __name__ == "__main__":
    r = check()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print("PLANCHERS TENUS" if r["ok"] else "RÉGRESSION : " + " ; ".join(r["failures"]))
    sys.exit(0 if r["ok"] else 1)
