"""Boucle de retour des analystes vers le modèle.

1. File de revue prioritaire (GET /feedback/queue) : les analystes ne voient d'habitude que les ALERTES ; le modèle
   n'apprend alors que de ses propres décisions et on ne peut pas mesurer ce qu'il laisse passer. La file propose des
   transactions APPROUVÉES et non étiquetées, choisies pour ce qu'elles apprennent :
       INCERTITUDE  le modèle a hésité (probabilité au plus près du seuil) : apprentissage actif ;
       NOUVEAUTE    comportement inconnu de l'autoencodeur ;
       RESEAU       reliée à une entité à risque (portefeuille mule, appareil de fraudeur…) ;
       TEMOIN       tirage ALÉATOIRE (graine du jour) : seule source sans biais du taux de fraudes manquées.
   Le motif est conservé dans le dossier (cases.review_reason) lors de la revue (POST /cases/review).
2. Qualité réelle (GET /feedback/quality) : précision des alertes d'après les verdicts, taux de fraudes manquées
   estimé sur l'échantillon témoin, rappel estimé, calibration, apport de chaque source d'étiquettes."""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers.network import _snapshot
from app.security import get_current_user

router = APIRouter(prefix="/feedback", tags=["boucle de retour"])

REASONS = ("INCERTITUDE", "NOUVEAUTE", "RESEAU", "TEMOIN")
NETWORK_MIN_SCORE = 0.5
NETWORK_WINDOW_MIN = 1440      # même instantané (24 h) que l'écran Réseaux : déjà en cache
QUEUE_TTL_S = 60               # la file n'a pas besoin d'être temps réel ; les cas jugés entre-temps sont retirés
_queue_cache: dict[tuple[int, int], tuple[float, dict]] = {}
_queue_lock = threading.Lock()
_TX_COLS = """s.transaction_id, s.tx_time, s.scored_at, s.user_id, s.channel, s.operator, s.tx_type, s.province,
              s.amount_usd, s.fraud_probability, s.risk_level, s.action, s.fraud_type"""
_UNREVIEWED = "s.label IS NULL AND s.action = 'APPROVE' AND s.scored_at > now() - make_interval(days => :d)"


def model_threshold() -> float:
    try:
        meta = Path(settings.RAG_INDEX_PATH).parent / "metadata.json"
        return float(json.loads(meta.read_text(encoding="utf-8"))["threshold"])
    except (OSError, ValueError, KeyError):
        return 0.5


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    """Proportion et intervalle de confiance de Wilson à 95 % (fiable pour de petits effectifs)."""
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "low": None, "high": None}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"k": k, "n": n, "rate": p, "low": max(0.0, c - h), "high": min(1.0, c + h)}


def _rows(db: Session, sql: str, **params) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


# ---------------------------------------------------------------------- file de revue
@router.get("/queue")
def queue(days: int = Query(7, ge=1, le=60), per_reason: int = Query(10, ge=1, le=50),
          db: Session = Depends(get_db), _=Depends(get_current_user)):
    key = (days, per_reason)
    with _queue_lock:
        hit = _queue_cache.get(key)
        if hit is None or time.monotonic() - hit[0] > QUEUE_TTL_S:
            hit = (time.monotonic(), _build_queue(db, days, per_reason))
            _queue_cache.clear()
            _queue_cache[key] = hit
    res = hit[1]
    ids = [r["transaction_id"] for k in REASONS for r in res["reasons"][k]]
    done = {r[0] for r in db.execute(text("""SELECT transaction_id FROM scored_transactions
                                              WHERE transaction_id = ANY(:ids) AND label IS NOT NULL"""), {"ids": ids})}
    return {**res, "reasons": {k: [r for r in res["reasons"][k] if r["transaction_id"] not in done] for k in REASONS}}


