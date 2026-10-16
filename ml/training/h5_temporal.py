"""
H5 — Les comportements frauduleux évoluent ; un modèle de profilage mis à jour régulièrement conserve ses
performances, alors qu'un modèle figé se dégrade face aux fraudes émergentes.

Protocole (jeu pluriannuel 2019-2025, XGBoost sur les 58 variables de profilage, un seul facteur change) :
    FIGÉ        entraîné une fois sur 2019-2021, jamais mis à jour, évalué sur chaque année 2022 … 2025
    CUMULATIF   réentraîné chaque année sur TOUT l'historique disponible (jusqu'au 31/12 de l'année précédente)
    GLISSANT    réentraîné chaque année sur les 3 DERNIÈRES années seulement : même quantité de données que le
                modèle figé ; s'il fait aussi bien que le cumulatif, c'est la RÉCENCE des données qui compte,
                pas leur volume (contrôle du facteur de confusion « plus de données »)
Dans chaque entraînement, les 3 derniers mois servent à l'arrêt précoce et au choix du seuil (jamais l'année évaluée).

Mesures par année évaluée : PR-AUC [IC95], rappel à 1 % de faux positifs, rappel et faux positifs au seuil,
rappel par typologie ; différences appariées (bootstrap par usager) entre stratégies sur les MÊMES transactions.

Usage : python -m ml.training.h5_temporal         Sorties : ml/reports/h5_evaluation.json / .md
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features.feature_engineering import FEATURE_NAMES, PROCESSED_DIR
from ml.models.xgboost_branch import train_xgboost_branch, xgb_logit
from ml.training.evaluation import best_f1_threshold, evaluate, recall_by_fraud_type
from ml.training.significance import paired_bootstrap

REPORTS = Path("ml/reports")
TEST_YEARS = [2022, 2023, 2024, 2025]
FIRST_TRAIN, LAST_FROZEN = 2019, 2021
WINDOW_YEARS = 3
N_EST, N_BOOT = 600, 300


def train(table: pd.DataFrame, X: np.ndarray, y: np.ndarray, years: np.ndarray, until_year: int, from_year: int):
    """Entraîne sur [from_year, until_year] ; les 3 derniers mois = arrêt précoce et choix du seuil."""
    ts = table["timestamp"]
    in_range = (years >= from_year) & (years <= until_year)
    es_start = pd.Timestamp(f"{until_year}-10-01")
    fit, es = in_range & (ts < es_start).to_numpy(), in_range & (ts >= es_start).to_numpy()
    m = train_xgboost_branch(X[fit], y[fit], X[es], y[es], N_EST, 42)
    s_es = xgb_logit(m, X[es])
    return m, best_f1_threshold(y[es], s_es), int(fit.sum()), int(es.sum())


def main() -> None:
    t0 = time.perf_counter()
    table = pd.read_csv(PROCESSED_DIR / "features.csv", parse_dates=["timestamp"], low_memory=False)
    if table["timestamp"].dt.year.min() > FIRST_TRAIN or table["timestamp"].dt.year.max() < TEST_YEARS[-1]:
        raise SystemExit("H5 demande le jeu pluriannuel 2019-2025 (python ml/generator/generate_synthetic_data.py --multi-year)")
    X = table[FEATURE_NAMES].to_numpy(np.float32)
    y = table["is_fraud"].to_numpy()
    years = table["timestamp"].dt.year.to_numpy()
    users = table["user_id"].to_numpy()
    ftype = table["fraud_type"].to_numpy()

    print("[H5] modèle figé 2019-2021", flush=True)
    frozen, thr_f, n_fit, n_es = train(table, X, y, years, LAST_FROZEN, FIRST_TRAIN)
    R: dict = {"protocole": {"figé": f"{FIRST_TRAIN}-{LAST_FROZEN}", "cumulatif": "tout l'historique jusqu'à l'année précédente",
                             "glissant": f"{WINDOW_YEARS} dernières années", "n_estimators": N_EST, "n_boot": N_BOOT},
         "entraînement_figé": {"lignes": n_fit, "arrêt_précoce": n_es}, "années": {}}
    pooled = {"figé": [], "cumulatif": [], "glissant": [], "rows": []}

    for Y in TEST_YEARS:
        print(f"[H5] année {Y}", flush=True)
        cum, thr_c, nc, _ = train(table, X, y, years, Y - 1, FIRST_TRAIN)
        win, thr_w, nw, _ = train(table, X, y, years, Y - 1, Y - WINDOW_YEARS)
        rows = np.flatnonzero(years == Y)
        scores = {"figé": xgb_logit(frozen, X[rows]), "cumulatif": xgb_logit(cum, X[rows]), "glissant": xgb_logit(win, X[rows])}
        thr = {"figé": thr_f, "cumulatif": thr_c, "glissant": thr_w}
        boot = paired_bootstrap(y[rows], scores, users[rows], reference="figé", n_boot=N_BOOT, seed=Y)
        year = {"n": int(len(rows)), "n_fraud": int(y[rows].sum()), "lignes_entraînement": {"cumulatif": nc, "glissant": nw},
                "fraudes_par_typologie": pd.Series(ftype[rows][y[rows] == 1]).value_counts().to_dict()}
        for k in scores:
            year[k] = {**boot[k], "operational": evaluate(y[rows], scores[k], thr[k]),
                       "rappel_par_typologie": recall_by_fraud_type(y[rows], scores[k], thr[k], ftype[rows])}
        R["années"][str(Y)] = year
        for k in scores:
            pooled[k].append(scores[k])
        pooled["rows"].append(rows)

    print("[H5] ensemble 2022-2025", flush=True)
    rows = np.concatenate(pooled["rows"])
    # scores de chaque année concaténés : chaque stratégie est jugée sur toutes les années évaluées
    sc = {k: np.concatenate(pooled[k]) for k in ("figé", "cumulatif", "glissant")}
    R["ensemble_2022_2025"] = paired_bootstrap(y[rows], sc, users[rows], reference="figé", n_boot=N_BOOT, seed=1)

    # tendance du modèle figé : écart avec le cumulatif qui se creuse d'année en année ?
    gaps = [R["années"][str(Y)]["cumulatif"]["pr_auc"]["diff_vs_reference"] for Y in TEST_YEARS]
    R["tendance"] = {"écart_cumulatif_moins_figé_par_année": dict(zip(map(str, TEST_YEARS), gaps)),
                     "pente_par_an": round(float(np.polyfit(TEST_YEARS, gaps, 1)[0]), 5)}
    last = R["années"][str(TEST_YEARS[-1])]["cumulatif"]["pr_auc"]
    overall = R["ensemble_2022_2025"]["cumulatif"]["pr_auc"]
    win_overall = R["ensemble_2022_2025"]["glissant"]["pr_auc"]
    confirmed = overall["significant_95"] and overall["diff_vs_reference"] > 0 and last["diff_vs_reference"] > 0
    R["verdict"] = ("CONFIRMÉE" if confirmed and R["tendance"]["pente_par_an"] > 0 else
                    "PARTIELLEMENT CONFIRMÉE" if confirmed else "NON CONFIRMÉE")
    R["récence_vs_volume"] = ("la fenêtre glissante fait aussi bien que le cumulatif : la récence compte plus que le volume"
                              if win_overall["significant_95"] and win_overall["diff_vs_reference"] > 0 else
                              "la fenêtre glissante n'améliore pas significativement le modèle figé : le gain vient surtout du volume")
    R["durée_s"] = round(time.perf_counter() - t0)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "h5_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    md = to_markdown(R)
    (REPORTS / "h5_evaluation.md").write_text(md, encoding="utf-8")
    print(md)


def ci(m: dict) -> str:
    d = m["pr_auc"]
    return f"{d['point']:.4f} [{d['ci95'][0]:.4f} ; {d['ci95'][1]:.4f}]"


def diff(m: dict) -> str:
    d = m["pr_auc"]
    if "diff_vs_reference" not in d:
        return "réf."
    return (f"{d['diff_vs_reference']:+.4f} [{d['diff_ci95'][0]:+.4f} ; {d['diff_ci95'][1]:+.4f}] "
            f"({'significatif' if d['significant_95'] else 'non significatif'})")


def to_markdown(R: dict) -> str:
    L = ["# H5 — Évolution des fraudes et mise à jour du modèle", "",
         "Modèle figé entraîné sur 2019-2021, comparé chaque année à un modèle réentraîné sur tout l'historique "
         "(cumulatif) et sur les 3 dernières années (glissant). XGBoost, 58 variables de profilage, IC95 par bootstrap "
         "apparié par usager. **Données simulées : les tendances des fraudes sont des hypothèses du générateur.**", "",
         "| Année | Fraudes | Figé : PR-AUC | Cumulatif : PR-AUC | Δ cumulatif − figé | Glissant : PR-AUC | Δ glissant − figé |",
         "|---|---|---|---|---|---|---|"]
    for Y, d in R["années"].items():
        L.append(f"| {Y} | {d['n_fraud']} | {ci(d['figé'])} | {ci(d['cumulatif'])} | {diff(d['cumulatif'])} | "
                 f"{ci(d['glissant'])} | {diff(d['glissant'])} |")
    e = R["ensemble_2022_2025"]
    L += ["", f"**Ensemble 2022-2025** : figé {ci(e['figé'])}, cumulatif {ci(e['cumulatif'])} ({diff(e['cumulatif'])}), "
              f"glissant {ci(e['glissant'])} ({diff(e['glissant'])}).", "",
          "Rappel au seuil et faux positifs (seuil choisi sur les 3 derniers mois de chaque entraînement) :", "",
          "| Année | Figé : rappel / faux positifs | Cumulatif | Glissant |", "|---|---|---|---|"]
    for Y, d in R["années"].items():
        cell = lambda k: f"{d[k]['operational']['recall']:.3f} / {d[k]['operational']['false_positive_rate']:.4%}"  # noqa: E731
        L.append(f"| {Y} | {cell('figé')} | {cell('cumulatif')} | {cell('glissant')} |")
    types = sorted({t for d in R["années"].values() for t in d["figé"]["rappel_par_typologie"]})
    L += ["", "Rappel par typologie (figé → cumulatif), dernière année évaluée :", "",
          "| Typologie | n | Figé | Cumulatif | Glissant |", "|---|---|---|---|---|"]
    last = R["années"][max(R["années"])]
    for t in types:
        f, c, g = (last[k]["rappel_par_typologie"].get(t, {}) for k in ("figé", "cumulatif", "glissant"))
        L.append(f"| {t} | {f.get('n', '-')} | {f.get('recall', '-')} | {c.get('recall', '-')} | {g.get('recall', '-')} |")
    t = R["tendance"]
    L += ["", f"Écart cumulatif − figé par année : {t['écart_cumulatif_moins_figé_par_année']} "
              f"(pente {t['pente_par_an']:+.4f} par an : {'il se creuse' if t['pente_par_an'] > 0 else 'il ne se creuse pas'}).",
          f"Récence ou volume : {R['récence_vs_volume']}.", "",
          f"**Conclusion H5 : {R['verdict']}**. Confirmée si le modèle mis à jour est significativement meilleur sur "
          "2022-2025 ET encore meilleur la dernière année, avec un écart qui se creuse ; partiellement si l'écart est "
          "significatif sans se creuser.", "",
          "Limites : données simulées ; un seul modèle (XGBoost) et une seule graine ; les tendances des typologies "
          "(FRAUD_TRENDS) sont fixées par hypothèse dans le générateur.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
