from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security import get_current_user
from shared.database.models import ScoredTransaction
from shared.rag.retriever import CaseMemory, KnowledgeBase, build_evidence

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TxSummary(BaseModel):
    transaction_id: str
    tx_time: datetime
    scored_at: datetime
    user_id: str
    channel: str
    operator: str | None
    tx_type: str
    access_channel: str
    amount_usd: float
    province: str
    fraud_probability: float
    risk_level: str
    action: str
    reason: str
    fraud_type: str | None
    fraud_type_probability: float | None
    latency_ms: float
    label: int | None

    model_config = {"from_attributes": True}


class TxDetail(TxSummary):
    amount: float
    currency: str
    device_id: str
    counterparty_id: str | None
    agent_id: str | None
    merchant_id: str | None
    rules_triggered: list
    model_version: str
    degraded: bool
    explanation: dict
    features: dict


@router.get("")
def list_transactions(
    db: Session = Depends(get_db), _=Depends(get_current_user),
    channel: str | None = None, action: str | None = None, risk_level: str | None = None,
    fraud_type: str | None = None, operator: str | None = None, user_id: str | None = None, min_probability: float | None = None,
    labeled: bool | None = None, alerts_only: bool = False, search: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500),
):
    q = select(ScoredTransaction)
    filters = []
    if alerts_only:
        filters.append(ScoredTransaction.action != "APPROVE")
    if search:
        filters.append((ScoredTransaction.transaction_id == search) | (ScoredTransaction.user_id == search))
    if channel:
        filters.append(ScoredTransaction.channel == channel)
    if action:
        filters.append(ScoredTransaction.action == action)
    if risk_level:
        filters.append(ScoredTransaction.risk_level == risk_level)
    if fraud_type:
        filters.append(ScoredTransaction.fraud_type == fraud_type)
    if operator:
        filters.append(ScoredTransaction.operator == operator)
    if user_id:
        filters.append(ScoredTransaction.user_id == user_id)
    if min_probability is not None:
        filters.append(ScoredTransaction.fraud_probability >= min_probability)
    if labeled is not None:
        filters.append(ScoredTransaction.label.is_not(None) if labeled else ScoredTransaction.label.is_(None))
    q = q.where(*filters)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(ScoredTransaction.scored_at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size,
            "items": [TxSummary.model_validate(r).model_dump() for r in rows]}


@router.get("/{transaction_id}", response_model=TxDetail)
def get_transaction(transaction_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    tx = db.scalar(select(ScoredTransaction).where(ScoredTransaction.transaction_id == transaction_id))
    if tx is None:
        raise HTTPException(404, "transaction introuvable")
    return tx


_rag: dict = {}


def _rag_tools() -> tuple[KnowledgeBase, CaseMemory]:
    """Chargement paresseux (une fois par processus) de la base de connaissances et de la mémoire de cas."""
    if "memory" not in _rag:
        try:
            _rag["memory"] = CaseMemory(settings.RAG_INDEX_PATH)
        except (OSError, KeyError, ValueError) as e:
            raise HTTPException(503, f"mémoire de cas indisponible ({e.__class__.__name__}) : "
                                     "lancer `python -m ml.rag.case_index`")
        _rag["kb"] = KnowledgeBase()
    return _rag["kb"], _rag["memory"]


@router.get("/{transaction_id}/evidence")
def transaction_evidence(transaction_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Éléments de preuve (RAG) : cas passés les plus proches avec leur verdict, fiches de typologie
    pertinentes, et cohérence entre l'avis de ces cas et la décision du modèle."""
    tx = db.scalar(select(ScoredTransaction).where(ScoredTransaction.transaction_id == transaction_id))
    if tx is None:
        raise HTTPException(404, "transaction introuvable")
    kb, memory = _rag_tools()
    # verdicts d'analystes : la mémoire s'enrichit des dossiers clos (hors cette transaction)
    labeled = db.scalars(select(ScoredTransaction)
                         .where(ScoredTransaction.label.is_not(None), ScoredTransaction.channel == tx.channel,
                                ScoredTransaction.transaction_id != tx.transaction_id)
                         .order_by(ScoredTransaction.labeled_at.desc()).limit(settings.RAG_EXTRA_CASES)).all()
    extra = [{"id": r.transaction_id, "features": r.features, "label": r.label,
              "fraud_type": r.fraud_type if r.label == 1 else None, "channel": r.channel, "tx_type": r.tx_type,
              "amount_usd": r.amount_usd, "source": "verdict analyste"} for r in labeled if r.features]
    top = [f["feature"] for f in (tx.explanation or {}).get("top_features", [])]
    return build_evidence(kb, memory, tx.features, model_flagged=tx.risk_level in ("ELEVE", "CRITIQUE"),
                          probability=tx.fraud_probability, fraud_type=tx.fraud_type, top_features=top,
                          channel=tx.channel, extra_cases=extra)


@router.get("/by-user/{user_id}/history")
def user_history(user_id: str, db: Session = Depends(get_db), _=Depends(get_current_user),
                 limit: int = Query(30, le=200)):
    rows = db.scalars(select(ScoredTransaction).where(ScoredTransaction.user_id == user_id)
                      .order_by(ScoredTransaction.tx_time.desc()).limit(limit)).all()
    return [TxSummary.model_validate(r).model_dump() for r in rows]