def _build_queue(db: Session, days: int, per_reason: int) -> dict:
    t = min(max(model_threshold(), 1e-6), 1 - 1e-6)
    out: dict[str, list[dict]] = {}

    out["INCERTITUDE"] = _rows(db, f"""
        SELECT {_TX_COLS} FROM scored_transactions s WHERE {_UNREVIEWED}
        ORDER BY abs(ln(greatest(least(s.fraud_probability, 1 - 1e-6), 1e-6)
                        / (1 - greatest(least(s.fraud_probability, 1 - 1e-6), 1e-6))) - :lt)
        LIMIT :n""", d=days, n=per_reason, lt=math.log(t / (1 - t)))
    for r in out["INCERTITUDE"]:
        r["why"] = f"probabilité {r['fraud_probability']:.0%}, seuil {t:.0%} : le modèle a hésité"

    out["NOUVEAUTE"] = _rows(db, f"""
        SELECT {_TX_COLS}, CAST(s.explanation->'branch_scores'->>'autoencoder' AS float) AS novelty
        FROM scored_transactions s
        WHERE {_UNREVIEWED} AND s.explanation->'branch_scores'->>'autoencoder' IS NOT NULL
        ORDER BY novelty DESC LIMIT :n""", d=days, n=per_reason)
    for r in out["NOUVEAUTE"]:
        r["why"] = f"comportement jamais vu (écart de reconstruction {r.pop('novelty'):.2f})"

    g, sc, _, _ = _snapshot(db, NETWORK_WINDOW_MIN)
    cand = _rows(db, f"""
        SELECT {_TX_COLS}, s.counterparty_id, s.device_id, s.agent_id, s.merchant_id
        FROM scored_transactions s WHERE {_UNREVIEWED} ORDER BY s.scored_at DESC LIMIT 5000""", d=1)
    scored = []
    for r in cand:
        net = g.tx_network_score(r, sc)
        if net["score"] >= NETWORK_MIN_SCORE and net["entity"]:
            for k in ("counterparty_id", "device_id", "agent_id", "merchant_id"):
                r.pop(k)
            r["network_score"], r["network_entity"] = round(net["score"], 4), net["entity"]
            r["why"] = f"liée à {net['entity']} (risque réseau {net['score']:.0%})"
            scored.append(r)
    out["RESEAU"] = sorted(scored, key=lambda r: -r["network_score"])[:per_reason]

    # graine du jour : tirage reproductible dans la journée, renouvelé chaque jour
    out["TEMOIN"] = _rows(db, f"""
        SELECT {_TX_COLS} FROM scored_transactions s WHERE {_UNREVIEWED}
        ORDER BY md5(s.transaction_id || :seed) LIMIT :n""", d=days, n=per_reason, seed=date.today().isoformat())
    for r in out["TEMOIN"]:
        r["why"] = "tirage aléatoire parmi les transactions approuvées : mesure les fraudes manquées"

    return {"threshold": t, "days": days, "reasons": {k: out[k] for k in REASONS}}


