"""
Modèle par les LOIS PHYSIQUES : ce qui est physiquement ou comptablement impossible, quel que soit
le comportement du client. Il complète le modèle de données (XGBoost + LSTM + autoencodeur), qui
apprend ce qui est STATISTIQUEMENT inhabituel à partir d'exemples passés.

    modèle de données  : « cette opération ressemble à des fraudes déjà vues »
    modèle physique    : « cette opération viole une loi qui ne dépend d'aucun exemple »

Deux lois, écrites sous forme d'équations explicites avec leurs paramètres :

1. CINÉMATIQUE (déplacement). Un client ne peut pas être dans deux provinces à des heures
   incompatibles avec la vitesse de déplacement possible. Distance d = grand cercle (haversine)
   entre les chefs-lieux ; durée minimale de trajet
        t_min(d) = min( d / v_route ,  t_aéroport + d / v_avion )
   avec v_route = 80 km/h (borne généreuse pour la RDC), v_avion = 800 km/h, t_aéroport = 2 h
   (enregistrement, attente, transfert). Si le temps écoulé t < t_min, l'opération est
   physiquement impossible ; l'infériorité est mesurée par  I = t_min / t − 1  (0 = faisable).
   La province est celle transmise par l'opérateur (zone de la cellule ou de l'agent) : c'est une
   précision de l'ordre de la province, jamais de la rue.

2. CONSERVATION (bilan comptable). On ne dépense pas ce qu'on n'a pas : un débit d'un montant
   supérieur au solde est impossible (dépassement D = max(0, a − B) / a). Le « temps avant
   vidage » τ = B / Q, avec Q le débit sortant de la dernière heure, quantifie la vitesse à
   laquelle le réservoir qu'est le portefeuille se vide.

Limites assumées : les coordonnées sont celles des chefs-lieux (précision de l'ordre de la
province) ; les constantes de vitesse sont des bornes physiques, pas des mesures. Les lois
sont valides par construction, mais la fréquence des violations dans des données réelles
doit être mesurée avant de les faire agir sur les décisions (voir PHYSICS_MODE).
"""
from __future__ import annotations

import math

# Coordonnées approximatives (latitude, longitude) des chefs-lieux des provinces du jeu de données
PROVINCE_COORDS = {
    "Kinshasa": (-4.325, 15.322), "Haut-Katanga": (-11.664, 27.479), "Nord-Kivu": (-1.679, 29.222),
    "Sud-Kivu": (-2.508, 28.860), "Kongo-Central": (-5.817, 13.463), "Kasai-Oriental": (-6.150, 23.590),
    "Lualaba": (-10.717, 25.467), "Tshopo": (0.516, 25.191), "Ituri": (1.559, 30.252),
}
EARTH_RADIUS_KM = 6371.0
V_ROAD_KMH = 80.0          # vitesse routière maximale soutenue (borne généreuse)
V_AIR_KMH = 800.0          # vitesse de croisière d'un avion de ligne
AIRPORT_OVERHEAD_H = 2.0   # temps fixe pour prendre l'avion
MIN_DISTANCE_KM = 1.0

# Gravité à partir de laquelle une loi est considérée violée avec netteté (voir summarize)
SEVERE_TRAVEL = 1.0        # I >= 1 : il aurait fallu aller au moins 2 fois plus vite que la borne physique


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def min_travel_hours(distance_km: float) -> float:
    """Durée minimale physiquement possible pour parcourir distance_km (route ou avion)."""
    if distance_km < MIN_DISTANCE_KM:
        return 0.0
    return min(distance_km / V_ROAD_KMH, AIRPORT_OVERHEAD_H + distance_km / V_AIR_KMH)


def travel_law(prev_province: str | None, province: str, elapsed_s: float | None) -> dict:
    """Loi 1 : cinématique. Inconnu (aucun relevé, province hors table, horloge incohérente) = pas de violation."""
    unknown = {"km": 0.0, "required_kmh": 0.0, "infeasibility": 0.0, "known": False}
    if prev_province is None or elapsed_s is None or elapsed_s <= 0:
        return unknown
    a, b = PROVINCE_COORDS.get(prev_province), PROVINCE_COORDS.get(province)
    if a is None or b is None:
        return unknown
    km = haversine_km(a, b)
    hours = elapsed_s / 3600.0
    t_min = min_travel_hours(km)
    return {"km": round(km, 1), "required_kmh": round(km / max(hours, 1e-6), 1),
            "infeasibility": round(max(0.0, t_min / max(hours, 1e-6) - 1.0), 4), "known": True}


def balance_law(amount_usd: float, balance_usd: float, is_debit: bool, outflow_1h_usd: float) -> dict:
    """Loi 2 : conservation. Dépassement et temps avant vidage (heures) au débit de la dernière heure."""
    overdraft = max(0.0, amount_usd - balance_usd) / amount_usd if is_debit and amount_usd > 0 else 0.0
    flow = outflow_1h_usd + (amount_usd if is_debit else 0.0)           # USD par heure
    tte = balance_usd / flow if flow > 1e-6 else 1e4
    return {"overdraft": round(overdraft, 4), "time_to_empty_h": round(min(tte, 1e4), 3)}


def evaluate(prev_province: str | None, province: str, elapsed_s: float | None, amount_usd: float,
             balance_usd: float, is_debit: bool, outflow_1h_usd: float) -> dict:
    """Ensemble des lois pour une opération : valeurs `phys_*` (stockées avec les variables, hors du vecteur
    d'entrée du modèle de données) et score de violation entre 0 (plausible) et 1 (impossible)."""
    t = travel_law(prev_province, province, elapsed_s)
    b = balance_law(amount_usd, balance_usd, is_debit, outflow_1h_usd)
    travel_sev = min(1.0, math.log1p(t["infeasibility"]) / math.log1p(10.0))
    score = max(travel_sev, min(1.0, b["overdraft"]))
    return {
        "phys_travel_km": t["km"], "phys_travel_required_kmh": t["required_kmh"],
        "phys_travel_infeasibility": t["infeasibility"], "phys_overdraft": b["overdraft"],
        "phys_time_to_empty_h": b["time_to_empty_h"], "phys_score": round(score, 4),
    }


PHYSICS_FEATURES = ["phys_travel_km", "phys_travel_required_kmh", "phys_travel_infeasibility", "phys_overdraft",
                    "phys_time_to_empty_h", "phys_score"]


def summarize(phys: dict) -> dict:
    """Lecture des violations à partir des valeurs `phys_*` d'une opération (réponse de l'API, interface)."""
    violated = []
    if phys.get("phys_travel_infeasibility", 0.0) > 0:
        violated.append("CINEMATIQUE")
    if phys.get("phys_overdraft", 0.0) > 0:
        violated.append("CONSERVATION")
    severe = phys.get("phys_travel_infeasibility", 0.0) >= SEVERE_TRAVEL or phys.get("phys_overdraft", 0.0) > 0
    return {
        "score": phys.get("phys_score", 0.0), "violated": violated, "severe": bool(severe and violated),
        "travel": {"km": phys.get("phys_travel_km", 0.0), "required_kmh": phys.get("phys_travel_required_kmh", 0.0),
                   "infeasibility": phys.get("phys_travel_infeasibility", 0.0)},
        "balance": {"overdraft": phys.get("phys_overdraft", 0.0),
                    "time_to_empty_h": phys.get("phys_time_to_empty_h", 1e4)},
    }
