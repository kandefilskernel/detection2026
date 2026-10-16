"""Institutions partenaires de l'API publique (ADMIN) : création, droits, renouvellement et révocation des clés.

La clé d'API n'est renvoyée qu'une fois (création ou renouvellement) : la base n'en garde que l'empreinte SHA-256.
Une clé révoquée ou renouvelée cesse de fonctionner au plus tard 30 s après (cache de la couche d'intégration).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import Publisher, get_publisher
from app.security import require_role
from shared.database.models import Institution, ScoredTransaction
from shared.utils.api_keys import DEFAULT_SCOPES, SCOPES, generate_key, hash_key, key_prefix

router = APIRouter(prefix="/institutions", tags=["institutions"])

PROVIDERS = ("vodacom", "airtel", "orange", "visa")
Kind = Literal["OPERATEUR_MM", "BANQUE", "EMETTEUR_CARTE", "REGULATEUR"]


def _check(values: list[str] | None, allowed: tuple[str, ...], what: str) -> list[str] | None:
    if values is None:
        return None
    bad = sorted(set(values) - set(allowed))
    if bad:
        raise ValueError(f"{what} inconnu(s) : {', '.join(bad)} (valeurs : {', '.join(allowed)})")
    return sorted(set(values))


class InstitutionCreate(BaseModel):
    code: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{1,31}$", description="Identifiant court, ex. rawbank, bcc")
    name: str = Field(..., min_length=2, max_length=255)
    kind: Kind
    scopes: list[str] | None = Field(None, description="Par défaut selon le type d'institution")
    providers: list[str] = Field(default_factory=list, description="Formats natifs autorisés")
    contact_email: EmailStr | None = None
    rate_limit_per_s: int | None = Field(None, ge=1, le=10_000, description="Requêtes/s ; vide = valeur par défaut")

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, v):
        return _check(v, SCOPES, "droit")

    @field_validator("providers")
    @classmethod
    def _providers(cls, v):
        return _check(v, PROVIDERS, "format")


class InstitutionUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    scopes: list[str] | None = None
    providers: list[str] | None = None
    is_active: bool | None = None
    contact_email: EmailStr | None = None
    rate_limit_per_s: int | None = Field(None, ge=1, le=10_000)

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, v):
        return _check(v, SCOPES, "droit")

    @field_validator("providers")
    @classmethod
    def _providers(cls, v):
        return _check(v, PROVIDERS, "format")


def out(i: Institution, volume: int | None = None, last_tx=None) -> dict:
    return {"id": i.id, "code": i.code, "name": i.name, "kind": i.kind, "scopes": i.scopes, "providers": i.providers,
            "key_prefix": i.key_prefix, "is_active": i.is_active, "contact_email": i.contact_email,
            "created_at": i.created_at, "key_rotated_at": i.key_rotated_at, "rate_limit_per_s": i.rate_limit_per_s,
            "volume_30d": volume, "last_transaction_at": last_tx}


@router.get("")
def list_institutions(db: Session = Depends(get_db), _=Depends(require_role("ADMIN"))):
    usage = {r.institution: (r.n, r.last) for r in db.execute(
        select(ScoredTransaction.institution, func.count().label("n"), func.max(ScoredTransaction.scored_at).label("last"))
        .where(ScoredTransaction.scored_at >= func.now() - func.make_interval(0, 0, 0, 30))
        .group_by(ScoredTransaction.institution))}
    return [out(i, *usage.get(i.code, (0, None))) for i in db.scalars(select(Institution).order_by(Institution.id))]


@router.post("", status_code=201)
def create_institution(body: InstitutionCreate, db: Session = Depends(get_db), admin=Depends(require_role("ADMIN")),
                       pub: Publisher = Depends(get_publisher)):
    if db.scalar(select(Institution.id).where(Institution.code == body.code)):
        raise HTTPException(409, "code d'institution déjà utilisé")
    if body.providers and body.kind == "REGULATEUR":
        raise HTTPException(422, "un régulateur ne soumet pas de transactions")
    key = generate_key()
    i = Institution(code=body.code, name=body.name, kind=body.kind,
                    scopes=body.scopes if body.scopes is not None else DEFAULT_SCOPES[body.kind],
                    providers=body.providers, key_prefix=key_prefix(key), key_hash=hash_key(key),
                    is_active=True, contact_email=body.contact_email, rate_limit_per_s=body.rate_limit_per_s)
    db.add(i)
    db.commit()
    pub.audit(admin.email, "INSTITUTION_CREEE", "institution", i.code,
              {"kind": i.kind, "scopes": i.scopes, "providers": i.providers})
    return {**out(i), "api_key": key, "warning": "Clé affichée une seule fois : transmettez-la par un canal sûr."}


@router.patch("/{institution_id}")
def update_institution(institution_id: int, body: InstitutionUpdate, db: Session = Depends(get_db),
                       admin=Depends(require_role("ADMIN")), pub: Publisher = Depends(get_publisher)):
    i = db.get(Institution, institution_id)
    if i is None:
        raise HTTPException(404, "institution introuvable")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(i, k, v)
    db.commit()
    pub.audit(admin.email, "INSTITUTION_MODIFIEE", "institution", i.code, changes)
    return out(i)


@router.post("/{institution_id}/rotate-key")
def rotate_key(institution_id: int, db: Session = Depends(get_db), admin=Depends(require_role("ADMIN")),
               pub: Publisher = Depends(get_publisher)):
    """Nouvelle clé (fuite suspectée, départ d'un employé, renouvellement périodique) : l'ancienne est invalidée."""
    i = db.get(Institution, institution_id)
    if i is None:
        raise HTTPException(404, "institution introuvable")
    key = generate_key()
    i.key_prefix, i.key_hash, i.key_rotated_at = key_prefix(key), hash_key(key), datetime.now(timezone.utc)
    db.commit()
    pub.audit(admin.email, "CLE_API_RENOUVELEE", "institution", i.code, {"key_prefix": i.key_prefix})
    return {**out(i), "api_key": key, "warning": "Clé affichée une seule fois. L'ancienne clé est révoquée."}
