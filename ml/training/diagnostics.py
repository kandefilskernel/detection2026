"""
Diagnostic des courbes d'apprentissage : le modèle apprend-il ou apprend-il par cœur ?

Pour chaque branche (XGBoost, LSTM, autoencodeur) on compare la perte sur l'ENTRAÎNEMENT à la perte sur
des données jamais vues pendant l'apprentissage (tranche early_stop), à la même distribution :

    écart de généralisation  G = (perte_validation − perte_entraînement) / perte_entraînement
        à l'époque retenue par l'arrêt précoce (celle du modèle réellement conservé)
    remontée                 R = (perte_validation_finale − perte_validation_minimale) / perte_validation_minimale
        si la perte de validation remonte alors que celle d'entraînement baisse : surapprentissage constaté

Quand la PR-AUC est disponible sur l'entraînement et la validation (XGBoost, LSTM), le verdict « net » se fonde sur
l'ÉCART DE PERFORMANCE  M = PR-AUC_entraînement − PR-AUC_validation, et non sur le rapport des pertes : quand les
pertes sont minuscules (0,0009 contre 0,0046), leur rapport explose sans que le modèle généralise mal.

Verdicts :
    SURAPPRENTISSAGE_NET  M > MAX_METRIC_GAP (0,05) ; sans PR-AUC : G > MAX_GAP (1,0 : perte inconnue > double de la connue)
                          → le nouveau modèle est refusé par le réentraînement automatique
    SURAPPRENTISSAGE_LEGER  M > 0,02, ou G > 0,3, ou R > 5 % avec une perte d'entraînement qui baisse
                          → signalé, non bloquant (l'arrêt précoce restaure la meilleure époque)
    SOUS_APPRENTISSAGE    perte d'entraînement encore élevée et en baisse à la dernière époque, sans arrêt précoce
                          → davantage d'époques pourraient aider
    SAIN                  sinon

Les seuils sont des conventions de lecture, réglables : MAX_GAP via la variable d'environnement OVERFIT_MAX_GAP.
Un écart de perte est une information sur l'apprentissage, pas une garantie sur les performances en production.
"""
from __future__ import annotations

import os

import numpy as np

MAX_GAP = float(os.getenv("OVERFIT_MAX_GAP", "1.0"))
MAX_METRIC_GAP = float(os.getenv("OVERFIT_MAX_METRIC_GAP", "0.05"))
LIGHT_METRIC_GAP = 0.02
LIGHT_GAP = 0.3
RISE = 0.05


def analyze_curve(train: list[float], val: list[float], best_epoch: int | None = None, stopped_early: bool = False,
                  train_metric: list[float] | None = None, val_metric: list[float] | None = None) -> dict:
    """train / val : pertes par époque (ou itération), mêmes longueurs. best_epoch est numéroté à partir de 1."""
    train, val = np.asarray(train, float), np.asarray(val, float)
    n = len(val)
    if n == 0 or len(train) != n:
        return {"verdict": "INCONNU", "reason": "courbes absentes"}
    b = (best_epoch if best_epoch else int(np.argmin(val)) + 1) - 1
    b = min(max(b, 0), n - 1)
    gap = float((val[b] - train[b]) / max(abs(train[b]), 1e-9))
    rise = float((val[-1] - val.min()) / max(abs(val.min()), 1e-9))
    train_falling = n >= 3 and train[-1] < train[max(b, 0)] - 1e-12
    mgap = (float(train_metric[b]) - float(val_metric[b])
            if train_metric is not None and val_metric is not None and len(train_metric) == n == len(val_metric) else None)
    if mgap is not None:
        if mgap > MAX_METRIC_GAP:
            verdict, why = "SURAPPRENTISSAGE_NET", f"PR-AUC plus basse de {mgap:.3f} en validation qu'à l'entraînement"
        elif mgap > LIGHT_METRIC_GAP:
            verdict, why = "SURAPPRENTISSAGE_LEGER", f"PR-AUC plus basse de {mgap:.3f} en validation"
        elif gap > LIGHT_GAP:
            verdict = "SURAPPRENTISSAGE_LEGER"
            why = (f"perte de validation {gap:.0%} au-dessus de celle d'entraînement mais PR-AUC quasi identique (écart "
                   f"{mgap:.3f}) : modèle très confiant sur ses données d'entraînement, sans perte de performance")
        elif rise > RISE and train_falling:
            verdict, why = "SURAPPRENTISSAGE_LEGER", f"la perte de validation remonte de {rise:.0%} alors que celle d'entraînement baisse"
        else:
            verdict, why = "SAIN", f"PR-AUC proches (écart {mgap:.3f}) et pertes stables"
        return {"verdict": verdict, "reason": why, "epochs": n, "best_epoch": b + 1,
                "train_loss_at_best": round(float(train[b]), 5), "val_loss_at_best": round(float(val[b]), 5),
                "generalization_gap": round(gap, 4), "val_rise_after_best": round(rise, 4),
                "train_pr_auc_at_best": round(float(train_metric[b]), 4), "val_pr_auc_at_best": round(float(val_metric[b]), 4),
                "metric_gap": round(mgap, 4)}
    if gap > MAX_GAP:
        verdict, why = "SURAPPRENTISSAGE_NET", f"perte de validation {gap:.0%} au-dessus de celle d'entraînement"
    elif gap > LIGHT_GAP or (rise > RISE and train_falling):
        verdict = "SURAPPRENTISSAGE_LEGER"
        why = (f"écart de généralisation {gap:.0%}" if gap > LIGHT_GAP else
               f"la perte de validation remonte de {rise:.0%} alors que celle d'entraînement baisse")
    elif not stopped_early and n >= 3 and train[-1] < train[-2] * 0.98 and val[-1] <= val[max(b, 0)] * 1.001:
        verdict, why = "SOUS_APPRENTISSAGE", "la perte baisse encore à la dernière époque (arrêt par le nombre d'époques)"
    else:
        verdict, why = "SAIN", "pertes d'entraînement et de validation proches et stables"
    return {"verdict": verdict, "reason": why, "epochs": n, "best_epoch": b + 1,
            "train_loss_at_best": round(float(train[b]), 5), "val_loss_at_best": round(float(val[b]), 5),
            "generalization_gap": round(gap, 4), "val_rise_after_best": round(rise, 4)}


