"""
Robustesse face à un fraudeur qui s'adapte : tests adversariaux sur le modèle hybride champion.

Le fraudeur ne contrôle pas le modèle, mais il contrôle SA FAÇON D'OPÉRER. On réécrit tous les épisodes de fraude de la
période de test selon quatre stratégies réalistes, on recalcule toutes les variables comportementales (même extracteur
qu'en production, rejeu chronologique complet) et on rescore avec le modèle en service :

    fractionnement   chaque débit supérieur à 2 fois le montant habituel de la victime est découpé en k morceaux
                     (≈ 1,5 fois le montant habituel chacun, k ≤ 8) espacés de quelques minutes (« smurfing ») ;
    mimetisme        l'attaquant opère depuis l'appareil, le canal d'accès et la province habituels de la victime
                     (session relayée, maliciel sur le téléphone) ; il doit toujours encaisser : destinataires inchangés ;
    lenteur          l'épisode est étalé sur plusieurs jours, en journée (9 h - 17 h) : la vélocité ne trahit plus rien ;
    combinee         les trois à la fois.

Mesures (période de test) : rappel au seuil F1, interception par la politique de coût (vérification ou blocage),
détection d'ÉPISODE (au moins une opération interceptée), montant volé non intercepté, nombre d'opérations que
l'attaquant doit effectuer, et fausses alertes sur les opérations légitimes. Complément « réseau » : part des
transferts frauduleux envoyés à un portefeuille déjà impliqué dans une fraude confirmée (verdict révélé 7 jours plus
tard) : le mimétisme ne change pas le destinataire de l'argent.

ATTENTION : scénarios construits par l'équipe sur données simulées ; ils montrent OÙ le modèle est fragile et ce que
les autres défenses compensent, pas une performance contre de vrais fraudeurs.

Usage : python -m ml.robustness.evaluate_adversarial [--scenarios mimetisme,lenteur]
Sortie : ml/reports/adversarial_evaluation.json / .md (copie JSON dans ml/artifacts)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_engineering import DEBIT_TYPES, FEATURE_NAMES, RAW_DIR, _period_start, build_feature_table
from ml.models.hybrid_ensemble import HybridEnsemble
from ml.preprocessing.train_test_split_normalize import build_sequence_index
from shared.policy.costs import CostPolicy

ARTIFACTS = Path("ml/artifacts")
REPORTS = Path("ml/reports")
SCENARIOS = ("propre", "fractionnement", "mimetisme", "lenteur", "combinee")
LABEL_DELAY = pd.Timedelta(days=7)


# ---------------------------------------------------------------------- attaques
def _split(r: dict, typical: float, rng) -> list[dict]:
    amount = float(r["amount_usd"])
    if r["tx_type"] not in DEBIT_TYPES or typical <= 0 or amount <= 2 * typical:
        return [r]
    k = int(min(8, math.ceil(amount / (1.5 * typical))))
    before, t = float(r["balance_before_usd"] or 0.0), pd.Timestamp(r["timestamp"])
    out = []
    for j in range(k):
        piece = round(amount / k, 2)
        c = dict(r)
        c.update(transaction_id=f"{r['transaction_id']}-{j}", timestamp=t, amount_usd=piece,
                 amount=round(float(r["amount"]) / k, 2), balance_before_usd=round(before, 2),
                 balance_after_usd=round(max(before - piece, 0.0), 2))
        before -= piece
        t += pd.Timedelta(minutes=float(rng.uniform(1, 6)))
        out.append(c)
    return out


def _mimic(r: dict, u: pd.Series) -> dict:
    c = dict(r)
    smart = u["device_type"] == "smartphone"
    c.update(device_id=u["primary_device_id"], device_type=u["device_type"], location_province=u["province"])
    if c["access_channel"] != "AGENT":           # un retrait chez un agent reste chez un agent
        c["access_channel"] = "APP" if smart else "USSD"
        c["ip_country"] = "CD" if smart else None
    elif c["channel"] == "VISA_VIRTUAL":
        c["ip_country"] = "CD"
    if c["channel"] == "VISA_VIRTUAL":
        c["ip_country"] = "CD"
    return c


def attack(tx: pd.DataFrame, users: pd.DataFrame, test_from: pd.Timestamp, kind: str, seed: int = 0) -> pd.DataFrame:
    if kind == "propre":
        return tx
    rng = np.random.default_rng(seed)
    fr = tx[(tx["is_fraud"] == 1) & (tx["timestamp"] >= test_from)]
    u = users.set_index("user_id")
    out = []
    for _, g in fr.groupby("fraud_episode_id", sort=False):
        rows = g.sort_values("timestamp").to_dict("records")
        prof = u.loc[rows[0]["user_id"]]
        if kind in ("lenteur", "combinee"):
            t0 = pd.Timestamp(rows[0]["timestamp"]).normalize()
            day = 0.0
            for i, r in enumerate(rows):
                day += 0 if i == 0 else float(rng.uniform(1, 3))
                r["timestamp"] = t0 + pd.Timedelta(days=day) + pd.Timedelta(hours=float(rng.uniform(9, 17)))
        if kind in ("mimetisme", "combinee"):
            rows = [_mimic(r, prof) for r in rows]
        if kind in ("fractionnement", "combinee"):
            rows = [p for r in rows for p in _split(r, float(prof["typical_amount_usd"]), rng)]
        out.extend(rows)
    return pd.concat([tx.drop(fr.index), pd.DataFrame(out)], ignore_index=True)


# ---------------------------------------------------------------------- score
class Champion:
    def __init__(self):
        self.ens = HybridEnsemble.load(ARTIFACTS)
        self.scaler = joblib.load(ARTIFACTS / "scaler.pkl")
        prep = json.loads((ARTIFACTS / "preprocessing.json").read_text(encoding="utf-8"))
        self.clip, self.seq_len = prep["clip"], prep["seq_len"]
        self.test_from = pd.Timestamp(prep["split_bounds"]["test_from"])
        self.threshold = float(json.loads((ARTIFACTS / "metadata.json").read_text(encoding="utf-8"))["threshold"])

    def score(self, table: pd.DataFrame, rows: np.ndarray) -> np.ndarray:
        X = np.clip(self.scaler.transform(table[FEATURE_NAMES].to_numpy(np.float32)), -self.clip, self.clip).astype(np.float32)
        seq = build_sequence_index(table["user_id"], self.seq_len)
        return self.ens.predict_proba(X, seq, rows)


def network_flags(tx: pd.DataFrame) -> pd.Series:
    """Transfert envoyé à un portefeuille déjà impliqué dans une fraude dont le verdict est connu (≥ 7 jours avant)."""
    t = tx.sort_values("timestamp", kind="stable")
    known: dict[str, pd.Timestamp] = {}
    pending: list[tuple[pd.Timestamp, str]] = []
    flags = {}
    for r in t[["transaction_id", "timestamp", "tx_type", "counterparty_id", "is_fraud"]].itertuples(index=False):
        while pending and pending[0][0] <= r.timestamp:
            _, w = pending.pop(0)
            known.setdefault(w, r.timestamp)
        p2p = r.tx_type in ("P2P_SEND", "P2P_RECEIVE") and isinstance(r.counterparty_id, str)
        flags[r.transaction_id] = bool(p2p and r.counterparty_id in known)
        if p2p and r.is_fraud == 1:
            pending.append((r.timestamp + LABEL_DELAY, r.counterparty_id))
    return pd.Series(flags)


def evaluate(kind: str, tx: pd.DataFrame, users: pd.DataFrame, champ: Champion, policy: CostPolicy) -> dict:
    t0 = time.perf_counter()
    atk = attack(tx, users, champ.test_from, kind)
    table = build_feature_table(atk, users, _period_start(atk["timestamp"], RAW_DIR))
    extra = atk.set_index("transaction_id")[["fraud_episode_id", "operator", "counterparty_id"]]
    table = table.join(extra, on="transaction_id")
    rows = np.flatnonzero((table["timestamp"] >= champ.test_from).to_numpy())
    p = champ.score(table, rows)
    t = table.iloc[rows].reset_index(drop=True)
    t["p"] = p
    t["alert"] = p >= champ.threshold
    t["intercept"] = [policy.cost_action(pp, m, ch, op if isinstance(op, str) else None)[0] != "APPROVE"
                      for pp, m, ch, op in zip(p, t["amount_usd"], t["channel"], t["operator"])]
    net = network_flags(atk)
    t["network"] = t["transaction_id"].map(net).fillna(False).astype(bool)
    fr, lg = t[t["is_fraud"] == 1], t[t["is_fraud"] == 0]
    debit = fr["tx_type"].isin(DEBIT_TYPES)
    ep = fr.groupby("fraud_episode_id").agg(model=("intercept", "any"), net=("network", "any"),
                                            n=("transaction_id", "size"), ftype=("fraud_type", "first"))
    stolen = fr.loc[debit, "amount_usd"].sum()
    passed = fr.loc[debit & ~fr["intercept"], "amount_usd"].sum()
    return {
        "scenario": kind, "n_fraud_tx": int(len(fr)), "n_episodes": int(len(ep)),
        "tx_per_episode": round(float(ep["n"].mean()), 2),
        "recall_threshold": round(float(fr["alert"].mean()), 4),
        "recall_intercept": round(float(fr["intercept"].mean()), 4),
        "episode_detection": round(float(ep["model"].mean()), 4),
        "episode_detection_with_network": round(float((ep["model"] | ep["net"]).mean()), 4),
        "stolen_usd": round(float(stolen), 2), "stolen_not_intercepted_usd": round(float(passed), 2),
        "share_not_intercepted": round(float(passed / stolen), 4) if stolen else 0.0,
        "legit_intercept_rate": round(float(lg["intercept"].mean()), 5),
        "legit_alert_rate": round(float(lg["alert"].mean()), 5),
        "episode_detection_by_type": {str(k): round(float(v), 4) for k, v in ep.groupby("ftype")["model"].mean().items()},
        "duration_s": round(time.perf_counter() - t0, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    kinds = [k for k in ap.parse_args().scenarios.split(",") if k]
    tx = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["timestamp"], low_memory=False)
    users = pd.read_csv(RAW_DIR / "users.csv")
    champ, policy = Champion(), CostPolicy()
    out_path = REPORTS / "adversarial_evaluation.json"
    R = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    R.setdefault("scenarios", {})
    R["threshold"] = champ.threshold
    for k in kinds:
        res = evaluate(k, tx, users, champ, policy)
        R["scenarios"][k] = res
        print(json.dumps({x: res[x] for x in ("scenario", "recall_intercept", "episode_detection",
                                              "episode_detection_with_network", "share_not_intercepted", "duration_s")},
                         ensure_ascii=False), flush=True)
        out_path.write_text(json.dumps(R, indent=2, ensure_ascii=False), encoding="utf-8")   # résultat partiel conservé
    (ARTIFACTS / "adversarial_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "adversarial_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    print(to_markdown(R))


LABEL = {"propre": "Fraudes telles quelles", "fractionnement": "Fractionnement sous le montant habituel",
         "mimetisme": "Appareil, canal et province de la victime", "lenteur": "Épisode étalé sur plusieurs jours",
         "combinee": "Les trois combinées"}


def to_markdown(R: dict) -> str:
    L = ["# Robustesse face à un fraudeur qui s'adapte", "",
         "Tous les épisodes de fraude de la période de test sont réécrits selon chaque stratégie, les variables sont "
         "recalculées et le modèle hybride en service rescore. « Interceptée » : vérification ou blocage par la politique "
         "de coût.", "",
         "| Stratégie du fraudeur | Opérations / épisode | Rappel (seuil F1) | Interceptées | Épisodes détectés | + réseau | Montant volé non intercepté | Fausses alertes (légitimes) |",
         "|---|---|---|---|---|---|---|---|"]
    for k in SCENARIOS:
        s = R["scenarios"].get(k)
        if not s:
            continue
        L.append(f"| {LABEL[k]} | {s['tx_per_episode']} | {100 * s['recall_threshold']:.1f} % | {100 * s['recall_intercept']:.1f} % | "
                 f"{100 * s['episode_detection']:.1f} % | {100 * s['episode_detection_with_network']:.1f} % | "
                 f"{100 * s['share_not_intercepted']:.1f} % | {100 * s['legit_intercept_rate']:.2f} % |")
    L += ["", "_Scénarios construits sur données simulées : ils montrent où le modèle est fragile, pas une performance "
          "contre de vrais fraudeurs._", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
