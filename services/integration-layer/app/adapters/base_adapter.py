"""
Patron Adapter : chaque opérateur envoie son format propriétaire ; son adaptateur le
convertit vers le schéma pivot UnifiedTransaction. Ajouter un opérateur = écrire un
adaptateur, sans toucher au scoring ni au modèle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from shared.schemas.unified_transaction import UnifiedTransaction
from shared.utils.fx import usd_cdf_rate

# Taux de change de référence (à alimenter en production par le cours BCC du jour). Par défaut, le taux de l'ANNÉE de
# l'opération (shared/utils/fx.py) : une opération de 2019 rejouée est convertie au taux de 2019, comme dans les données.
DEFAULT_USD_CDF_RATE = None


class AdapterError(ValueError):
    """Message opérateur invalide ou incomplet."""


class BaseAdapter(ABC):
    provider: str = ""

    def __init__(self, usd_cdf_rate: float | None = DEFAULT_USD_CDF_RATE):
        self.rate = usd_cdf_rate          # None : taux de l'année de l'opération ; sinon taux fixe imposé

    def to_usd(self, amount: float, currency: str, when: datetime | None = None) -> float:
        currency = currency.upper()
        if currency == "USD":
            return round(float(amount), 2)
        if currency == "CDF":
            return round(float(amount) / (self.rate or usd_cdf_rate(when)), 2)
        raise AdapterError(f"devise non prise en charge : {currency}")

    @staticmethod
    def parse_time(value: str, fmt: str | None = None) -> datetime:
        try:
            return datetime.strptime(value, fmt) if fmt else datetime.fromisoformat(value)
        except (TypeError, ValueError) as e:
            raise AdapterError(f"horodatage invalide : {value!r}") from e

    MEMO_KEYS = ("memo", "Remarks", "narration", "description", "reference_text")

    @classmethod
    def memo(cls, payload: dict) -> str | None:
        """Texte libre du transfert (motif / référence), si l'opérateur le transmet : analysé par le NLP.
        Le nom du champ varie selon l'opérateur ; à confirmer avec chacun lors de l'intégration."""
        for k in cls.MEMO_KEYS:
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()[:500]
        return None

    @staticmethod
    def require(payload: dict, *keys: str):
        missing = [k for k in keys if payload.get(k) in (None, "")]
        if missing:
            raise AdapterError(f"champs obligatoires manquants : {', '.join(missing)}")

    @abstractmethod
    def to_unified(self, payload: dict) -> UnifiedTransaction:
        ...

    @abstractmethod
    def from_unified(self, tx: dict) -> dict:
        """Opération inverse (format opérateur) : utilisée par le simulateur de démo."""
