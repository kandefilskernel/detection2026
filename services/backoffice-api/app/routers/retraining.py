"""Apprentissage continu : état des signaux, journal, demande de réentraînement, comportements nouveaux à examiner."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.events import Publisher, get_publisher
from app.security import get_current_user, require_role
from shared.database.models import BackofficeUser, RetrainEvent, RetrainState

router = APIRouter(prefix="/retraining", tags=["retraining"])


def event_dict(e: RetrainEvent) -> dict:
    return {"id": e.id, "ts": e.ts, "trigger": e.trigger, "reasons": e.reasons, "status": e.status,
            "detail": e.detail, "requested_by": e.requested_by, "handled_at": e.handled_at}


def training_diagnostics() -> dict | None:
    """Courbes d'apprentissage du modèle en place (écrites par l'entraînement ou ml.training.diagnose_training)."""
    try:
        return json.loads((Path(settings.RAG_INDEX_PATH).parent / "training_diagnostics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(get_current_user)):
    state = db.get(RetrainState, 1)
    events = db.scalars(select(RetrainEvent).order_by(RetrainEvent.ts.desc()).limit(15)).all()
    champion = db.execute(text("SELECT version, created_at FROM model_registry WHERE status = 'CHAMPION' "
                               "ORDER BY id DESC LIMIT 1")).first()
    return {"signals": state.signals if state else None, "signals_at": state.updated_at if state else None,
            "champion": {"version": champion[0], "since": champion[1]} if champion else None,
            "training_diagnostics": training_diagnostics(),
            "events": [event_dict(e) for e in events],
            "pending_request": any(e.status == "DEMANDEE" and e.handled_at is None for e in events)}


@router.post("/trigger", status_code=202)
def trigger(db: Session = Depends(get_db), user: BackofficeUser = Depends(require_role("SUPERVISEUR")),
            pub: Publisher = Depends(get_publisher)):
    """Demande un réentraînement : le planificateur la prend en charge en moins d'une minute. Les garde-fous
    sur les données étiquetées s'appliquent toujours ; le nouveau modèle n'est promu que s'il est meilleur."""
    if db.scalar(select(RetrainEvent).where(RetrainEvent.status == "DEMANDEE", RetrainEvent.handled_at.is_(None))):
        raise HTTPException(409, "une demande de réentraînement est déjà en attente")
    ev = RetrainEvent(trigger="MANUEL", reasons=["demande manuelle"], status="DEMANDEE", detail={},
                      requested_by=user.email)
    db.add(ev)
    db.commit()
    pub.audit(user.email, "REENTRAINEMENT_DEMANDE", "model", None, {"event_id": ev.id})
    return event_dict(ev)


@router.get("/novel-behaviors")
def novel_behaviors(limit: int = Query(10, ge=1, le=50), days: int = Query(7, ge=1, le=60),
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Transactions récentes non étiquetées dont le comportement s'écarte le plus de l'habituel (erreur de
    reconstruction de l'autoencodeur). Ce sont les meilleures candidates à une revue d'analyste : leurs verdicts
    apprennent au modèle les comportements qu'il ne connaît pas encore."""
    ref = Path(settings.RAG_INDEX_PATH).parent / "drift_reference.npz"
    threshold = None
    try:
        z = np.load(ref, allow_pickle=False)
        if "ae_scores" in z:
            threshold = float(np.quantile(z["ae_scores"], 0.99))
    except OSError:
        pass
    rows = db.execute(text("""
        SELECT transaction_id, tx_time, channel, tx_type, province, amount_usd, action, risk_level, fraud_probability,
               fraud_type, CAST(explanation->'branch_scores'->>'autoencoder' AS float) AS novelty
        FROM scored_transactions
        WHERE label IS NULL AND scored_at > now() - make_interval(days => :d)
          AND explanation->'branch_scores'->>'autoencoder' IS NOT NULL
        ORDER BY novelty DESC LIMIT :n"""), {"d": days, "n": limit}).mappings().all()
    return {"threshold": threshold, "items": [dict(r) for r in rows]}
