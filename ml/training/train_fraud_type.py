"""
Identification du TYPE de fraude (SIM_SWAP, SOCIAL_ENGINEERING, SMURFING, ...).

Second étage du système : le modèle hybride dit SI une transaction est frauduleuse ;
ce classifieur multi-classes dit, pour une transaction suspecte, QUELLE typologie de
fraude elle ressemble le plus. Il n'est consulté que pour les transactions signalées,
et ses probabilités sont restreintes aux typologies possibles pour le canal
(Mobile Money : 5 typologies ; Visa virtuelle : 3).

    - entraîné sur les seules transactions frauduleuses de la période d'entraînement
      (arrêt précoce sur la période early_stop), poids de classes équilibrés
    - mêmes variables normalisées que le modèle hybride (scaler.pkl figé) : aucun
      calcul supplémentaire en production
    - évalué UNE fois sur les fraudes du test : exactitude, F1 macro, rappel et précision
      par typologie, matrice de confusion, comparé à la classe majoritaire du canal

Usage (depuis la racine du projet, après la génération des variables) :
    python -m ml.training.train_fraud_type
Sorties : ml/artifacts/fraud_type_xgb.pkl, fraud_types.json ; ml/reports/fraud_type_results.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.utils.class_weight import compute_sample_weight

from ml.features.feature_engineering import FEATURE_NAMES, PROCESSED_DIR, load_or_build_features
from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR, CLIP, temporal_split

REPORTS_DIR = Path("ml/reports")
MODEL_FILE, LABELS_FILE = "fraud_type_xgb.pkl", "fraud_types.json"

# Typologies possibles par canal (cf. générateur : 5 Mobile Money, 3 Visa virtuelle)
TYPES_BY_CHANNEL = {
    "MOBILE_MONEY": ["SIM_SWAP", "SOCIAL_ENGINEERING", "ACCOUNT_TAKEOVER", "AGENT_FRAUD", "SMURFING"],
    "VISA_VIRTUAL": ["CARD_TESTING", "CNP_FRAUD", "TOPUP_DRAIN"],
}
# Libellés d'affichage (repris par le tableau de bord)
TYPE_LABELS_FR = {
    "SIM_SWAP": "Échange de SIM",
    "SOCIAL_ENGINEERING": "Ingénierie sociale",
    "ACCOUNT_TAKEOVER": "Prise de contrôle de compte",
    "AGENT_FRAUD": "Fraude d'agent",
    "SMURFING": "Fractionnement (smurfing)",
    "CARD_TESTING": "Test de carte",
    "CNP_FRAUD": "Fraude carte non présente",
    "TOPUP_DRAIN": "Vidage par rechargement",
}


def load_scaled(table: pd.DataFrame, scaler) -> np.ndarray:
    raw = table[FEATURE_NAMES].to_numpy(dtype=np.float32)
    return np.clip(scaler.transform(raw), -CLIP, CLIP).astype(np.float32)


def restrict(proba: np.ndarray, classes: list[str], channels: np.ndarray) -> np.ndarray:
    """Met à zéro les typologies impossibles pour le canal puis renormalise."""
    out = proba.copy()
    for ch, allowed in TYPES_BY_CHANNEL.items():
        keep = np.array([c in allowed for c in classes])
        rows = channels == ch
        out[np.ix_(rows, ~keep)] = 0.0
    sums = out.sum(axis=1, keepdims=True)
    return out / np.where(sums == 0, 1.0, sums)


def run(n_estimators: int = 400, seed: int = 42) -> dict:
    t0 = time.perf_counter()
    cache = PROCESSED_DIR / "features.csv"
    table = (pd.read_csv(cache, parse_dates=["timestamp"], low_memory=False) if cache.exists()
             else load_or_build_features(cache_path=cache))
    table["timestamp"] = pd.to_datetime(table["timestamp"])
    split, bounds = temporal_split(table["timestamp"])
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    X = load_scaled(table, scaler)
    fraud = (table["is_fraud"] == 1).to_numpy()
    classes = sorted(t for ts in TYPES_BY_CHANNEL.values() for t in ts)
    code = {c: i for i, c in enumerate(classes)}
    unknown = set(table.loc[fraud, "fraud_type"].dropna()) - set(classes)
    assert not unknown, f"typologies inconnues dans les données : {unknown}"
    y = np.full(len(table), -1, dtype=np.int64)
    y[fraud] = table.loc[fraud, "fraud_type"].map(code).to_numpy()

    fit, es, test = fraud & (split == 0), fraud & (split == 1), fraud & (split == 3)
    # le canal et le type de transaction sont connus en production : ils restent des variables
    model = xgb.XGBClassifier(
        objective="multi:softprob", n_estimators=n_estimators, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=2, tree_method="hist",
        eval_metric="mlogloss", early_stopping_rounds=40, random_state=seed, n_jobs=-1)
    model.fit(X[fit], y[fit], sample_weight=compute_sample_weight("balanced", y[fit]),
              eval_set=[(X[es], y[es])], verbose=False)

    channels = table["channel"].to_numpy()
    proba = restrict(model.predict_proba(X[test]), classes, channels[test])
    pred = proba.argmax(axis=1)
    yt = y[test]
    p, r, f, n = precision_recall_fscore_support(yt, pred, labels=list(range(len(classes))), zero_division=0)
    # référence : toujours la typologie la plus fréquente du canal (entraînement)
    major = {ch: max(allowed, key=lambda t: int(((y[fit] == code[t]) & (channels[fit] == ch)).sum()))
             for ch, allowed in TYPES_BY_CHANNEL.items()}
    base_pred = np.array([code[major[c]] for c in channels[test]])
    per_class = {c: {"n": int(n[i]), "precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
                     "f1": round(float(f[i]), 4)} for i, c in enumerate(classes)}
    by_channel = {}
    for ch in TYPES_BY_CHANNEL:
        m = channels[test] == ch
        by_channel[ch] = {"n": int(m.sum()), "accuracy": round(float(accuracy_score(yt[m], pred[m])), 4),
                          "macro_f1": round(float(f1_score(yt[m], pred[m], average="macro",
                                                           labels=sorted({code[t] for t in TYPES_BY_CHANNEL[ch]}),
                                                           zero_division=0)), 4)}
    top2 = np.argsort(-proba, axis=1)[:, :2]
    results = {
        "n_train": int(fit.sum()), "n_test": int(test.sum()), "classes": classes,
        "accuracy": round(float(accuracy_score(yt, pred)), 4),
        "top2_accuracy": round(float(np.mean([yt[i] in top2[i] for i in range(len(yt))])), 4),
        "macro_f1": round(float(f1_score(yt, pred, average="macro", zero_division=0)), 4),
        "baseline_majority_accuracy": round(float(accuracy_score(yt, base_pred)), 4),
        "per_class": per_class, "by_channel": by_channel,
        "confusion_matrix": confusion_matrix(yt, pred, labels=list(range(len(classes)))).tolist(),
        "best_iteration": int(model.best_iteration), "split_bounds": bounds,
        "note": "Étiquettes issues du générateur synthétique : les typologies sont celles que le simulateur injecte.",
        "seconds": round(time.perf_counter() - t0),
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "best_iteration": int(model.best_iteration)}, ARTIFACTS_DIR / MODEL_FILE)
    (ARTIFACTS_DIR / LABELS_FILE).write_text(json.dumps(
        {"classes": classes, "types_by_channel": TYPES_BY_CHANNEL, "labels_fr": TYPE_LABELS_FR,
         "feature_names": FEATURE_NAMES}, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "fraud_type_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")
    return results


if __name__ == "__main__":
    res = run()
    print(f"exactitude {res['accuracy']} (référence classe majoritaire {res['baseline_majority_accuracy']}), "
          f"F1 macro {res['macro_f1']}, top-2 {res['top2_accuracy']}")
    for c, v in res["per_class"].items():
        print(f"  {c:<20} n={v['n']:>4}  précision={v['precision']:.3f}  rappel={v['recall']:.3f}")
    print(f"[OK] -> {ARTIFACTS_DIR / MODEL_FILE}")
