"""
Simulateur de trafic opérateurs (démo temps réel).

Rejoue les transactions de la période de TEST (jamais vues à l'entraînement) dans l'ordre
chronologique. Chaque transaction est convertie dans le format PROPRIÉTAIRE de son
opérateur (Vodacom, Airtel, Orange, Visa) puis envoyée à l'integration-layer, comme le
feraient les systèmes des opérateurs.

Le statut réel (succès / solde insuffisant) n'est PAS envoyé : comme en production, la
transaction est scorée avant exécution.

Usage :
    python scripts/simulate_transactions.py --rate 20            # 20 transactions / seconde
    python scripts/simulate_transactions.py --rate 50 --n 2000
    python scripts/simulate_transactions.py --only-fraud-episodes --rate 5   # démo jury
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "integration-layer"))

from app.adapters.airtel_adapter import AirtelAdapter  # noqa: E402
from app.adapters.orange_adapter import OrangeAdapter  # noqa: E402
from app.adapters.visa_virtual_adapter import VisaVirtualAdapter  # noqa: E402
from app.adapters.vodacom_adapter import VodacomAdapter  # noqa: E402
from shared.schemas.unified_transaction import canonical_id  # noqa: E402

ADAPTERS = {"vodacom": VodacomAdapter(), "airtel": AirtelAdapter(), "orange": OrangeAdapter(),
            "visa": VisaVirtualAdapter()}
KEYS = {"vodacom": "dev-vodacom-key", "airtel": "dev-airtel-key", "orange": "dev-orange-key",
        "visa": "dev-visa-key"}
COLORS = {"APPROVE": "\033[32m", "VERIFY": "\033[33m", "BLOCK": "\033[31m"}


# DÉMO UNIQUEMENT : messages rédigés par l'équipe pour montrer l'analyse de texte. Les données d'entraînement
# n'en contiennent pas ; ces messages ne prouvent donc rien sur la performance réelle (voir ml/reports/nlp_evaluation.json).
DEMO_SCAM_MEMOS = [
    "Je suis du service client Vodacom, votre compte sera bloque, envoyez-moi votre code PIN",
    "Felicitations vous avez gagne 1000 USD, payez les frais de dossier pour recevoir votre lot",
    "Ici la banque, donnez le code de verification recu par SMS pour annuler une fraude",
    "J'ai envoye de l'argent par erreur, renvoyez-moi le montant vite svp",
]
DEMO_BENIGN_MEMOS = ["loyer de novembre merci", "cotisation tontine", "achat au marche", "frais de scolarite"]


def add_demo_memos(rows: list[dict], seed: int = 7) -> None:
    import random
    rnd = random.Random(seed)
    for r in rows:
        if r["tx_type"] != "P2P_SEND":
            continue
        if r["is_fraud"] == 1 and r["fraud_type"] == "SOCIAL_ENGINEERING" and rnd.random() < 0.6:
            r["memo"] = rnd.choice(DEMO_SCAM_MEMOS)
        elif r["is_fraud"] == 0 and rnd.random() < 0.2:
            r["memo"] = rnd.choice(DEMO_BENIGN_MEMOS)


def load(n: int | None, skip: int, only_fraud: bool, fraud_users: int = 40, user_offset: int = 0) -> list[dict]:
    prep = json.loads((ROOT / "ml/artifacts/preprocessing.json").read_text(encoding="utf-8"))
    tx = pd.read_csv(ROOT / "ml/data/raw/transactions.csv")
    tx["timestamp"] = pd.to_datetime(tx["timestamp"])
    tx = tx.sort_values(["timestamp", "transaction_id"], kind="mergesort")
    tx = tx[tx["timestamp"] >= pd.Timestamp(prep["split_bounds"]["test_from"])].iloc[skip:]
    if only_fraud:
        # épisodes de fraude + un peu de trafic normal autour, pour une démo lisible
        victims = list(dict.fromkeys(tx.loc[tx["is_fraud"] == 1, "user_id"]))
        users = set(victims[user_offset:user_offset + fraud_users])
        tx = tx[tx["user_id"].isin(users)]
    if n:
        tx = tx.head(n)
    tx = tx.astype(object).where(tx.notna(), None)
    rows = []
    for r in tx.to_dict("records"):
        for k in ("user_id", "wallet_id", "card_id", "counterparty_id", "merchant_id", "agent_id", "device_id"):
            r[k] = canonical_id(r[k])
        r["timestamp"] = pd.Timestamp(r["timestamp"]).to_pydatetime()
        r["status"] = None  # inconnu au moment du scoring
        rows.append(r)
    return rows


def provider_of(r: dict) -> str:
    return "visa" if r["channel"] == "VISA_VIRTUAL" else r["operator"].lower()


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8002")
    p.add_argument("--rate", type=float, default=20, help="transactions par seconde")
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--skip", type=int, default=0)
    p.add_argument("--only-fraud-episodes", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--fraud-users", type=int, default=40, help="nombre de clients victimes rejoués")
    p.add_argument("--user-offset", type=int, default=0, help="clients victimes à ignorer (échantillon neuf)")
    p.add_argument("--fresh-ids", action="store_true",
                   help="suffixe chaque identifiant (~xxxxxx) : un nouveau rejeu crée de nouvelles lignes au lieu d'être ignoré "
                        "par la base (ON CONFLICT DO NOTHING). À réamorcer Redis avant pour des profils neufs.")
    p.add_argument("--demo-memos", action="store_true",
                   help="DÉMO : ajoute des motifs de transfert rédigés par l'équipe (arnaques et messages anodins)")
    p.add_argument("--report", action="store_true",
                   help="détection en temps réel par type de fraude -> ml/reports/realtime_replay.json")
    a = p.parse_args()

    rows = load(a.n, a.skip, a.only_fraud_episodes, a.fraud_users, a.user_offset)
    if a.demo_memos:
        add_demo_memos(rows)
    if a.fresh_ids:
        import uuid
        tag = uuid.uuid4().hex[:6]
        for r in rows:
            r["transaction_id"] = f"{r['transaction_id']}~{tag}"
    print(f"{len(rows)} transactions à rejouer à {a.rate}/s vers {a.url}\n")
    stats, lat, tp, fn, fp = Counter(), [], 0, 0, 0
    per_type: dict = {}
    fraud_events: list = []
    sem = asyncio.Semaphore(64)
    async with httpx.AsyncClient(base_url=a.url, timeout=5) as client:
        async def send(r):
            nonlocal tp, fn, fp
            prov = provider_of(r)
            async with sem:
                try:
                    resp = await client.post(f"/v1/transactions/{prov}", json=ADAPTERS[prov].from_unified(r),
                                             headers={"X-API-Key": KEYS[prov]})
                    try:
                        d = resp.json()
                    except ValueError:
                        d = {"detail": resp.text[:200]}
                except httpx.HTTPError as e:
                    stats["erreur"] += 1
                    print(f"erreur réseau ({type(e).__name__}) sur {r['transaction_id']} : {e or 'délai dépassé'}")
                    return
            if resp.status_code != 200:
                stats["erreur"] += 1
                print(f"erreur HTTP {resp.status_code} sur {r['transaction_id']} : {d}")
                return
            if d.get("risk_level") == "INCONNU":      # politique de repli : le scoring n'a pas répondu
                stats["repli"] += 1                    # exclu des mesures (ce n'est pas une décision du modèle)
                return
            action = d["action"]
            stats[action] += 1
            lat.append(d.get("end_to_end_ms", 0))
            caught = action != "APPROVE"
            if r["is_fraud"] == 1:
                fraud_events.append((r["timestamp"], r["user_id"], r["fraud_type"], action,
                                     d.get("fraud_type"), r["amount_usd"]))
                t = per_type.setdefault(r["fraud_type"], Counter())
                t["n"] += 1
                t["detectee"] += caught
                t["bloquee"] += action == "BLOCK"
                t["type_connu"] += d.get("fraud_type") is not None
                t["type_correct"] += d.get("fraud_type") == r["fraud_type"]
            else:
                legit = per_type.setdefault("LEGITIME", Counter())
                legit["n"] += 1
                legit["detectee"] += caught
                legit["bloquee"] += action == "BLOCK"
            if r["is_fraud"] == 1:
                tp += caught
                fn += not caught
            else:
                fp += action == "BLOCK"
            if not a.quiet and (action != "APPROVE" or r["is_fraud"] == 1):
                truth = f"FRAUDE {r['fraud_type']}" if r["is_fraud"] == 1 else "légitime"
                print(f"{COLORS.get(action, '')}{action:7s}\033[0m p={d['fraud_probability']:.3f} "
                      f"{d['risk_level']:8s} {prov:7s} {r['tx_type']:16s} {r['amount_usd']:>9.2f} USD "
                      f"| réalité : {truth} | {d['end_to_end_ms']:.0f} ms")

        t0 = time.perf_counter()
        tasks = []
        for i, r in enumerate(rows):
            target = t0 + i / a.rate
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(send(r)))
        await asyncio.gather(*tasks)
        dt = time.perf_counter() - t0

    lat_s = sorted(lat)
    pct = lambda q: lat_s[min(len(lat_s) - 1, int(q * len(lat_s)))] if lat_s else 0  # noqa: E731
    print(f"\n{len(rows)} transactions en {dt:.1f} s ({len(rows) / dt:.1f}/s) : {dict(stats)}")
    print(f"latence bout-en-bout : p50={pct(0.5):.0f} ms  p95={pct(0.95):.0f} ms  p99={pct(0.99):.0f} ms")
    if a.report and per_type:
        print("\nDétection en temps réel par type de fraude (VERIFY ou BLOCK) et type identifié :")
        out = {}
        for name, c in sorted(per_type.items()):
            n = c["n"]
            row = {"n": n, "detectees": c["detectee"], "taux_detection": round(c["detectee"] / n, 4),
                   "bloquees": c["bloquee"]}
            if name != "LEGITIME":
                row.update(type_correct_parmi_detectees=round(c["type_correct"] / max(c["detectee"], 1), 4),
                           type_correct_parmi_toutes=round(c["type_correct"] / n, 4))
            out[name] = row
            extra = (f"  type correct parmi détectées {row['type_correct_parmi_detectees']:.0%}"
                     if name != "LEGITIME" else "  (taux de fausses alertes)")
            print(f"  {name:<20} n={n:>5}  détectées {row['taux_detection']:>6.1%}  bloquées {c['bloquee']:>4}{extra}")
        # Vue par ÉPISODE (même client et même typologie, coupure après 6 h sans fraude) : ce qui compte
        # en temps réel, c'est de stopper l'épisode dès la première opération. Une opération bloquée
        # arrête la chaîne dans la réalité ; les suivantes ne sont rejouées que par la simulation.
        episodes: dict = {}
        key_last: dict = {}
        for ev in sorted(fraud_events, key=lambda e: e[0]):
            k = (ev[1], ev[2])
            if k in key_last and (ev[0] - key_last[k][0]).total_seconds() <= 6 * 3600:
                episodes[key_last[k][1]].append(ev)
            else:
                key_last[k] = (ev[0], len(episodes))
                episodes[len(episodes)] = [ev]
            key_last[k] = (ev[0], key_last[k][1])
        agg: dict = {}
        for evs in episodes.values():
            ftype = evs[0][2]
            first_alert = next((i for i, e in enumerate(evs) if e[3] != "APPROVE"), None)
            g = agg.setdefault(ftype, Counter())
            g["n"] += 1
            if first_alert is not None:
                g["detected"] += 1
                g["immediate"] += first_alert == 0
                g["first_type_ok"] += evs[first_alert][4] == ftype
                g["passed_before"] += first_alert
                g["usd_passed"] += sum(e[5] for e in evs[:first_alert])
            g["usd_total"] += sum(e[5] for e in evs)
        print("\nPar épisode de fraude (arrêt dès la première opération suspecte) :")
        ep_out = {}
        for ftype, g in sorted(agg.items()):
            det = max(g["detected"], 1)
            ep_out[ftype] = {"episodes": g["n"], "detectes": g["detected"],
                             "taux_detection": round(g["detected"] / g["n"], 4),
                             "stoppes_des_la_1ere_operation": round(g["immediate"] / g["n"], 4),
                             "type_correct_a_la_1ere_alerte": round(g["first_type_ok"] / det, 4),
                             "operations_passees_avant_alerte_moy": round(g["passed_before"] / det, 2),
                             "usd_passes_avant_alerte": round(g["usd_passed"], 2),
                             "usd_total_episodes": round(g["usd_total"], 2)}
            e = ep_out[ftype]
            print(f"  {ftype:<20} épisodes={g['n']:>3}  détectés {e['taux_detection']:>6.1%}  stoppés dès la 1re opération "
                  f"{e['stoppes_des_la_1ere_operation']:>6.1%}  type correct 1re alerte {e['type_correct_a_la_1ere_alerte']:>5.0%}  "
                  f"perte avant alerte {e['usd_passes_avant_alerte']:>8.2f} / {e['usd_total_episodes']:.2f} USD")
        out["_episodes"] = ep_out
        out["_meta"] = {"transactions": len(rows), "cadence_par_s": a.rate, "latence_p50_ms": pct(0.5),
                        "latence_p95_ms": pct(0.95), "latence_p99_ms": pct(0.99)}
        (ROOT / "ml/reports/realtime_replay.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                                             encoding="utf-8")
    if tp + fn:
        print(f"fraudes interceptées (VERIFY ou BLOCK) : {tp}/{tp + fn} ; clients honnêtes bloqués : {fp}")


if __name__ == "__main__":
    asyncio.run(main())
