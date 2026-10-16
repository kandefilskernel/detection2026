"""Authentification JWT et contrôle d'accès par rôle (RBAC).

    ANALYSTE     consulte les transactions, traite les dossiers
    SUPERVISEUR  + rapports, réaffectation des dossiers, journal d'audit
    ADMIN        + gestion des utilisateurs

Double authentification (TOTP) : obligatoire pour les rôles de REQUIRE_2FA_ROLES. Tant qu'un tel utilisateur ne l'a
pas activée, toutes les routes lui répondent 403 « 2FA_SETUP_REQUIRED », sauf /auth/me et /auth/2fa/* (dépendance
get_current_user_setup). Le jeton indique si la connexion a été confirmée par un code (« mfa »).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from shared.database.models import BackofficeUser

ROLES = ("ANALYSTE", "SUPERVISEUR", "ADMIN")
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: BackofficeUser, mfa: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "email": user.email, "role": user.role, "mfa": mfa, "exp": exp},
                      settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def two_factor_required(user: BackofficeUser) -> bool:
    return user.role in {r.strip() for r in settings.REQUIRE_2FA_ROLES.split(",") if r.strip()}


def _authenticate(token: str, db: Session) -> tuple[BackofficeUser, dict]:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "authentification requise",
                                 headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(BackofficeUser, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    # 2FA activée après l'émission du jeton : la session doit être rouverte avec un code
    if user.totp_enabled and not payload.get("mfa"):
        raise unauthorized
    return user, payload


def get_current_user_setup(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> BackofficeUser:
    """Utilisateur authentifié, même sans 2FA encore configurée (profil, configuration de la 2FA)."""
    return _authenticate(token, db)[0]


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> BackofficeUser:
    user, _ = _authenticate(token, db)
    if two_factor_required(user) and not user.totp_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "2FA_SETUP_REQUIRED")
    return user


def require_role(minimum: str):
    def checker(user: BackofficeUser = Depends(get_current_user)) -> BackofficeUser:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"rôle {minimum} requis")
        return user
    return checker
