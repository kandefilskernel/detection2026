"""
Taux de change USD -> CDF par année, partagé par le générateur de données et les adaptateurs opérateurs
(un montant en francs congolais doit être converti au taux de SON époque, sinon un rejeu d'opérations de 2019
au taux de 2025 fausserait les montants en USD et donc les variables du modèle).

Valeurs APPROXIMATIVES (moyennes annuelles arrondies du franc congolais, ordre de grandeur du marché) : ce sont
des paramètres de simulation, à remplacer en production par le cours officiel BCC du jour.
"""
from __future__ import annotations

from datetime import datetime

USD_CDF_BY_YEAR = {2019: 1650.0, 2020: 1850.0, 2021: 1990.0, 2022: 2010.0, 2023: 2450.0, 2024: 2800.0, 2025: 2850.0}
DEFAULT_RATE = 2850.0


def usd_cdf_rate(when: datetime | int | None = None) -> float:
    """Taux pour une date (ou une année). Hors table : année la plus proche ; sans date : taux par défaut."""
    if when is None:
        return DEFAULT_RATE
    year = when if isinstance(when, int) else when.year
    years = sorted(USD_CDF_BY_YEAR)
    return USD_CDF_BY_YEAR[min(max(year, years[0]), years[-1])]
