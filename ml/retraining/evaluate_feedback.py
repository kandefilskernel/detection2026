"""
Évaluation hors ligne de la boucle de retour : quelles transactions faire revoir aux analystes, et quel poids
donner à leurs verdicts ?

Rejeu MENSUEL de la période de test (branche XGBoost seule, pour un coût raisonnable) :
    - au début de chaque mois, le modèle courant score les transactions du mois (métriques mesurées à ce moment,
      avant toute étiquette du mois) ;
    - fin de mois, étiquettes révélées comme en production :
        alertes (probabilité ≥ seuil F1 de la validation)  -> verdict des analystes (vrai label, vérifié) ;
        BUDGET transactions approuvées choisies par la STRATÉGIE -> verdict (vérifié) ;
        plaintes : une part COMPLAINT_RATE des fraudes manquées restantes est signalée par les clients (vérifié) ;
        tout le reste -> « 0 » supposé (étiquette mûre, bruitée : contient les fraudes jamais signalées) ;
    - réentraînement sur l'historique + toutes les étiquettes de production accumulées, verdicts pondérés.

Stratégies (même budget) : aucune revue supplémentaire, témoin aléatoire, incertitude (au plus près du seuil),
mélange incertitude + témoin. Le témoin sert aussi à ESTIMER le taux de fraudes manquées : on vérifie que son
intervalle de confiance couvre la vraie valeur, ce que la revue par incertitude, biaisée par construction, ne permet pas.

HYPOTHÈSES (à citer) : tous les verdicts sont exacts ; 30 % des fraudes manquées font l'objet d'une plainte ;
la nouveauté (autoencodeur) et le réseau ne sont pas simulés ici.

Usage : python -m ml.retraining.evaluate_feedback      Sortie : ml/reports/feedback_evaluation.json / .md
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml.models.xgboost_branch import train_xgboost_branch
from ml.training.evaluation import best_f1_threshold

PROCESSED = Path("ml/data/processed")
REPORTS = Path("ml/reports")
BUDGET = 200                 # revues supplémentaires par mois (~1,4 % des transactions approuvées)
COMPLAINT_RATE = 0.30
N_EST = 150
CONFIGS = [  # nom, part incertitude, part témoin, poids des verdicts
    ("alertes_seules", 0.0, 0.0, 1.0),
    ("temoin_aleatoire", 0.0, 1.0, 3.0),
    ("incertitude_poids1", 1.0, 0.0, 1.0),
    ("incertitude_poids3", 1.0, 0.0, 3.0),
    ("incertitude_plus_temoin_poids3", 0.5, 0.5, 3.0),
]


def load():
    X = np.load(PROCESSED / "X_all.npy")
    y = np.load(PROCESSED / "y_all.npy").astype(np.int8)
    split = np.load(PROCESSED / "split.npy")
    meta = pd.read_csv(PROCESSED / "meta.csv", usecols=["timestamp", "fraud_type"], parse_dates=["timestamp"])
    return X, y, split, meta


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fit(X, y, w, rows, es_rows, seed=42):
    m = train_xgboost_branch(X[rows], y[rows], X[es_rows], y[es_rows], N_EST, seed, sample_weight=w[rows])
    return m


def run_config(name, unc_share, ctl_share, weight, X, y, split, months, val_rows, base_rows, es_rows, initial, seed=42):
    rng = np.random.default_rng(seed)
    w = np.ones(len(y))
    y_used = y.copy()                      # étiquettes visibles par l'entraînement (0 supposé pour le non revu)
    labeled = list(base_rows)
    model, thr = initial                   # modèle initial identique pour toutes les stratégies
    per_month, found_by_review, ctl_checks = [], 0, []
    for i, rows in enumerate(months):
        p = model.predict_proba(X[rows])[:, 1]
        yt = y[rows]
        alert = p >= thr
        per_month.append({"month": i, "n": int(len(rows)), "frauds": int(yt.sum()),
                          "ap": float(average_precision_score(yt, p)) if yt.any() else None,
                          "recall": float(alert[yt == 1].mean()) if yt.any() else None,
                          "precision": float(yt[alert].mean()) if alert.any() else None,
                          "missed": int((~alert & (yt == 1)).sum())})
        # ---- étiquettes révélées en fin de mois
        approved = np.flatnonzero(~alert)
        n_unc, n_ctl = int(round(BUDGET * unc_share)), int(round(BUDGET * ctl_share))
        logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
        unc = approved[np.argsort(np.abs(logit[approved] - math.log(thr / (1 - thr))))[:n_unc]]
        rest = np.setdiff1d(approved, unc)
        ctl = rng.choice(rest, size=min(n_ctl, len(rest)), replace=False) if n_ctl else np.array([], int)
        if n_ctl:
            k = int(yt[ctl].sum())
            lo, hi = wilson(k, len(ctl))
            true_rate = float(yt[approved].mean())
            ctl_checks.append({"month": i, "estimate": k / len(ctl), "low": lo, "high": hi, "true": true_rate,
                               "covered": lo <= true_rate <= hi})
        reviewed = np.zeros(len(rows), bool)
        reviewed[alert] = True
        reviewed[unc] = True
        reviewed[ctl] = True
        found_by_review += int(yt[np.concatenate([unc, ctl]).astype(int)].sum())
        missed = np.flatnonzero(~reviewed & (yt == 1))
        complained = (rng.choice(missed, size=int(round(COMPLAINT_RATE * len(missed))), replace=False)
                      if len(missed) else np.array([], int))
        verified = reviewed.copy()
        verified[complained] = True
        g = np.asarray(rows)
        y_used[g] = np.where(verified, yt, 0)
        w[g] = np.where(verified, weight, 1.0)
        labeled.extend(g.tolist())
        if i < len(months) - 1:
            model = fit(X, y_used, w, np.array(labeled), es_rows, seed)
            thr = best_f1_threshold(y[val_rows], model.predict_proba(X[val_rows])[:, 1])
    ev = [m for m in per_month[1:] if m["ap"] is not None]           # mois 0 : modèle initial, identique partout
    res = {"name": name, "uncertainty_share": unc_share, "control_share": ctl_share, "verified_weight": weight,
           "mean_ap": float(np.mean([m["ap"] for m in ev])),
           "recall": float(sum(m["frauds"] - m["missed"] for m in ev) / max(sum(m["frauds"] for m in ev), 1)),
           "missed": int(sum(m["missed"] for m in ev)),
           "frauds_found_by_extra_reviews": found_by_review, "per_month": per_month}
    if ctl_checks:
        res["control_estimate"] = {"coverage": float(np.mean([c["covered"] for c in ctl_checks])), "months": ctl_checks}
    return res


def main() -> None:
    t0 = time.time()
    X, y, split, meta = load()
    base_rows = np.flatnonzero(split == 0)
    es_rows = np.flatnonzero(split == 1)
    val_rows = np.flatnonzero(split == 2)
    test = np.flatnonzero(split == 3)
    month = meta["timestamp"].iloc[test].dt.to_period("M").to_numpy()
    months = [test[month == m] for m in pd.unique(month)]
    months = [m for m in months if len(m) > 1000]
    R = {"budget_per_month": BUDGET, "complaint_rate": COMPLAINT_RATE, "n_months": len(months),
         "n_test": int(len(test)), "n_test_fraud": int(y[test].sum()), "configs": []}
    m0 = fit(X, y, np.ones(len(y)), base_rows, es_rows)
    initial = (m0, best_f1_threshold(y[val_rows], m0.predict_proba(X[val_rows])[:, 1]))
    for cfg in CONFIGS:
        r = run_config(*cfg, X, y, split, months, val_rows, base_rows, es_rows, initial)
        print(f"{r['name']}: AP={r['mean_ap']:.4f} rappel={r['recall']:.4f} manquées={r['missed']} "
              f"trouvées={r['frauds_found_by_extra_reviews']}", flush=True)
        R["configs"].append(r)
    R["duration_s"] = round(time.time() - t0, 1)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "feedback_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    (REPORTS / "feedback_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    print(to_markdown(R))


def to_markdown(R: dict) -> str:
    L = ["# Évaluation de la boucle de retour des analystes", "",
         f"Rejeu mensuel de la période de test ({R['n_months']} mois, {R['n_test']:,} transactions, {R['n_test_fraud']:,} "
         f"fraudes), branche XGBoost. Budget : {R['budget_per_month']} revues supplémentaires par mois ; "
         f"{R['complaint_rate']:.0%} des fraudes manquées signalées par plainte. Métriques mesurées avant les étiquettes "
         "du mois, à partir du 2ᵉ mois.", "",
         "| Stratégie | Poids des verdicts | AP moyenne | Rappel | Fraudes manquées | Fraudes trouvées par les revues |",
         "|---|---|---|---|---|---|"]
    for r in R["configs"]:
        L.append(f"| {r['name']} | {r['verified_weight']:g} | {r['mean_ap']:.4f} | {100 * r['recall']:.2f} % | "
                 f"{r['missed']} | {r['frauds_found_by_extra_reviews']} |")
    L += ["", "## Estimation du taux de fraudes manquées par l'échantillon témoin", ""]
    for r in R["configs"]:
        if "control_estimate" in r:
            c = r["control_estimate"]
            L.append(f"- **{r['name']}** : l'intervalle de confiance à 95 % couvre le vrai taux {100 * c['coverage']:.0f} % "
                     f"des mois ({len(c['months'])} mois).")
    L += ["", "_Hypothèses : verdicts exacts, taux de plainte fixe ; la nouveauté et le réseau ne sont pas simulés._", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
