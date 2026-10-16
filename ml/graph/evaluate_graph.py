"""
Évaluation de l'analyse de réseau (shared/graph) sur les données simulées.

Rejeu CHRONOLOGIQUE, sans fuite temporelle :
    - avant la période de validation, toutes les transactions sont ajoutées avec leur étiquette (historique connu) ;
    - ensuite, chaque transaction reçoit un score réseau calculé sur l'instantané du graphe de LA VEILLE
      (scores recalculés une fois par jour), puis elle est ajoutée au graphe ; son étiquette n'est révélée
      qu'après LABEL_DELAY_DAYS jours (délai d'instruction d'un dossier par un analyste).
      Variante « production » : en attendant le verdict, la transaction compte avec la probabilité du modèle.
    - le seuil du score réseau est choisi sur la VALIDATION (taux de fausses alertes visé), jamais sur le test.

Mesures :
    A. Transaction : le score réseau seul (AP, ROC-AUC), et la règle hybride « alerte du modèle OU réseau ≥ seuil »
       comparée au modèle seul (rappel, taux de fausses alertes, fraudes rattrapées par typologie).
    B. Entité : les entités partagées (≥ 2 comptes) sont classées par score ; précision@k contre la vérité du
       générateur (portefeuilles mules, appareils de fraudeurs, agents compromis), comparée à la variable de
       premier niveau déjà dans le modèle (nombre de comptes distincts) et au risque direct seul.
       Variante sans aucune étiquette : graphe de la période de test pondéré par les seules probabilités du modèle.
    C. Réseaux : nombre, pureté (part des entités qui sont réellement frauduleuses), couverture.

ATTENTION : le générateur réutilise un nombre fini de portefeuilles mules et d'appareils de fraudeurs ; l'ampleur
du gain dépend de cette hypothèse de simulation. Le résultat montre le mécanisme, pas une performance réelle.

Usage : python -m ml.graph.evaluate_graph       Sortie : ml/reports/graph_evaluation.json / .md
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from shared.graph.network import TransactionGraph, node_id

RAW_DIR = Path("ml/data/raw")
PROCESSED_DIR = Path("ml/data/processed")
REPORTS = Path("ml/reports")
ARTIFACTS = Path("ml/artifacts")      # copie lue par le back-office (GET /network/evaluation)
LABEL_DELAY_DAYS = 7
TARGET_FPR = 0.005                    # fausses alertes supplémentaires tolérées pour la règle réseau
POOL_DEVICE_TYPES = {"SIM_SWAP", "ACCOUNT_TAKEOVER", "CARD_TESTING", "CNP_FRAUD", "TOPUP_DRAIN"}
MULE_WALLET_PREFIX = "2437"           # préfixe des portefeuilles mules du générateur
KS = (25, 50, 100, 200)
COLS = ["transaction_id", "timestamp", "user_id", "tx_type", "amount_usd", "counterparty_id",
        "device_id", "agent_id", "merchant_id", "is_fraud", "fraud_type"]


def load() -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    tx = pd.read_csv(RAW_DIR / "transactions.csv", usecols=COLS, parse_dates=["timestamp"],
                     dtype={"counterparty_id": str, "agent_id": str, "merchant_id": str, "device_id": str})
    meta = pd.read_csv(PROCESSED_DIR / "meta.csv", usecols=["transaction_id"])
    meta["split"] = np.load(PROCESSED_DIR / "split.npy")
    pred = pd.read_csv(REPORTS / "test_predictions.csv", usecols=["transaction_id", "score_hybrid", "pred_hybrid"])
    tx = tx.merge(meta, on="transaction_id", how="left").merge(pred, on="transaction_id", how="left")
    tx = tx.sort_values("timestamp", kind="stable").reset_index(drop=True)
    val_start = tx.loc[tx["split"] == 1, "timestamp"].min()
    test_start = tx.loc[tx["pred_hybrid"].notna(), "timestamp"].min()
    return tx, val_start, test_start


def ground_truth(tx: pd.DataFrame) -> dict[str, set[str]]:
    agents = pd.read_csv(RAW_DIR / "agents.csv", dtype={"agent_id": str})
    users = pd.read_csv(RAW_DIR / "users.csv", usecols=["user_id", "is_mule_account"])
    fraud_dev = tx.loc[(tx["is_fraud"] == 1) & tx["fraud_type"].isin(POOL_DEVICE_TYPES), "device_id"].dropna()
    wallets = tx["counterparty_id"].dropna().astype(str)
    return {
        "W": {node_id("W", w) for w in wallets.unique() if w.startswith(MULE_WALLET_PREFIX) and len(w) == 12},
        "D": {node_id("D", d) for d in fraud_dev.unique()},
        "A": {node_id("A", a) for a in agents.loc[agents["is_compromised"] == 1, "agent_id"]},
        "U": {node_id("U", u) for u in users.loc[users["is_mule_account"].astype(bool), "user_id"]},
    }


def replay(tx: pd.DataFrame, val_start, use_model_scores: bool) -> tuple[np.ndarray, TransactionGraph]:
    """Score réseau de chaque transaction à partir de la validation (NaN avant)."""
    g = TransactionGraph()
    records = tx.to_dict("records")
    net = np.full(len(records), np.nan)
    pending: deque = deque()                       # (date de révélation, transaction, suspicion provisoire)
    delay = pd.Timedelta(days=LABEL_DELAY_DAYS)
    day, scores = None, None
    for i, r in enumerate(records):
        ts = r["timestamp"]
        if ts < val_start:
            g.add(r, float(r["is_fraud"]))
            continue
        while pending and pending[0][0] <= ts:     # verdicts des analystes arrivés entre-temps
            _, old_r, old_s = pending.popleft()
            g.relabel(old_r, old_s, float(old_r["is_fraud"]))
        if ts.normalize() != day:                  # instantané quotidien
            day, scores = ts.normalize(), g.compute_scores()
        net[i] = g.tx_network_score(r, scores)["score"]
        provisional = float(r["score_hybrid"]) if use_model_scores and not pd.isna(r["score_hybrid"]) else None
        g.add(r, provisional)
        pending.append((ts + delay, r, provisional))
    while pending:
        _, old_r, old_s = pending.popleft()
        g.relabel(old_r, old_s, float(old_r["is_fraud"]))
    return net, g


def threshold_at_fpr(y: np.ndarray, s: np.ndarray, fpr: float) -> float:
    legit = np.sort(s[y == 0])
    return float(legit[min(len(legit) - 1, int(np.ceil((1 - fpr) * len(legit))))]) + 1e-12


def tx_metrics(tx: pd.DataFrame, net: np.ndarray, val_mask: np.ndarray, test_mask: np.ndarray) -> dict:
    yv, sv = tx.loc[val_mask, "is_fraud"].to_numpy(), net[val_mask]
    tau = threshold_at_fpr(yv, sv, TARGET_FPR)
    t = tx.loc[test_mask].copy()
    t["net"] = net[test_mask]
    y = t["is_fraud"].to_numpy()
    model = t["pred_hybrid"].to_numpy().astype(bool)
    rule = t["net"].to_numpy() >= tau
    both = model | rule

    def rates(alert):
        return {"recall": float(alert[y == 1].mean()), "false_alert_rate": float(alert[y == 0].mean()),
                "precision": float(y[alert].mean()) if alert.any() else 0.0, "n_alerts": int(alert.sum())}

    by_type = {}
    for ft, grp in t[t["is_fraud"] == 1].groupby("fraud_type"):
        m, r = grp["pred_hybrid"].to_numpy().astype(bool), grp["net"].to_numpy() >= tau
        by_type[ft] = {"n": int(len(grp)), "model": float(m.mean()), "hybrid_or_network": float((m | r).mean()),
                       "rescued": int((r & ~m).sum())}
    return {
        "threshold_from_validation": tau, "target_fpr": TARGET_FPR,
        "network_alone": {"average_precision": float(average_precision_score(y, t["net"])),
                          "roc_auc": float(roc_auc_score(y, t["net"])), **rates(rule)},
        "model_alone": {"average_precision": float(average_precision_score(y, t["score_hybrid"])), **rates(model)},
        "model_or_network": rates(both),
        "frauds_rescued": int((rule & ~model & (y == 1)).sum()),
        "extra_false_alerts": int((rule & ~model & (y == 0)).sum()),
        "by_fraud_type": by_type,
    }


def precision_at_k(ranked: list[str], truth: set[str]) -> dict:
    return {f"p@{k}": float(np.mean([e in truth for e in ranked[:k]])) for k in KS if len(ranked) >= k}


def entity_metrics(g: TransactionGraph, truth: dict[str, set[str]]) -> dict:
    sc = g.compute_scores()
    shared = [e for e, us in g.by_entity.items() if len(us) >= 2]
    all_truth = truth["W"] | truth["D"] | truth["A"]
    rankings = {
        "nb_comptes_distincts (variable déjà dans le modèle)": sorted(shared, key=lambda e: -len(g.by_entity[e])),
        "risque_direct": sorted(shared, key=lambda e: -sc.direct[e]),
        "score_reseau (direct + propagé)": sorted(shared, key=lambda e: -sc.entity[e]),
    }
    acc = sorted(g.by_account, key=lambda u: -sc.account[u])
    return {
        "n_shared_entities": len(shared), "n_true_shared": int(sum(e in all_truth for e in shared)),
        "entities": {k: precision_at_k(v, all_truth) for k, v in rankings.items()},
        "mule_accounts_in_top10_exposure": int(sum(u in truth["U"] for u in acc[:10])),
        "_scores": sc,
    }


def ring_metrics(g: TransactionGraph, sc, truth: dict[str, set[str]]) -> dict:
    rings = g.rings(sc, include_members=True)
    all_truth = truth["W"] | truth["D"] | truth["A"]
    in_rings = {e for r in rings for e in r["entities"]}
    shared_truth = {e for e in all_truth if len(g.by_entity.get(e, ())) >= 2}
    return {
        "n_rings": len(rings),
        "largest_ring_accounts": max((r["n_accounts"] for r in rings), default=0),
        "n_entities_in_rings": len(in_rings),
        "purity_entities": float(np.mean([e in all_truth for e in in_rings])) if in_rings else 0.0,
        "coverage_true_shared_entities": float(len(in_rings & shared_truth) / len(shared_truth)) if shared_truth else 0.0,
        "top5": [{k: r[k] for k in ("id", "score", "n_accounts", "n_entities", "entity_kinds", "expected_frauds")}
                 for r in rings[:5]],
    }


def recent_window_rings(tx: pd.DataFrame, test_mask: np.ndarray, truth: dict[str, set[str]], days: int = 30) -> dict:
    """Comme l'écran « Réseaux » : 30 derniers jours, suspicion = probabilité du modèle (aucun verdict)."""
    t = tx.loc[test_mask]
    t = t[t["timestamp"] >= t["timestamp"].max() - pd.Timedelta(days=days)]
    g = TransactionGraph()
    for r in t.to_dict("records"):
        g.add(r, float(r["score_hybrid"]))
    return {"days": days, "n_tx": int(len(t)), **ring_metrics(g, g.compute_scores(), truth)}


