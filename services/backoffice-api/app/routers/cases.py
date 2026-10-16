"""Gestion des dossiers : les analystes confirment ou infirment les alertes.
Chaque verdict devient une étiquette (label) qui alimente le réentraînement.

Principe des quatre yeux : déclarer « faux positif » (donc débloquer) une transaction BLOQUÉE d'au moins
FOUR_EYES_MIN_USD crée une demande de déblocage ; elle n'est appliquée qu'après validation par un second utilisateur,
superviseur ou administrateur, différent du demandeur. Une fraude débloquée par erreur coûte le montant entier."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.events import Publisher, get_publisher
from app.security import ROLE_RANK, get_current_user, require_role
from shared.database.models import BackofficeUser, Case, ScoredTransaction, UnblockRequest
from shared.nlp.analyzer import analyze

router = APIRouter(prefix="/cases", tags=["dossiers"])

FINAL = {"FRAUDE_CONFIRMEE": 1, "FAUX_POSITIF": 0}
TRANSITIONS = {"OUVERT": {"EN_COURS", *FINAL}, "EN_COURS": {"OUVERT", *FINAL}}


class CaseOut(BaseModel):
    id: int
    transaction_id: str
    tx_time: datetime
    user_id: str
    channel: str
    tx_type: str
    amount_usd: float
    fraud_probability: float
    risk_level: str
    action: str
    fraud_type: str | None
    status: str
    review_reason: str
    assigned_to: int | None
    resolution_note: str | None
    resolved_by: int | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(OUVERT|EN_COURS|FRAUDE_CONFIRMEE|FAUX_POSITIF)$")
    assigned_to: int | None = None
    resolution_note: str | None = Field(None, max_length=2000)


def needs_four_eyes(c: Case, label: int) -> bool:
    return label == 0 and c.action == "BLOCK" and c.amount_usd >= settings.FOUR_EYES_MIN_USD


def _pending(db: Session, case_id: int) -> UnblockRequest | None:
    return db.scalar(select(UnblockRequest).where(UnblockRequest.case_id == case_id,
                                                  UnblockRequest.status == "EN_ATTENTE"))


def request_unblock(db: Session, c: Case, user: BackofficeUser, note: str, pub: Publisher) -> JSONResponse:
    """Enregistre la demande (dossier « en cours ») au lieu d'appliquer le verdict : 202 Accepted."""
    if c.id is None:              # dossier créé par cette revue : il lui faut un identifiant
        db.flush()
    req = UnblockRequest(case_id=c.id, transaction_id=c.transaction_id, amount_usd=c.amount_usd,
                         requested_by=user.id, note=note)
    db.add(req)
    c.status = "EN_COURS"
    c.assigned_to = c.assigned_to or user.id
    db.commit()
    pub.audit(user.email, "DEBLOCAGE_DEMANDE", "case", str(c.id),
              {"request_id": req.id, "transaction_id": c.transaction_id, "montant_usd": c.amount_usd})
    return JSONResponse(status_code=202, content=jsonable_encoder({
        "four_eyes": True, "request": unblock_out(req, db),
        "detail": f"déblocage de {c.amount_usd:,.2f} USD : validation d'un second superviseur requise"}))


def apply_verdict(db: Session, c: Case, label: int, user: BackofficeUser, pub: Publisher) -> None:
    c.status = "FRAUDE_CONFIRMEE" if label else "FAUX_POSITIF"
    c.resolved_by, c.resolved_at = user.id, datetime.now(timezone.utc)
    db.execute(update(ScoredTransaction)
               .where(ScoredTransaction.transaction_id == c.transaction_id, ScoredTransaction.tx_time == c.tx_time)
               .values(label=label, labeled_at=c.resolved_at))
    pub.feedback(c.transaction_id, label, user.email, c.id)


