"""Politique de décision coût-sensible : consultation, simulation, réglage versionné.

Le réglage se fait EN CONNAISSANCE DE CAUSE : le simulateur rejoue les transactions récentes avec la politique candidate
(même calcul que le scoring, shared/policy) et montre, à côté de la politique active, les actions qui changeraient,
la perte attendue (d'après les probabilités du modèle) et la perte réalisée (d'après les verdicts). Une fois
enregistrée par un superviseur, la version devient active, est publiée dans Redis et le scoring la recharge à chaud
(moins de 10 s). Chaque version garde son auteur, sa justification et l'effet simulé (audit BCC)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.events import Publisher, get_publisher
from app.security import get_current_user, require_role
from shared.database.models import BackofficeUser, DecisionPolicyVersion
from shared.policy.costs import BOUNDS, CHANNELS, OPERATORS, REDIS_KEY, CostPolicy
from shared.policy.simulate import compare

router = APIRouter(prefix="/policy", tags=["politique de décision"])
log = logging.getLogger("backoffice.policy")
MAX_ROWS = 100_000

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
    return _redis


def active_policy(db: Session) -> tuple[CostPolicy, DecisionPolicyVersion | None]:
    row = db.scalar(select(DecisionPolicyVersion).where(DecisionPolicyVersion.is_active))
    return (CostPolicy.from_dict(row.params) if row else CostPolicy()), row


def publish(policy: CostPolicy) -> bool:
    try:
        get_redis().set(REDIS_KEY, json.dumps(policy.to_dict()))
        return True
    except redis.RedisError as e:
        log.error("publication de la politique impossible : %s", e)
        return False


def sync_on_startup(db: Session) -> None:
    """Redis vidé ou redémarré : republie la version active (sinon le scoring reviendrait aux coûts par défaut)."""
    policy, row = active_policy(db)
    if row is not None:
        publish(policy)


def _rows(db: Session, days: int) -> list[dict]:
    rows = db.execute(text("""
        SELECT fraud_probability AS p, amount_usd, channel, operator, label,
               jsonb_array_length(coalesce(rules_triggered, '[]'::jsonb)) > 0 AS rule_verify
        FROM scored_transactions WHERE scored_at > now() - make_interval(days => :d)
        ORDER BY scored_at DESC LIMIT :n"""), {"d": days, "n": MAX_ROWS}).mappings().all()
    return [dict(r) for r in rows]


def _version_out(v: DecisionPolicyVersion, names: dict[int, str]) -> dict:
    return {"id": v.id, "created_at": v.created_at, "created_by": names.get(v.created_by), "note": v.note,
            "is_active": v.is_active, "params": v.params, "simulation": v.simulation}


@router.get("")
def get_policy(db: Session = Depends(get_db), _=Depends(get_current_user)):
    policy, row = active_policy(db)
    history = db.scalars(select(DecisionPolicyVersion).order_by(DecisionPolicyVersion.id.desc()).limit(15)).all()
    names = dict(db.execute(select(BackofficeUser.id, BackofficeUser.full_name)).all())
    try:
        published = get_redis().get(REDIS_KEY)
        in_sync = (json.loads(published) == policy.to_dict()) if published else row is None
    except redis.RedisError:
        in_sync = None
    return {"active": policy.to_dict(), "active_id": row.id if row else None, "defaults": CostPolicy().to_dict(),
            "bounds": BOUNDS, "channels": CHANNELS, "operators": OPERATORS, "published": in_sync,
            "history": [_version_out(v, names) for v in history]}


class PolicyIn(BaseModel):
    params: dict
    days: int = Field(7, ge=1, le=90)


@router.post("/simulate")
def simulate_policy(body: PolicyIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        candidate = CostPolicy.from_dict(body.params)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    current, _row = active_policy(db)
    rows = _rows(db, body.days)
    return {"days": body.days, "n_rows": len(rows), "truncated": len(rows) >= MAX_ROWS, **compare(rows, current, candidate)}


class PolicySave(BaseModel):
    params: dict
    note: str = Field(min_length=10, max_length=2000)


@router.put("")
def save_policy(body: PolicySave, db: Session = Depends(get_db), user: BackofficeUser = Depends(require_role("SUPERVISEUR")),
                pub: Publisher = Depends(get_publisher)):
    try:
        candidate = CostPolicy.from_dict(body.params)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    current, _row = active_policy(db)
    effect = compare(_rows(db, 7), current, candidate)
    summary = {"changed": effect["changed"], "moves": effect["moves"],
               "expected_total": [effect["current"]["expected"]["total"], effect["candidate"]["expected"]["total"]],
               "actions": [effect["current"]["actions"], effect["candidate"]["actions"]]}
    db.execute(update(DecisionPolicyVersion).where(DecisionPolicyVersion.is_active).values(is_active=False))
    v = DecisionPolicyVersion(created_by=user.id, params={}, note=body.note, is_active=True, simulation=summary)
    db.add(v)
    db.flush()
    candidate.version = f"v{v.id}"
    v.params = candidate.to_dict()
    db.commit()
    ok = publish(candidate)
    pub.audit(user.email, "POLITIQUE_DECISION_MODIFIEE", "policy", str(v.id),
              {"note": body.note, "version": candidate.version, "effet_simule_7j": summary, "publiee": ok})
    return {"id": v.id, "version": candidate.version, "published": ok, "simulation": summary}


@router.get("/evaluation")
def evaluation(_=Depends(get_current_user)):
    """Comparaison hors ligne seuil unique / politique de coût (ml/serving/evaluate_policy.py)."""
    try:
        return json.loads((Path(settings.RAG_INDEX_PATH).parent / "policy_evaluation.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "évaluation non disponible : lancer python -m ml.serving.evaluate_policy") from None


@router.get("/history/{version_id}")
def get_version(version_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    v = db.get(DecisionPolicyVersion, version_id)
    if v is None:
        raise HTTPException(404, "version introuvable")
    names = dict(db.execute(select(BackofficeUser.id, BackofficeUser.full_name)).all())
    return _version_out(v, names)


__all__ = ["router", "sync_on_startup"]
