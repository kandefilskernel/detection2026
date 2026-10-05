"""
Diagnostic des courbes d'apprentissage SANS toucher au modèle déployé.

Réentraîne les trois branches avec la configuration de ml.training.train_model (mêmes données, même découpage
temporel, mêmes hyperparamètres), enregistre leurs courbes de perte (entraînement / validation) et écrit :
    ml/artifacts/training_diagnostics.json   lu par le tableau de bord (hors metadata.json : aucun rechargement du modèle)
    ml/reports/training_diagnostics.md       rapport lisible

Usage : python -m ml.training.diagnose_training [--quick]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_engineering import FEATURE_NAMES, PROCESSED_DIR, load_or_build_features
from ml.models.autoencoder_branch import train_autoencoder_branch
from ml.models.lstm_attention_branch import train_lstm_branch
from ml.models.xgboost_branch import train_xgboost_branch
from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR, CLIP, build_sequence_index, temporal_split
from ml.training.diagnostics import summarize_training

REPORTS = Path("ml/reports")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    quick = ap.parse_args().quick
    t0 = time.perf_counter()
    cache = PROCESSED_DIR / "features.csv"
    table = (pd.read_csv(cache, parse_dates=["timestamp"], low_memory=False) if cache.exists()
             else load_or_build_features(cache_path=cache))
    split, _ = temporal_split(pd.to_datetime(table["timestamp"]))
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    X = np.clip(scaler.transform(table[FEATURE_NAMES].to_numpy(np.float32)), -CLIP, CLIP).astype(np.float32)
    y = table["is_fraud"].to_numpy(np.int8)
    seq = build_sequence_index(table["user_id"], 10)
    fit, es = np.flatnonzero(split == 0), np.flatnonzero(split == 1)
    print(f"fit={len(fit):,} early_stop={len(es):,}", flush=True)

    xgb_m = train_xgboost_branch(X[fit], y[fit], X[es], y[es], 150 if quick else 600, 42, record_curves=True)
    ae = train_autoencoder_branch(X[fit][y[fit] == 0], X[es][y[es] == 0], epochs=4 if quick else 30, seed=42, log=lambda m: None)
    lstm = train_lstm_branch(X, y, seq, fit, es, epochs=2 if quick else 8, neg_sample_rate=0.3, seed=42, log=print)
    diag = summarize_training(xgb_m, lstm, ae)
    diag["meta"] = {"quick": quick, "seconds": round(time.perf_counter() - t0), "fit_rows": int(len(fit)), "es_rows": int(len(es))}
    if not quick:
        (ARTIFACTS_DIR / "training_diagnostics.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORTS.mkdir(exist_ok=True)
    L = ["# Courbes d'apprentissage", "",
         f"Réentraînement de diagnostic ({'rapide' if quick else 'configuration complète'}, {diag['meta']['seconds']} s). "
         "Perte d'entraînement comparée à la perte sur la tranche early_stop (données jamais vues pendant l'apprentissage).", "",
         "| Branche | Verdict | Époque retenue | Perte entraînement | Perte validation | Écart de généralisation |", "|---|---|---|---|---|---|"]
    for k, v in diag.items():
        if isinstance(v, dict) and "verdict" in v:
            L.append(f"| {k} ({v['unit']}) | **{v['verdict']}** | {v['best_epoch']}/{v['epochs']} | {v['train_loss_at_best']} | "
                     f"{v['val_loss_at_best']} | {v['generalization_gap']:.1%} |")
    L += ["", *[f"- {k} : {v['reason']}" for k, v in diag.items() if isinstance(v, dict) and "verdict" in v], "",
          f"Pire verdict : **{diag['worst']}**. Blocage du réentraînement automatique : PR-AUC plus basse de plus de 0,05 en validation (`OVERFIT_MAX_METRIC_GAP`), ou, sans PR-AUC, perte de validation plus du double (`OVERFIT_MAX_GAP`).", ""]
    (REPORTS / ("training_diagnostics_quick.md" if quick else "training_diagnostics.md")).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