def model_only_entities(tx: pd.DataFrame, test_mask: np.ndarray, truth: dict[str, set[str]]) -> dict:
    """Aucune étiquette : graphe de la période de test, suspicion = probabilité du modèle."""
    g = TransactionGraph()
    for r in tx.loc[test_mask].to_dict("records"):
        g.add(r, float(r["score_hybrid"]))
    res = entity_metrics(g, truth)
    res.pop("_scores")
    return res


def main() -> None:
    t0 = time.time()
    tx, val_start, test_start = load()
    truth = ground_truth(tx)
    val_mask = ((tx["timestamp"] >= val_start) & (tx["timestamp"] < test_start)).to_numpy()
    test_mask = tx["pred_hybrid"].notna().to_numpy()
    R = {"label_delay_days": LABEL_DELAY_DAYS, "val_start": str(val_start), "test_start": str(test_start),
         "n_test": int(test_mask.sum()), "n_test_fraud": int(tx.loc[test_mask, "is_fraud"].sum()),
         "truth_sizes": {k: len(v) for k, v in truth.items()}}

    for name, soft in (("etiquettes_differees", False), ("etiquettes_differees_plus_scores_modele", True)):
        net, g = replay(tx, val_start, use_model_scores=soft)
        R[name] = {"transactions": tx_metrics(tx, net, val_mask, test_mask)}
        if not soft:
            em = entity_metrics(g, truth)
            sc = em.pop("_scores")
            R["entites_fin_de_test"] = em
            R["reseaux_fin_de_test"] = ring_metrics(g, sc, truth)
    R["entites_sans_etiquette (scores du modèle seulement)"] = model_only_entities(tx, test_mask, truth)
    R["reseaux_30_derniers_jours"] = recent_window_rings(tx, test_mask, truth)
    R["duration_s"] = round(time.time() - t0, 1)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "graph_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    (REPORTS / "graph_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    (ARTIFACTS / "graph_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(to_markdown(R))


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %"


def to_markdown(R: dict) -> str:
    L = ["# Évaluation de l'analyse de réseau", "",
         f"Rejeu chronologique ; validation dès {R['val_start'][:10]}, test dès {R['test_start'][:10]} "
         f"({R['n_test']:,} transactions, {R['n_test_fraud']:,} fraudes). Verdicts révélés après "
         f"{R['label_delay_days']} jours. Vérité du générateur : {R['truth_sizes']}.", "",
         "## A. Transactions (période de test)", ""]
    for name, label in (("etiquettes_differees", "Étiquettes différées seulement"),
                        ("etiquettes_differees_plus_scores_modele", "Étiquettes différées + probabilités du modèle")):
        m = R[name]["transactions"]
        L += [f"### {label}", "",
              f"Seuil réseau choisi sur la validation pour {_pct(m['target_fpr'])} de fausses alertes : {m['threshold_from_validation']:.3f}.", "",
              "| Règle | Rappel | Fausses alertes | Précision | AP |", "|---|---|---|---|---|",
              f"| Modèle hybride seul | {_pct(m['model_alone']['recall'])} | {_pct(m['model_alone']['false_alert_rate'])} | {_pct(m['model_alone']['precision'])} | {m['model_alone']['average_precision']:.3f} |",
              f"| Réseau seul | {_pct(m['network_alone']['recall'])} | {_pct(m['network_alone']['false_alert_rate'])} | {_pct(m['network_alone']['precision'])} | {m['network_alone']['average_precision']:.3f} |",
              f"| Modèle OU réseau | {_pct(m['model_or_network']['recall'])} | {_pct(m['model_or_network']['false_alert_rate'])} | {_pct(m['model_or_network']['precision'])} | — |",
              "", f"Fraudes rattrapées par le réseau (manquées par le modèle) : **{m['frauds_rescued']}**, "
              f"pour {m['extra_false_alerts']} fausses alertes supplémentaires.", "",
              "| Typologie | Fraudes | Modèle | Modèle OU réseau | Rattrapées |", "|---|---|---|---|---|"]
        L += [f"| {ft} | {v['n']} | {_pct(v['model'])} | {_pct(v['hybrid_or_network'])} | {v['rescued']} |"
              for ft, v in m["by_fraud_type"].items()]
        L.append("")
    for key, title in (("entites_fin_de_test", "B. Entités partagées (fin du test, avec étiquettes)"),
                       ("entites_sans_etiquette (scores du modèle seulement)", "B'. Entités partagées sans aucune étiquette")):
        e = R[key]
        L += [f"## {title}", "", f"{e['n_shared_entities']:,} entités partagées, dont {e['n_true_shared']} réellement frauduleuses.", "",
              "| Classement | " + " | ".join(f"p@{k}" for k in KS) + " |", "|---" * (len(KS) + 1) + "|"]
        for k, v in e["entities"].items():
            L.append(f"| {k} | " + " | ".join(_pct(v[f'p@{kk}']) if f"p@{kk}" in v else "—" for kk in KS) + " |")
        L += ["", f"Comptes mules parmi les 10 comptes les plus exposés : {e['mule_accounts_in_top10_exposure']}.", ""]
    L += ["## C. Réseaux détectés", ""]
    for key, title in (("reseaux_fin_de_test", "Historique complet (avec étiquettes)"),
                       ("reseaux_30_derniers_jours", "30 derniers jours, probabilités du modèle seulement (écran Réseaux)")):
        r = R[key]
        L += [f"**{title}** : {r['n_rings']} réseaux ({r['n_entities_in_rings']} entités) ; le plus grand relie {r['largest_ring_accounts']} comptes. Pureté (entités réellement "
              f"frauduleuses) : {_pct(r['purity_entities'])} ; couverture des entités frauduleuses partagées : "
              f"{_pct(r['coverage_true_shared_entities'])}.", ""]
    L += ["_Le générateur réutilise un nombre fini de mules et d'appareils de fraudeurs : l'ampleur du gain dépend de "
          "cette hypothèse de simulation._", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
