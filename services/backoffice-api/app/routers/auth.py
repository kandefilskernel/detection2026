from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import totp
from app.config import settings
from app.db import get_db
from app.events import Publisher, get_publisher
from app.security import (ROLES, create_access_token, get_current_user_setup, hash_password, require_role,
                          two_factor_required, verify_password)
from shared.database.models import BackofficeUser

router = APIRouter(tags=["authentification & utilisateurs"])


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    totp_enabled: bool = False
    locked_until: datetime | None = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2)
    role: str = Field(pattern="^(ANALYSTE|SUPERVISEUR|ADMIN)$")
    password: str = Field(min_length=10)


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = Field(None, pattern="^(ANALYSTE|SUPERVISEUR|ADMIN)$")
    is_active: bool | None = None
    password: str | None = Field(None, min_length=10)
    reset_totp: bool | None = None      # téléphone perdu : l'utilisateur reconfigure sa 2FA à la connexion suivante
    unlock: bool | None = None          # lève un verrouillage après échecs de connexion


def _session(user: BackofficeUser, mfa: bool) -> dict:
    return {"access_token": create_access_token(user, mfa=mfa), "token_type": "bearer",
            "user": UserOut.model_validate(user).model_dump(),
            "two_factor_setup_required": two_factor_required(user) and not user.totp_enabled}


def _record_failure(db: Session, user: BackofficeUser, pub: Publisher, now: datetime) -> None:
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= settings.MAX_FAILED_LOGINS:
        user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
        user.failed_logins = 0
        pub.audit(user.email, "COMPTE_VERROUILLE", "bo_user", str(user.id),
                  {"minutes": settings.LOCKOUT_MINUTES, "echecs": settings.MAX_FAILED_LOGINS})
    db.commit()


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), otp: str | None = Form(None),
          db: Session = Depends(get_db), pub: Publisher = Depends(get_publisher)):
    """Mot de passe, puis code TOTP si la double authentification est activée (champ « otp »). Après
    MAX_FAILED_LOGINS échecs consécutifs (mot de passe ou code), le compte est verrouillé LOCKOUT_MINUTES minutes."""
    now = datetime.now(timezone.utc)
    user = db.scalar(select(BackofficeUser).where(BackofficeUser.email == form.username.lower()))
    if user is not None and user.locked_until and user.locked_until > now:
        pub.audit(user.email, "LOGIN_VERROUILLE", "bo_user", str(user.id), {})
        wait = int((user.locked_until - now).total_seconds()) + 1
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"compte verrouillé après trop d'échecs : réessayer dans {wait // 60 + 1} min",
                            headers={"Retry-After": str(wait)})
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        if user is not None and user.is_active:
            _record_failure(db, user, pub, now)
        pub.audit(form.username, "LOGIN_ECHEC", "bo_user", None, {})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "identifiants invalides")
    mfa = False
    if user.totp_enabled:
        if not otp:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "TOTP_REQUIRED")
        step = totp.verify(totp.decrypt(user.totp_secret or "") or "", otp, user.totp_last_step)
        if step is None:
            _record_failure(db, user, pub, now)
            pub.audit(user.email, "LOGIN_ECHEC_2FA", "bo_user", str(user.id), {})
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "code de double authentification invalide")
        user.totp_last_step, mfa = step, True
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    pub.audit(user.email, "LOGIN", "bo_user", str(user.id), {"double_authentification": mfa})
    return _session(user, mfa)


@router.get("/auth/me")
def me(user: BackofficeUser = Depends(get_current_user_setup)):
    return {**UserOut.model_validate(user).model_dump(),
            "two_factor_required": two_factor_required(user),
            "two_factor_setup_required": two_factor_required(user) and not user.totp_enabled}


class TotpCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/auth/2fa/setup")
def totp_setup(db: Session = Depends(get_db), user: BackofficeUser = Depends(get_current_user_setup)):
    """Nouveau secret (pas encore actif) : à saisir dans l'application d'authentification, puis confirmer."""
    if user.totp_enabled:
        raise HTTPException(409, "double authentification déjà activée")
    secret = totp.new_secret()
    user.totp_secret, user.totp_last_step = totp.encrypt(secret), None
    db.commit()
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.email),
            "issuer": totp.ISSUER, "digits": totp.DIGITS, "period": totp.PERIOD_S}


