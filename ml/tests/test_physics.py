import pytest

from ml.physics.laws import (PROVINCE_COORDS, balance_law, evaluate, haversine_km, min_travel_hours, summarize,
                             travel_law)


def test_haversine_matches_known_distances():
    d = haversine_km(PROVINCE_COORDS["Kinshasa"], PROVINCE_COORDS["Haut-Katanga"])
    assert 1500 < d < 1650                       # Kinshasa - Lubumbashi, environ 1 570 km à vol d'oiseau
    assert haversine_km(PROVINCE_COORDS["Kinshasa"], PROVINCE_COORDS["Kinshasa"]) == 0


def test_min_travel_time_uses_the_fastest_possible_means():
    assert min_travel_hours(0.5) == 0.0
    assert min_travel_hours(40) == pytest.approx(0.5)               # 40 km : route à 80 km/h
    assert min_travel_hours(1570) == pytest.approx(2 + 1570 / 800)   # longue distance : avion + 2 h de formalités


def test_travel_law_flags_teleportation_but_not_a_realistic_trip():
    kin, kat = "Kinshasa", "Haut-Katanga"
    assert travel_law(kin, kat, 2 * 60)["infeasibility"] > 10          # 2 minutes pour 1 570 km
    assert travel_law(kin, kat, 6 * 3600)["infeasibility"] == 0         # 6 h : un vol est possible
    assert travel_law(kin, kin, 30)["infeasibility"] == 0               # même province
    for unknown in (travel_law(None, kat, 60), travel_law(kin, kat, None), travel_law(kin, kat, -5),
                    travel_law(kin, "Atlantide", 60)):
        assert unknown["infeasibility"] == 0 and not unknown["known"]    # inconnu n'est jamais une violation


def test_balance_law_conservation_and_time_to_empty():
    b = balance_law(120.0, 100.0, True, 0.0)
    assert b["overdraft"] == pytest.approx(20 / 120, abs=1e-3)
    assert balance_law(50.0, 100.0, True, 0.0)["overdraft"] == 0
    assert balance_law(120.0, 100.0, False, 0.0)["overdraft"] == 0       # un crédit ne peut pas dépasser le solde
    assert balance_law(50.0, 100.0, True, 50.0)["time_to_empty_h"] == pytest.approx(1.0)   # 100 USD à 100 USD/h
    assert balance_law(0.0, 100.0, False, 0.0)["time_to_empty_h"] == 1e4


def test_evaluate_and_summarize_roundtrip():
    ok = evaluate("Kinshasa", "Kinshasa", 600, 10.0, 100.0, True, 0.0)
    assert ok["phys_score"] == 0 and summarize(ok)["violated"] == []
    bad = evaluate("Kinshasa", "Ituri", 120, 10.0, 100.0, True, 0.0)
    s = summarize(bad)
    assert s["violated"] == ["CINEMATIQUE"] and s["severe"] and bad["phys_score"] > 0.9
    mild = evaluate("Kinshasa", "Kongo-Central", 7200, 10.0, 100.0, True, 0.0)    # Matadi (~270 km) en 2 h : juste en dessous de la borne
    assert summarize(mild)["violated"] == ["CINEMATIQUE"] and not summarize(mild)["severe"]