def xgb_curves(model) -> tuple[list[float], list[float]] | None:
    """Courbes logloss d'un XGBoost entraîné avec record_curves=True (None sinon)."""
    try:
        r = model.evals_result()
        return r["validation_0"]["logloss"], r["validation_1"]["logloss"]
    except (KeyError, AttributeError, ValueError):
        return None


def xgb_metric_curves(model) -> tuple[list[float], list[float]] | None:
    """Courbes PR-AUC (aucpr) entraînement / validation d'un XGBoost entraîné avec record_curves=True."""
    try:
        r = model.evals_result()
        return r["validation_0"]["aucpr"], r["validation_1"]["aucpr"]
    except (KeyError, AttributeError, ValueError):
        return None


def summarize_training(xgb_model=None, lstm_model=None, ae_model=None) -> dict:
    """Diagnostic des trois branches ; renvoie aussi le plus mauvais verdict (overfit_net bloque la promotion)."""
    out: dict = {}
    if xgb_model is not None and (c := xgb_curves(xgb_model)):
        best = getattr(xgb_model, "best_iteration", None)
        mc = xgb_metric_curves(xgb_model)
        out["xgboost"] = {**analyze_curve(c[0], c[1], (best + 1) if best is not None else None,
                                          stopped_early=best is not None and best + 1 < len(c[1]),
                                          train_metric=mc[0] if mc else None, val_metric=mc[1] if mc else None),
                          "unit": "logloss / itération"}
        out["xgboost"]["curve"] = {"train": [round(v, 5) for v in c[0][::10]], "val": [round(v, 5) for v in c[1][::10]], "step": 10}
    for name, m, unit in (("lstm_attention", lstm_model, "BCE / époque"), ("autoencoder", ae_model, "MSE / époque")):
        h = getattr(m, "history", None) if m is not None else None
        if h:
            val = [e["val_loss"] for e in h]
            best_epoch = int(np.argmin(val if name == "autoencoder" else [-e["val_pr_auc"] for e in h])) + 1
            has_m = all("train_pr_auc" in e and "val_pr_auc" in e for e in h)
            out[name] = {**analyze_curve([e["train_loss"] for e in h], val, best_epoch, stopped_early=best_epoch < len(h),
                                         train_metric=[e["train_pr_auc"] for e in h] if has_m else None,
                                         val_metric=[e["val_pr_auc"] for e in h] if has_m else None),
                         "unit": unit,
                         "curve": {"train": [round(e["train_loss"], 5) for e in h], "val": [round(e["val_loss"], 5) for e in h]}}
    verdicts = [v["verdict"] for v in out.values()]
    out["overfit_net"] = "SURAPPRENTISSAGE_NET" in verdicts
    out["worst"] = ("SURAPPRENTISSAGE_NET" if "SURAPPRENTISSAGE_NET" in verdicts else
                    "SURAPPRENTISSAGE_LEGER" if "SURAPPRENTISSAGE_LEGER" in verdicts else
                    "SOUS_APPRENTISSAGE" if "SOUS_APPRENTISSAGE" in verdicts else "SAIN" if verdicts else "INCONNU")
    return out