@router.post("/auth/2fa/enable")
def totp_enable(body: TotpCode, db: Session = Depends(get_db), user: BackofficeUser = Depends(get_current_user_setup),
                pub: Publisher = Depends(get_publisher)):
    """Active la 2FA si le code de l'application est juste ; renvoie une session confirmée par code."""
    if user.totp_enabled:
        raise HTTPException(409, "double authentification déjà activée")
    secret = totp.decrypt(user.totp_secret or "")
    if not secret:
        raise HTTPException(409, "lancer d'abord la configuration (POST /auth/2fa/setup)")
    step = totp.verify(secret, body.code, None)
    if step is None:
        raise HTTPException(422, "code invalide : vérifier l'heure du téléphone et la clé saisie")
    user.totp_enabled, user.totp_last_step = True, step
    db.commit()
    pub.audit(user.email, "2FA_ACTIVEE", "bo_user", str(user.id), {})
    return _session(user, mfa=True)


@router.post("/auth/2fa/disable")
def totp_disable(body: TotpCode, db: Session = Depends(get_db), user: BackofficeUser = Depends(get_current_user_setup),
                 pub: Publisher = Depends(get_publisher)):
    if not user.totp_enabled:
        raise HTTPException(409, "double authentification non activée")
    if two_factor_required(user):
        raise HTTPException(403, f"double authentification obligatoire pour le rôle {user.role}")
    if totp.verify(totp.decrypt(user.totp_secret or "") or "", body.code, user.totp_last_step) is None:
        raise HTTPException(422, "code invalide")
    user.totp_enabled, user.totp_secret, user.totp_last_step = False, None, None
    db.commit()
    pub.audit(user.email, "2FA_DESACTIVEE", "bo_user", str(user.id), {})
    return _session(user, mfa=False)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_role("SUPERVISEUR"))):
    return db.scalars(select(BackofficeUser).order_by(BackofficeUser.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin=Depends(require_role("ADMIN")),
                pub: Publisher = Depends(get_publisher)):
    if db.scalar(select(BackofficeUser).where(BackofficeUser.email == body.email.lower())):
        raise HTTPException(409, "e-mail déjà utilisé")
    u = BackofficeUser(email=body.email.lower(), full_name=body.full_name, role=body.role,
                       password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    pub.audit(admin.email, "UTILISATEUR_CREE", "bo_user", str(u.id), {"email": u.email, "role": u.role})
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                admin=Depends(require_role("ADMIN")), pub: Publisher = Depends(get_publisher)):
    u = db.get(BackofficeUser, user_id)
    if u is None:
        raise HTTPException(404, "utilisateur introuvable")
    changes = body.model_dump(exclude_none=True)
    if changes.pop("reset_totp", False):
        u.totp_enabled, u.totp_secret, u.totp_last_step = False, None, None
        changes["double_authentification"] = "réinitialisée"
    if changes.pop("unlock", False):
        u.failed_logins, u.locked_until = 0, None
        changes["verrouillage"] = "levé"
    if "password" in changes:
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "modifié"
    for k, v in changes.items():
        if k in ("full_name", "role", "is_active"):
            setattr(u, k, v)
    db.commit()
    pub.audit(admin.email, "UTILISATEUR_MODIFIE", "bo_user", str(u.id), changes)
    return u


def ensure_bootstrap_admin(db: Session, email: str, password: str) -> None:
    if db.scalar(select(BackofficeUser.id).limit(1)) is None:
        db.add(BackofficeUser(email=email.lower(), full_name="Administrateur", role="ADMIN",
                              password_hash=hash_password(password)))
        try:
            db.commit()
        except IntegrityError:   # plusieurs workers uvicorn démarrent en même temps
            db.rollback()


__all__ = ["router", "ensure_bootstrap_admin", "ROLES"]
