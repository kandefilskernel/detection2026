"""Équité du modèle en production : les alertes touchent-elles certains groupes de clients plus que d'autres ?

En direct, la vérité n'est connue que pour les transactions jugées : on suit donc le TAUX D'ALERTE par groupe (proche
du taux de fausses alertes, la fraude étant rare) et, quand des verdicts existent, la part de FAUX POSITIFS confirmés
parmi les alertes jugées. Un groupe est signalé quand son taux d'alerte dépasse 1,25 fois le taux global avec un écart
significatif (borne basse de l'intervalle de Wilson au-dessus du taux global). L'évaluation hors ligne, avec la vérité
complète, est servie par GET /fairness/evaluation (ml/robustness/evaluate_fairness.py)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers.feedback import wilson
from app.security import get_current_user

router = APIRouter(prefix="/fairness", tags=["équité"])

RATIO = 1.25
MIN_N = 200
# dimension -> expression SQL (les variables du modèle sont conservées dans `features`)
DIMENSIONS = {
    "province": ("Province de l'opération", "s.province"),
    "operator": ("Opérateur", "coalesce(s.operator, 'VISA')"),
    "access_channel": ("Canal d'accès", "s.access_channel"),
    "kyc_level": ("Niveau KYC", "'KYC ' || coalesce(round((s.features->>'kyc_level')::numeric)::text, '?')"),
    "device": ("Type de téléphone", "CASE WHEN (s.features->>'is_smartphone')::float >= 0.5 THEN 'smartphone' ELSE 'téléphone simple' END"),
    "channel": ("Canal", "s.channel"),
}


@router.get("/live")
def live(dimension: str = Query("province"), days: int = Query(30, ge=1, le=365),
         db: Session = Depends(get_db), _=Depends(get_current_user)):
    if dimension not in DIMENSIONS:
        raise HTTPException(422, f"dimensions : {', '.join(DIMENSIONS)}")
    label, expr = DIMENSIONS[dimension]
    rows = db.execute(text(f"""
        SELECT {expr} AS grp, count(*) AS n,
               count(*) FILTER (WHERE s.action <> 'APPROVE') AS alerts,
               count(*) FILTER (WHERE s.action = 'BLOCK') AS blocks,
               count(*) FILTER (WHERE s.action <> 'APPROVE' AND s.label IS NOT NULL) AS reviewed,
               count(*) FILTER (WHERE s.action <> 'APPROVE' AND s.label = 0) AS false_positives
        FROM scored_transactions s WHERE s.scored_at > now() - make_interval(days => :d)
        GROUP BY 1 ORDER BY 2 DESC"""), {"d": days}).mappings().all()
    n_all = sum(r["n"] for r in rows)
    a_all = sum(r["alerts"] for r in rows)
    overall = a_all / n_all if n_all else None
    groups = []
    for r in rows:
        rate = wilson(r["alerts"], r["n"])
        fp = wilson(r["false_positives"], r["reviewed"])
        ratio = rate["rate"] / overall if overall and rate["rate"] is not None else None
        judged = r["n"] >= MIN_N
        groups.append({"group": r["grp"] or "inconnu", "n": r["n"], "alerts": r["alerts"], "blocks": r["blocks"],
                       "alert_rate": rate["rate"], "alert_ci": [rate["low"], rate["high"]], "ratio": ratio,
                       "reviewed": r["reviewed"], "false_positive_share": fp["rate"], "judged": judged,
                       "flagged": bool(judged and ratio is not None and ratio >= RATIO and rate["low"] > overall)})
    groups.sort(key=lambda g: -(g["alert_rate"] or 0))
    rates = [g["alert_rate"] for g in groups if g["judged"] and g["alert_rate"]]
    return {"dimension": dimension, "label": label, "days": days, "n": n_all, "overall_alert_rate": overall,
            "ratio_rule": RATIO, "min_n": MIN_N, "max_min_ratio": max(rates) / min(rates) if len(rates) >= 2 else None,
            "dimensions": {k: v[0] for k, v in DIMENSIONS.items()}, "groups": groups}


@router.get("/evaluation")
def evaluation(_=Depends(get_current_user)):
    try:
        return json.loads((Path(settings.RAG_INDEX_PATH).parent / "fairness_evaluation.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "évaluation non disponible : lancer python -m ml.robustness.evaluate_fairness") from None
