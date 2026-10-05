"""Mode pluriannuel du générateur : ouvertures de comptes, lancement de la carte, taux de change par année,
voyages physiquement cohérents, même structure de fichiers que le jeu d'origine."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "generator"))
from generate_synthetic_data import (  # noqa: E402
    CARD_FRAUD_MIX, MM_FRAUD_MIX, TRANSACTION_COLUMNS, GeneratorConfig, SyntheticDataGenerator,
)
from ml.physics.laws import PROVINCE_COORDS, haversine_km, min_travel_hours  # noqa: E402
from shared.utils.fx import usd_cdf_rate  # noqa: E402

CFG = GeneratorConfig(n_users=250, start_date="2019-01-01", end_date="2021-12-31", seed=3, visa_adoption_multiplier=3.0,
                      onboarding=True, activity_growth=0.08, visa_launch_date="2020-07-01", fraud_trends=True,
                      fx_by_year=True, realistic_travel=True, mm_fraud_rate=0.02, card_fraud_rate=0.04)


@pytest.fixture(scope="module")
def data():
    return SyntheticDataGenerator(CFG).run()


def test_same_structure_and_whole_period(data):
    tx = data["transactions"]
    assert list(tx.columns) == TRANSACTION_COLUMNS
    assert tx["transaction_id"].is_unique and tx["timestamp"].is_monotonic_increasing
    assert tx["timestamp"].min() >= pd.Timestamp("2019-01-01") and tx["timestamp"].max() < pd.Timestamp("2022-01-01")
    assert set(tx["timestamp"].dt.year) == {2019, 2020, 2021}
    assert set(tx["fraud_type"].dropna()) == set(MM_FRAUD_MIX) | set(CARD_FRAUD_MIX)


def test_no_card_activity_before_launch(data):
    card = data["transactions"][data["transactions"]["channel"] == "VISA_VIRTUAL"]
    assert len(card) > 0 and card["timestamp"].min() >= pd.Timestamp("2020-07-01")


def test_no_activity_before_account_opening(data):
    tx, users = data["transactions"], data["users"]
    late = users[users["account_age_days"] < 0].set_index("user_id")["account_age_days"]
    assert len(late) > 0
    first = tx[tx["user_id"].isin(late.index)].groupby("user_id")["timestamp"].min()
    opened = pd.Timestamp("2019-01-01") + pd.to_timedelta(-late.loc[first.index], unit="D")
    assert (first.to_numpy() >= opened.to_numpy()).all()


def test_activity_grows_over_time(data):
    by_year = data["transactions"].groupby(data["transactions"]["timestamp"].dt.year).size()
    assert by_year[2019] < by_year[2020] < by_year[2021]


def test_cdf_amounts_use_the_rate_of_their_year(data):
    cdf = data["transactions"][(data["transactions"]["currency"] == "CDF") & (data["transactions"]["amount_usd"] > 2)]
    for year, g in cdf.groupby(cdf["timestamp"].dt.year):
        implied = (g["amount"] / g["amount_usd"]).median()
        assert implied == pytest.approx(usd_cdf_rate(int(year)), rel=0.02)


def test_legit_travel_respects_physics(data):
    tx = data["transactions"]
    legit = tx[tx["is_fraud"] == 0].sort_values(["user_id", "timestamp"])
    prev_p = legit.groupby("user_id")["location_province"].shift()
    prev_t = legit.groupby("user_id")["timestamp"].shift()
    moved = prev_p.notna() & (prev_p != legit["location_province"])
    assert moved.sum() > 0                                     # des voyages existent
    km = np.array([haversine_km(PROVINCE_COORDS[a], PROVINCE_COORDS[b])
                   for a, b in zip(prev_p[moved], legit.loc[moved, "location_province"])])
    hours = ((legit.loc[moved, "timestamp"] - prev_t[moved]).dt.total_seconds() / 3600).to_numpy()
    needed = np.array([min_travel_hours(k) for k in km])
    # entre deux opérations légitimes successives, le temps écoulé suffit toujours au trajet
    assert (hours >= needed - 1e-6).all()


def test_fraud_rate_stays_in_a_realistic_band_every_year(data):
    tx = data["transactions"]
    rates = tx.groupby(tx["timestamp"].dt.year)["is_fraud"].mean()
    assert rates.min() > 0.003 and rates.max() < 0.08
    assert rates.max() / rates.min() < 6                      # pas de concentration sur une seule année