def unblock_out(r: UnblockRequest, db: Session) -> dict:
    who = {u.id: u for u in db.scalars(select(BackofficeUser).where(
        BackofficeUser.id.in_([x for x in (r.requested_by, r.decided_by) if x])))}
    return {"id": r.id, "case_id": r.case_id, "transaction_id": r.transaction_id, "amount_usd": r.amount_usd,
            "status": r.status, "note": r.note, "requested_at": r.requested_at, "decided_at": r.decided_at,
            "decision_note": r.decision_note, "requested_by": r.requested_by, "decided_by": r.decided_by,
            "requested_by_name": who[r.requested_by].full_name if r.requested_by in who else None,
            "decided_by_name": who[r.decided_by].full_name if r.decided_by in who else None}


@router.get("")
def list_cases(db: Session = Depends(get_db), _=Depends(get_current_user),
               status: str | None = None, risk_level: str | None = None, fraud_type: str | None = None, assigned_to: int | None = None,
               page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    q = select(Case)
    if status:
        q = q.where(Case.status == status)
    if risk_level:
        q = q.where(Case.risk_level == risk_level)
    if fraud_type:
        q = q.where(Case.fraud_type == fraud_type)
    if assigned_to is not None:
        q = q.where(Case.assigned_to == assigned_to)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    # priorité : risque critique d'abord, puis montant
    order = func.array_position(["CRITIQUE", "ELEVE", "MOYEN", "FAIBLE"], Case.risk_level)
    rows = db.scalars(q.order_by(Case.status != "OUVERT", order, Case.amount_usd.desc())
                      .offset((page - 1) * size).limit(size)).all()
    counts = dict(db.execute(select(Case.status, func.count()).group_by(Case.status)).all())
    return {"total": total, "counts": counts, "items": [CaseOut.model_validate(r).model_dump() for r in rows]}


class Complaint(BaseModel):
    note: str = Field(min_length=5, max_length=2000)


@router.post("/complaint/{transaction_id}", response_model=CaseOut, status_code=201)
def customer_complaint(transaction_id: str, body: Complaint, db: Session = Depends(get_db),
                       user: BackofficeUser = Depends(get_current_user), pub: Publisher = Depends(get_publisher)):
    """Plainte d'un client pour une opération qu'il ne reconnaît pas. C'est la seule source
    d'étiquettes pour les fraudes que le modèle a LAISSÉ PASSER (faux négatifs) : sans elle,
    le réentraînement n'apprendrait que de ses propres alertes."""
    tx = db.scalar(select(ScoredTransaction).where(ScoredTransaction.transaction_id == transaction_id))
    if tx is None:
        raise HTTPException(404, "transaction introuvable")
    now = datetime.now(timezone.utc)
    c = db.scalar(select(Case).where(Case.transaction_id == transaction_id))
    if c is None:
        c = Case(transaction_id=tx.transaction_id, tx_time=tx.tx_time, user_id=tx.user_id, channel=tx.channel,
                 tx_type=tx.tx_type, amount_usd=tx.amount_usd, fraud_probability=tx.fraud_probability,
                 risk_level=tx.risk_level, action=tx.action, fraud_type=tx.fraud_type)
        db.add(c)
    elif c.status in FINAL:
        raise HTTPException(409, "dossier déjà clos")
    nlp = analyze(body.note)
    se = nlp["social_engineering"]
    # une plainte qui décrit une manipulation renseigne la typologie des fraudes que le modèle n'avait pas signalées
    from_text = tx.fraud_type is None and se["level"] == "ELEVE"
    if from_text:
        tx.fraud_type = c.fraud_type = "SOCIAL_ENGINEERING"
    c.status, c.resolution_note = "FRAUDE_CONFIRMEE", f"Plainte client : {body.note}"
    if tx.action == "APPROVE":          # fraude laissée passer : sinon le dossier reste celui de l'alerte
        c.review_reason = "PLAINTE"
    c.resolved_by, c.resolved_at, c.assigned_to = user.id, now, c.assigned_to or user.id
    tx.label, tx.labeled_at = 1, now
    db.commit()
    pub.feedback(tx.transaction_id, 1, user.email, c.id)
    pub.audit(user.email, "PLAINTE_CLIENT", "transaction", tx.transaction_id,
              {"case_id": c.id, "decision_modele": tx.action,
               "sentiment_plainte": nlp["sentiment"]["label"], "emotions": nlp["sentiment"]["emotions"],
               "indices_ingenierie_sociale": [x["category"] for x in se["cues"]],
               "score_ingenierie_sociale": se["score"], "type_deduit_de_la_plainte": from_text})
    return c


REVIEW_REASONS = ("REVUE", "INCERTITUDE", "NOUVEAUTE", "RESEAU", "TEMOIN")


class Review(BaseModel):
    verdict: str = Field(pattern="^(FRAUDE|LEGITIME)$")
    note: str = Field(min_length=5, max_length=2000)
    # cas proposé par la file de revue (GET /feedback/queue) : sa source est conservée pour mesurer son apport
    reason: str = Field("REVUE", pattern=f"^({'|'.join(REVIEW_REASONS)})$")


@router.post("/review/{transaction_id}", response_model=CaseOut, status_code=201)
def review_transaction(transaction_id: str, body: Review, db: Session = Depends(get_db),
                       user: BackofficeUser = Depends(get_current_user), pub: Publisher = Depends(get_publisher)):
    """Revue d'une transaction par un analyste (par exemple un comportement nouveau signalé par la détection de
    nouveauté), alerte ou non. Le verdict devient une étiquette pour le prochain réentraînement."""
    tx = db.scalar(select(ScoredTransaction).where(ScoredTransaction.transaction_id == transaction_id))
    if tx is None:
        raise HTTPException(404, "transaction introuvable")
    if tx.label is not None:
        raise HTTPException(409, "transaction déjà étiquetée")
    now = datetime.now(timezone.utc)
    c = db.scalar(select(Case).where(Case.transaction_id == transaction_id))
    if c is None:
        c = Case(transaction_id=tx.transaction_id, tx_time=tx.tx_time, user_id=tx.user_id, channel=tx.channel,
                 tx_type=tx.tx_type, amount_usd=tx.amount_usd, fraud_probability=tx.fraud_probability,
                 risk_level=tx.risk_level, action=tx.action, fraud_type=tx.fraud_type,
                 # transaction approuvée : le dossier naît de la revue (motif choisi), pas d'une alerte
                 review_reason=body.reason if tx.action == "APPROVE" else "ALERTE")
        db.add(c)
    elif c.status in FINAL:
        raise HTTPException(409, "dossier déjà clos")
    fraud = body.verdict == "FRAUDE"
    if c.id is not None and _pending(db, c.id):
        raise HTTPException(409, "un déblocage de ce dossier attend déjà sa validation")
    if not fraud and needs_four_eyes(c, 0):
        c.resolution_note = f"Revue d'analyste : {body.note}"
        return request_unblock(db, c, user, body.note, pub)
    c.status = "FRAUDE_CONFIRMEE" if fraud else "FAUX_POSITIF"
    c.resolution_note = f"Revue d'analyste : {body.note}"
    c.resolved_by, c.resolved_at, c.assigned_to = user.id, now, c.assigned_to or user.id
    tx.label, tx.labeled_at = int(fraud), now
    db.commit()
    pub.feedback(tx.transaction_id, int(fraud), user.email, c.id)
    pub.audit(user.email, "REVUE_ANALYSTE", "transaction", tx.transaction_id,
              {"case_id": c.id, "verdict": body.verdict, "decision_modele": tx.action, "motif": c.review_reason})
    return c


@router.get("/unblock-requests")
def list_unblock_requests(status: str | None = Query("EN_ATTENTE", pattern="^(EN_ATTENTE|APPROUVEE|REJETEE)$"),
                          limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                          user: BackofficeUser = Depends(get_current_user)):
    q = select(UnblockRequest).order_by(UnblockRequest.requested_at.desc()).limit(limit)
    if status:
        q = q.where(UnblockRequest.status == status)
    rows = db.scalars(q).all()
    return {"min_amount_usd": settings.FOUR_EYES_MIN_USD,
            "can_decide": ROLE_RANK[user.role] >= ROLE_RANK["SUPERVISEUR"],
            "items": [unblock_out(r, db) for r in rows]}


class UnblockDecision(BaseModel):
    approve: bool
    note: str = Field(min_length=5, max_length=2000)


@router.post("/unblock-requests/{request_id}/decision")
def decide_unblock(request_id: int, body: UnblockDecision, db: Session = Depends(get_db),
                   user: BackofficeUser = Depends(require_role("SUPERVISEUR")), pub: Publisher = Depends(get_publisher)):
    r = db.get(UnblockRequest, request_id, with_for_update=True)
    if r is None:
        raise HTTPException(404, "demande introuvable")
    if r.status != "EN_ATTENTE":
        raise HTTPException(409, "demande déjà traitée")
    if r.requested_by == user.id:
        raise HTTPException(403, "quatre yeux : la demande doit être validée par un autre utilisateur")
    c = db.get(Case, r.case_id, with_for_update=True)
    r.status = "APPROUVEE" if body.approve else "REJETEE"
    r.decided_by, r.decided_at, r.decision_note = user.id, datetime.now(timezone.utc), body.note
    if body.approve:
        apply_verdict(db, c, 0, user, pub)
        c.resolution_note = f"{c.resolution_note or ''}\nDéblocage validé par {user.full_name} : {body.note}".strip()
    db.commit()
    pub.audit(user.email, "DEBLOCAGE_VALIDE" if body.approve else "DEBLOCAGE_REFUSE", "case", str(c.id),
              {"request_id": r.id, "demandeur": r.requested_by, "transaction_id": r.transaction_id,
               "montant_usd": r.amount_usd})
    return unblock_out(r, db)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "dossier introuvable")
    return c


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(case_id: int, body: CaseUpdate, db: Session = Depends(get_db),
                user: BackofficeUser = Depends(get_current_user), pub: Publisher = Depends(get_publisher)):
    c = db.get(Case, case_id, with_for_update=True)
    if c is None:
        raise HTTPException(404, "dossier introuvable")
    changes: dict = {}

    if body.assigned_to is not None and body.assigned_to != c.assigned_to:
        # un analyste peut se l'attribuer ; réaffecter à autrui demande SUPERVISEUR
        if body.assigned_to != user.id and ROLE_RANK[user.role] < ROLE_RANK["SUPERVISEUR"]:
            raise HTTPException(403, "réaffectation réservée aux superviseurs")
        if db.get(BackofficeUser, body.assigned_to) is None:
            raise HTTPException(422, "utilisateur inconnu")
        changes["assigned_to"] = [c.assigned_to, body.assigned_to]
        c.assigned_to = body.assigned_to

    if body.status and body.status != c.status:
        if body.status not in TRANSITIONS.get(c.status, set()):
            raise HTTPException(409, f"transition {c.status} -> {body.status} interdite")
        if body.status in FINAL and not (body.resolution_note or c.resolution_note):
            raise HTTPException(422, "une note de résolution est obligatoire")
        if _pending(db, c.id):
            raise HTTPException(409, "un déblocage de ce dossier attend sa validation par un second superviseur")
        if body.status in FINAL and needs_four_eyes(c, FINAL[body.status]):
            if body.resolution_note is not None:
                c.resolution_note = body.resolution_note
            return request_unblock(db, c, user, body.resolution_note or c.resolution_note, pub)
        changes["status"] = [c.status, body.status]
        if body.status in FINAL:
            apply_verdict(db, c, FINAL[body.status], user, pub)
        else:
            c.status = body.status
            if c.assigned_to is None:
                c.assigned_to = user.id

    if body.resolution_note is not None:
        c.resolution_note = body.resolution_note
        changes["resolution_note"] = True

    db.commit()
    if changes:
        pub.audit(user.email, "DOSSIER_MODIFIE", "case", str(c.id), changes)
    return c
