"""
Évaluation hors ligne de la politique de décision : un seuil unique contre la décision coût-sensible.

Données : prédictions du modèle hybride sur la période de test (ml/reports/test_predictions.csv), montants, canaux et
opérateurs des transactions. Toutes les politiques sont jugées avec le MÊME modèle de coût métier (coûts par défaut,
shared/policy/costs.py) : fraude laissée passer = montant, vérification = friction (+ fraude non stoppée par la
vérification), client honnête bloqué = coût fixe + part du montant.

Politiques comparées :
    seuil_F1_blocage        bloquer si p ≥ seuil F1, approuver sinon (la pratique la plus simple) ;
    seuil_F1_verification   vérifier si p ≥ seuil F1, approuver sinon ;
    cout_defaut             décision coût-sensible, paramètres par défaut ;
    cout_regle              paramètres réglés (grille sur le plancher de blocage, le coût de faux blocage, la
                            friction) sur la PREMIÈRE moitié chronologique du test, mesurés sur la SECONDE.

Les règles réglementaires (qui n'imposent que des vérifications) ne sont pas rejouées : elles s'ajoutent à toutes les
politiques de la même façon. Usage : python -m ml.serving.evaluate_policy   Sortie : ml/reports/policy_evaluation.*
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pandas as pd

from shared.policy.costs import CostPolicy
from shared.policy.simulate import realized_costs, simulate

REPORTS = Path("ml/reports")
ARTIFACTS = Path("ml/artifacts")
RAW = Path("ml/data/raw")
GRID = {"block_floor": [0.9, 0.95, 0.97, 0.99], "false_block_x": [0.5, 1.0, 2.0, 4.0], "friction_x": [0.5, 1.0, 2.0]}


def load() -> tuple[list[dict], float]:
    pred = pd.read_csv(REPORTS / "test_predictions.csv", usecols=["transaction_id", "timestamp", "channel", "amount_usd",
                                                                  "is_fraud", "score_hybrid"])
    ops = pd.read_csv(RAW / "transactions.csv", usecols=["transaction_id", "operator"])
    t = pred.merge(ops, on="transaction_id", how="left").sort_values("timestamp", kind="stable")
    rows = [{"p": float(r.score_hybrid), "amount_usd": float(r.amount_usd), "channel": r.channel,
             "operator": r.operator if isinstance(r.operator, str) else None, "label": int(r.is_fraud)}
            for r in t.itertuples()]
    thr = float(json.loads((ARTIFACTS / "metadata.json").read_text(encoding="utf-8"))["threshold"])
    return rows, thr


def threshold_actions(rows, thr, alert_action):
    return [alert_action if r["p"] >= thr else "APPROVE" for r in rows]


def scaled(base: CostPolicy, block_floor: float, false_block_x: float, friction_x: float) -> CostPolicy:
    d = base.to_dict()
    d["block_floor"] = block_floor
    for ch in d["costs"].values():
        ch["false_block_usd"] = min(500.0, ch["false_block_usd"] * false_block_x)
        ch["friction_usd"] = min(50.0, ch["friction_usd"] * friction_x)
    d["version"] = f"réglée (plancher {block_floor}, faux blocage x{false_block_x}, friction x{friction_x})"
    return CostPolicy.from_dict(d)


def summarize(rows, actions, truth: CostPolicy) -> dict:
    r = realized_costs(rows, actions, truth)
    legit = r["n"] - r["frauds"]
    return {**r, "blocks": sum(a == "BLOCK" for a in actions), "verifications": sum(a == "VERIFY" for a in actions),
            "legit_friction_rate": (r["legit_blocked"] + r["legit_verified"]) / legit if legit else 0.0,
            "fraud_stopped_rate": (r["fraud_blocked"] + r["fraud_verified"]) / r["frauds"] if r["frauds"] else 0.0}


def main() -> None:
    rows, thr = load()
    truth = CostPolicy()
    half = len(rows) // 2
    tune, test = rows[:half], rows[half:]

    best, best_cost = None, float("inf")
    for bf, fbx, frx in itertools.product(*GRID.values()):
        pol = scaled(truth, bf, fbx, frx)
        cost = realized_costs(tune, simulate(tune, pol)[1], truth)["total"]
        if cost < best_cost:
            best, best_cost = pol, cost

    out = {"threshold_f1": thr, "n_eval": len(test), "n_eval_frauds": sum(r["label"] for r in test),
           "tuned_on": len(tune), "tuned_params": best.to_dict(), "policies": {}}
    candidates = {
        "seuil_F1_blocage": threshold_actions(test, thr, "BLOCK"),
        "seuil_F1_verification": threshold_actions(test, thr, "VERIFY"),
        "cout_defaut": simulate(test, truth)[1],
        "cout_regle": simulate(test, best)[1],
    }
    for name, actions in candidates.items():
        out["policies"][name] = summarize(test, actions, truth)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "policy_evaluation.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (ARTIFACTS / "policy_evaluation.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "policy_evaluation.md").write_text(to_markdown(out), encoding="utf-8")
    print(to_markdown(out))


LABELS = {"seuil_F1_blocage": "Seuil F1 → blocage", "seuil_F1_verification": "Seuil F1 → vérification",
          "cout_defaut": "Coût, paramètres par défaut", "cout_regle": "Coût, paramètres réglés"}


def to_markdown(o: dict) -> str:
    L = ["# Politique de décision : seuil unique contre coût", "",
         f"Seconde moitié chronologique du test : {o['n_eval']:,} transactions, {o['n_eval_frauds']:,} fraudes ; "
         f"réglage sur la première moitié ({o['tuned_on']:,}). Toutes les politiques sont jugées avec les mêmes coûts "
         f"métier (coûts par défaut). Seuil F1 du modèle : {o['threshold_f1']:.3f}.", "",
         "| Politique | Perte totale (USD) | Fraude non stoppée | Friction | Faux blocages | Fraudes stoppées | Clients honnêtes gênés | Blocages | Vérifications |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k, v in o["policies"].items():
        L.append(f"| {LABELS[k]} | {v['total']:,.0f} | {v['fraud_loss']:,.0f} | {v['friction']:,.0f} | {v['false_block']:,.0f} | "
                 f"{100 * v['fraud_stopped_rate']:.1f} % | {100 * v['legit_friction_rate']:.2f} % | {v['blocks']:,} | {v['verifications']:,} |")
    L += ["", f"Paramètres réglés : {o['tuned_params']['version']}.", "",
          "_Coûts métier : hypothèses de simulation à remplacer par les coûts réels de chaque opérateur._", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
