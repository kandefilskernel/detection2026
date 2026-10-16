"""Clés d'API des institutions partenaires.

La clé n'est montrée qu'une fois (création ou renouvellement) ; la base ne garde que son empreinte SHA-256 et un
préfixe lisible pour l'identifier dans l'interface. Une clé de 256 bits aléatoires rend inutile un hachage lent
(bcrypt) : il n'y a pas de dictionnaire à protéger, et la vérification reste en temps constant et rapide.
"""
from __future__ import annotations

import hashlib
import secrets

PREFIX = "nuru_"
SCOPES = ("transactions", "feedback", "supervision")
KINDS = ("OPERATEUR_MM", "BANQUE", "EMETTEUR_CARTE", "REGULATEUR")
# droits par défaut : un régulateur supervise, il ne soumet pas de transactions
DEFAULT_SCOPES = {"OPERATEUR_MM": ["transactions", "feedback"], "BANQUE": ["transactions", "feedback"],
                  "EMETTEUR_CARTE": ["transactions", "feedback"], "REGULATEUR": ["supervision"]}


def generate_key() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def key_prefix(key: str) -> str:
    return key[: len(PREFIX) + 6]
