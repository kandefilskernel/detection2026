"""Double authentification par code à usage unique (TOTP, RFC 6238), compatible Google Authenticator,
Microsoft Authenticator, FreeOTP… Bibliothèque standard uniquement.

Le secret est chiffré en base (Fernet) avec TOTP_ENCRYPTION_KEY, ou à défaut une clé dérivée de JWT_SECRET_KEY :
une copie de la base seule ne permet pas de générer les codes. Un code déjà utilisé est refusé (anti-rejeu)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

PERIOD_S = 30
DIGITS = 6
WINDOW = 1          # tolère ±30 s de décalage d'horloge du téléphone
ISSUER = "Fraude RDC"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD_S)


def verify(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Pas de temps du code s'il est valide et pas encore utilisé, sinon None."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for s in range(step - WINDOW, step + WINDOW + 1):
        if (last_step is None or s > last_step) and hmac.compare_digest(code_at(secret, s), code):
            return s
    return None


def provisioning_uri(secret: str, email: str) -> str:
    label = quote(f"{ISSUER}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={PERIOD_S}"


def _fernet() -> Fernet:
    raw = settings.TOTP_ENCRYPTION_KEY or hashlib.sha256(("totp:" + settings.JWT_SECRET_KEY).encode()).digest()
    key = raw if isinstance(raw, str) else base64.urlsafe_b64encode(raw).decode()
    return Fernet(key)


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
