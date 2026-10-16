"""
Équité du modèle : les erreurs touchent-elles certains groupes de clients plus que d'autres ?

Une fausse alerte n'a pas le même coût pour tout le monde : un client rural sur téléphone simple (USSD), loin d'un
agent, subit davantage un blocage qu'un client urbain sur smartphone. Pour chaque groupe (province, opérateur, canal,
canal d'accès, type de téléphone, niveau KYC, segment, tranche de revenu), sur la période de test :

    taux de fausses alertes   part des opérations LÉGITIMES interceptées (vérification ou blocage, politique de coût)
                              et alertées au seuil F1 ;
    rappel                    part des fraudes interceptées (une fraude manquée coûte aussi au client) ;
    précision                 part de fraudes parmi les opérations interceptées.

Chaque taux est donné avec son intervalle de confiance de Wilson à 95 %. Un groupe est SIGNALÉ quand son taux de fausses
alertes dépasse 1,25 fois le taux global (règle des « quatre cinquièmes » inversée) ET que la borne basse de son
intervalle dépasse le taux global (écart non dû au hasard), ou quand la borne haute de son rappel est sous le rappel
global. Les groupes trop petits (< 200 opérations légitimes) sont affichés sans être jugés.

Usage : python -m ml.robustness.evaluate_fairness   Sortie : ml/reports/fairness_evaluation.json / .md (copie dans ml/artifacts)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from shared.policy.costs import CostPolicy

RAW = Path("ml/data/raw")
REPORTS = Path("ml/reports")
ARTIFACTS = Path("ml/artifacts")
RATIO = 1.25
MIN_LEGIT = 200
DIMENSIONS = {
    "province": "Province", "operator": "Opérateur", "channel": "Canal", "access_channel": "Canal d'accès",
    "device_type": "Type de téléphone", "kyc_level": "Niveau KYC", "segment": "Segment de clientèle",
    "income_band": "Tranche de revenu",
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    if n == 0:
        return None, None, None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def load() -> pd.DataFrame:
    pred = pd.read_csv(REPORTS / "test_predictions.csv",
                       usecols=["transaction_id", "channel", "amount_usd", "is_fraud", "score_hybrid", "pred_hybrid"])
    raw = pd.read_csv(RAW / "transactions.csv", usecols=["transaction_id", "user_id", "operator", "access_channel",
                                                         "device_type", "location_province"], low_memory=False)
    users = pd.read_csv(RAW / "users.csv", usecols=["user_id", "province", "segment", "kyc_level", "monthly_income_usd"])
    t = pred.merge(raw, on="transaction_id").merge(users, on="user_id", suffixes=("", "_client"))
    # province du CLIENT (résidence), plus stable que le lieu de l'opération pour juger d'un traitement inégal
    t["operator"] = t["operator"].fillna("VISA")
    t["kyc_level"] = "KYC " + t["kyc_level"].astype(str)
    q = t["monthly_income_usd"].quantile([0.25, 0.5, 0.75]).to_numpy()
    t["income_band"] = pd.cut(t["monthly_income_usd"], [-np.inf, *q, np.inf],
                              labels=["Q1 (plus modestes)", "Q2", "Q3", "Q4 (plus aisés)"]).astype(str)
    pol = CostPolicy()
    t["intercept"] = [pol.cost_action(p, m, ch, op if op != "VISA" else None)[0] != "APPROVE"
                      for p, m, ch, op in zip(t["score_hybrid"], t["amount_usd"], t["channel"], t["operator"])]
    t["alert"] = t["pred_hybrid"].astype(bool)
    return t


def group_stats(g: pd.DataFrame, flag: str) -> dict:
    legit, fraud = g[g["is_fraud"] == 0], g[g["is_fraud"] == 1]
    fpr = wilson(int(legit[flag].sum()), len(legit))
    rec = wilson(int(fraud[flag].sum()), len(fraud))
    prec = wilson(int(g.loc[g[flag], "is_fraud"].sum()), int(g[flag].sum()))
    return {"n": int(len(g)), "n_legit": int(len(legit)), "n_fraud": int(len(fraud)),
            "false_alert_rate": fpr[0], "false_alert_ci": [fpr[1], fpr[2]],
            "recall": rec[0], "recall_ci": [rec[1], rec[2]], "precision": prec[0]}


def evaluate(t: pd.DataFrame, flag: str) -> dict:
    overall = group_stats(t, flag)
    out = {"overall": overall, "dimensions": {}}
    for dim, label in DIMENSIONS.items():
        col = "province" if dim == "province" else dim
        groups = []
        for key, g in t.groupby(col):
            s = {"group": str(key), **group_stats(g, flag)}
            judged = s["n_legit"] >= MIN_LEGIT
            ratio = s["false_alert_rate"] / overall["false_alert_rate"] if overall["false_alert_rate"] and s["false_alert_rate"] is not None else None
            s["false_alert_ratio"] = ratio
            s["judged"] = judged
            s["flag_false_alerts"] = bool(judged and ratio is not None and ratio >= RATIO
                                          and s["false_alert_ci"][0] > overall["false_alert_rate"])
            s["flag_recall"] = bool(s["n_fraud"] >= 30 and s["recall_ci"][1] is not None and s["recall_ci"][1] < overall["recall"])
            groups.append(s)
        groups.sort(key=lambda s: -(s["false_alert_rate"] or 0))
        rates = [s["false_alert_rate"] for s in groups if s["judged"] and s["false_alert_rate"]]
        out["dimensions"][dim] = {"label": label, "groups": groups,
                                  "max_min_ratio": (max(rates) / min(rates)) if len(rates) >= 2 else None,
                                  "n_flagged": sum(s["flag_false_alerts"] or s["flag_recall"] for s in groups)}
    return out


def main() -> None:
    t = load()
    R = {"n": int(len(t)), "ratio_rule": RATIO, "min_legit": MIN_LEGIT,
         "decision": {"intercept": evaluate(t, "intercept"), "alert": evaluate(t, "alert")}}
    REPORTS.mkdir(parents=True, exist_ok=True)
    js = json.dumps(R, indent=2, ensure_ascii=False, default=float)
    (REPORTS / "fairness_evaluation.json").write_text(js, encoding="utf-8")
    (ARTIFACTS / "fairness_evaluation.json").write_text(js, encoding="utf-8")
    (REPORTS / "fairness_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    print(to_markdown(R))


def _p(x):
    return "—" if x is None else f"{100 * x:.2f} %"


def to_markdown(R: dict) -> str:
    e = R["decision"]["intercept"]
    o = e["overall"]
    L = ["# Équité du modèle", "",
         f"Période de test : {R['n']:,} opérations. Décision : interception par la politique de coût. Taux global de fausses "
         f"alertes {_p(o['false_alert_rate'])}, rappel global {_p(o['recall'])}. Groupe signalé : fausses alertes ≥ "
         f"{R['ratio_rule']} × le taux global avec un écart significatif, ou rappel significativement plus bas.", ""]
    for dim, d in e["dimensions"].items():
        L += [f"## {d['label']}" + (f" — écart max/min {d['max_min_ratio']:.2f}" if d["max_min_ratio"] else ""), "",
              "| Groupe | Opérations | Fausses alertes (IC 95 %) | × global | Rappel | Signalé |", "|---|---|---|---|---|---|"]
        for s in d["groups"]:
            ci, ratio = s["false_alert_ci"], s["false_alert_ratio"]
            flag = "⚠ fausses alertes" if s["flag_false_alerts"] else ("⚠ rappel" if s["flag_recall"] else ("" if s["judged"] else "trop petit"))
            L.append(f"| {s['group']} | {s['n']:,} | {_p(s['false_alert_rate'])} ({_p(ci[0])} – {_p(ci[1])}) | "
                     f"{'—' if ratio is None else f'{ratio:.2f}'} | {_p(s['recall'])} | {flag} |")
        L.append("")
    L += ["_Données simulées : le générateur ne modélise pas de biais social ; un écart observé ici vient du comportement "
          "simulé (montants, canaux), et la même mesure doit être refaite sur les données réelles de chaque opérateur._", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