# ---------------------------------------------------------------------- qualité réelle
@router.get("/quality")
def quality(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _=Depends(get_current_user)):
    win = "s.scored_at > now() - make_interval(days => :d)"
    tot = _rows(db, f"""
        SELECT count(*) AS n_tx,
               count(*) FILTER (WHERE s.action <> 'APPROVE') AS alerts,
               count(*) FILTER (WHERE s.action <> 'APPROVE' AND s.label IS NOT NULL) AS alerts_reviewed,
               count(*) FILTER (WHERE s.action <> 'APPROVE' AND s.label = 1) AS alerts_confirmed,
               count(*) FILTER (WHERE s.action = 'APPROVE') AS approved
        FROM scored_transactions s WHERE {win}""", d=days)[0]

    by_reason = _rows(db, f"""
        SELECT c.review_reason AS reason, count(*) AS n,
               count(*) FILTER (WHERE c.status = 'FRAUDE_CONFIRMEE') AS frauds
        FROM cases c JOIN scored_transactions s ON s.transaction_id = c.transaction_id AND s.tx_time = c.tx_time
        WHERE {win} AND c.status IN ('FRAUDE_CONFIRMEE', 'FAUX_POSITIF')
        GROUP BY c.review_reason ORDER BY n DESC""", d=days)
    reason = {r["reason"]: r for r in by_reason}

    precision = wilson(tot["alerts_confirmed"], tot["alerts_reviewed"])
    control = wilson(reason.get("TEMOIN", {}).get("frauds", 0), reason.get("TEMOIN", {}).get("n", 0))
    approved = tot["approved"]
    estimate = None
    if control["n"] and precision["n"]:
        missed = {k: control[k] * approved for k in ("rate", "low", "high")}
        caught = precision["rate"] * tot["alerts"]
        estimate = {
            "missed_frauds": round(missed["rate"], 1),
            "missed_frauds_ci": [round(missed["low"], 1), round(missed["high"], 1)],
            "caught_frauds": round(caught, 1),
            "recall": caught / (caught + missed["rate"]) if caught + missed["rate"] else None,
            # rappel au pire / au mieux selon l'intervalle du taux de fraudes manquées
            "recall_ci": [caught / (caught + missed["high"]) if caught + missed["high"] else None,
                          caught / (caught + missed["low"]) if caught + missed["low"] else None],
        }

    by_risk = _rows(db, f"""
        SELECT s.risk_level, count(*) AS n, count(*) FILTER (WHERE s.label = 1) AS frauds
        FROM scored_transactions s WHERE {win} AND s.action <> 'APPROVE' AND s.label IS NOT NULL
        GROUP BY s.risk_level""", d=days)
    by_type = _rows(db, f"""
        SELECT coalesce(s.fraud_type, 'INCONNU') AS fraud_type, count(*) AS n, count(*) FILTER (WHERE s.label = 1) AS frauds
        FROM scored_transactions s WHERE {win} AND s.action <> 'APPROVE' AND s.label IS NOT NULL
        GROUP BY 1 ORDER BY n DESC LIMIT 10""", d=days)
    daily = _rows(db, f"""
        SELECT date_trunc('day', s.scored_at) AS day, count(*) AS n, count(*) FILTER (WHERE s.label = 1) AS frauds
        FROM scored_transactions s WHERE {win} AND s.action <> 'APPROVE' AND s.label IS NOT NULL
        GROUP BY 1 ORDER BY 1""", d=days)
    calibration = _rows(db, f"""
        SELECT width_bucket(s.fraud_probability, 0, 1, 10) AS bin, count(*) AS n,
               avg(s.fraud_probability) AS predicted, avg(s.label::float) AS observed
        FROM scored_transactions s WHERE {win} AND s.label IS NOT NULL
        GROUP BY 1 ORDER BY 1""", d=days)
    backlog = _rows(db, """
        SELECT count(*) FILTER (WHERE status IN ('OUVERT', 'EN_COURS')) AS open_cases,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM resolved_at - created_at) / 3600)
                 FILTER (WHERE resolved_at > now() - make_interval(days => :d)) AS median_hours_to_verdict
        FROM cases""", d=days)[0]

    return {
        "days": days, "threshold": model_threshold(), **tot,
        "alert_precision": precision,
        "control_sample": control,
        "complaints": reason.get("PLAINTE", {}).get("n", 0),
        "estimate": estimate,
        "labels_by_reason": [{**r, "fraud_rate": r["frauds"] / r["n"] if r["n"] else None} for r in by_reason],
        "precision_by_risk": [{**r, **wilson(r["frauds"], r["n"])} for r in by_risk],
        "precision_by_type": [{**r, **wilson(r["frauds"], r["n"])} for r in by_type],
        "precision_daily": [{**r, "rate": r["frauds"] / r["n"]} for r in daily],
        "calibration": [{**r, "predicted": float(r["predicted"]), "observed": float(r["observed"])} for r in calibration],
        "open_cases": backlog["open_cases"],
        "median_hours_to_verdict": float(backlog["median_hours_to_verdict"]) if backlog["median_hours_to_verdict"] is not None else None,
    }
