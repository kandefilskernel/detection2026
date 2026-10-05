"""Tests de l'API /v1/score avec le vrai modèle et un Redis simulé (fakeredis)."""
import json
import os
import sys
from pathlib import Path

import fakeredis
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "scoring-service")]
os.environ.update(KAFKA_ENABLED="false", ARTIFACTS_DIR=str(ROOT / "ml" / "artifacts"),
                  SCORING_API_KEYS="test-key")

import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FAKE = fakeredis.FakeRedis()
FAKE.set("fs:meta", json.dumps({"period_start": "2025-06-01"}))
FAKE.set("fs:profile:U1", json.dumps({"province": "Kinshasa", "kyc_level": 2, "kyc_tx_limit_usd": 500.0,
                                      "account_age_days": 400, "monthly_income_usd": 300.0,
                                      "has_visa_virtual": 0}))


@pytest.fixture(scope="module")
def client():
    redis.Redis.from_url = classmethod(lambda cls, *a, **k: FAKE)
    from app.main import app
    with TestClient(app) as c:
        yield c


def tx(i, **kw):
    return {"transaction_id": f"T{i}", "timestamp": f"2025-11-01T10:{i:02d}:00", "user_id": "U1",
            "channel": "MOBILE_MONEY", "operator": "VODACOM", "tx_type": "P2P_SEND", "access_channel": "APP",
            "amount": 12.0, "currency": "USD", "amount_usd": 12.0, "balance_before_usd": 150.0,
            "counterparty_id": "243820000001", "device_id": "DEV1", "device_type": "smartphone",
            "ip_country": "CD", "location_province": "Kinshasa", **kw}


def test_requires_api_key(client):
    assert client.post("/v1/score", json=tx(0)).status_code == 422
    assert client.post("/v1/score", json=tx(0), headers={"X-API-Key": "mauvaise"}).status_code == 401


def test_score_returns_decision_and_explanation(client):
    r = client.post("/v1/score", json=tx(1), headers={"X-API-Key": "test-key"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert 0.0 <= d["fraud_probability"] <= 1.0
    assert d["action"] in ("APPROVE", "VERIFY", "BLOCK")
    assert set(d["explanation"]["branch_scores"]) == {"xgboost", "lstm_attention", "autoencoder"}
    assert len(d["features"]) == 58 and d["known_user"] is True


def test_profile_is_updated_between_calls(client):
    h = {"X-API-Key": "test-key"}
    first = client.post("/v1/score", json=tx(2, device_id="NEWDEV"), headers=h).json()
    second = client.post("/v1/score", json=tx(3, device_id="NEWDEV"), headers=h).json()
    assert first["features"]["is_new_device"] == 1.0
    assert second["features"]["is_new_device"] == 0.0
    assert second["features"]["tx_count_1h"] > first["features"]["tx_count_1h"]


def test_account_drain_from_new_device_is_not_approved(client):
    h = {"X-API-Key": "test-key"}
    client.post("/v1/score", json=tx(4), headers=h)
    d = client.post("/v1/score", json=tx(5, tx_type="CASH_OUT", access_channel="AGENT", agent_id="A9",
                                         device_id="INCONNU", amount=148.0, amount_usd=148.0,
                                         counterparty_id=None, location_province="Lualaba",
                                         timestamp="2025-11-01T03:10:00"), headers=h).json()
    assert d["action"] != "APPROVE"
    # une transaction signalée porte une typologie valide pour son canal
    assert d["fraud_type"] in {"SIM_SWAP", "SOCIAL_ENGINEERING", "ACCOUNT_TAKEOVER", "AGENT_FRAUD", "SMURFING"}
    cands = d["fraud_type_candidates"]
    assert cands[0]["type"] == d["fraud_type"] and 0 < d["fraud_type_probability"] <= 1
    assert sum(c["probability"] for c in cands) <= 1.0001


def test_approved_transaction_has_no_fraud_type(client):
    d = client.post("/v1/score", json=tx(6), headers={"X-API-Key": "test-key"}).json()
    if d["action"] == "APPROVE" and not d["is_fraud_predicted"]:
        assert d["fraud_type"] is None and d["fraud_type_candidates"] == []


def test_scam_memo_forces_verification_and_sets_the_type(client):
    h = {"X-API-Key": "test-key"}
    memo = "Je suis du service client Vodacom, votre compte sera bloque. Envoyez-moi votre code PIN"
    d = client.post("/v1/score", json=tx(7, memo=memo), headers=h).json()
    assert "TEXTE_INGENIERIE_SOCIALE" in d["rules_triggered"] and d["action"] != "APPROVE"
    assert d["text_analysis"]["social_engineering"]["level"] == "ELEVE"
    assert d["fraud_type"] == "SOCIAL_ENGINEERING" and d["fraud_type_source"] == "texte"
    benign = client.post("/v1/score", json=tx(8, memo="loyer de novembre merci"), headers=h).json()
    assert "TEXTE_INGENIERIE_SOCIALE" not in benign["rules_triggered"]
    assert benign["text_analysis"]["social_engineering"]["level"] == "FAIBLE"
    assert client.post("/v1/score", json=tx(9), headers=h).json()["text_analysis"] is None


def test_physics_travel_law_is_reported_in_shadow_and_enforced_on_demand(client):
    from app.config import settings
    h = {"X-API-Key": "test-key"}
    assert settings.PHYSICS_MODE == "enforce"                                          # réglage par défaut
    settings.PHYSICS_MODE = "shadow"
    client.post("/v1/score", json=tx(30), headers=h)                                   # Kinshasa, 10:30
    far = client.post("/v1/score", json=tx(31, location_province="Ituri",             # Ituri 2 min plus tard
                                           timestamp="2025-11-01T10:32:00"), headers=h).json()
    assert far["physics"]["mode"] == "shadow" and "CINEMATIQUE" in far["physics"]["violated"]
    assert far["physics"]["severe"] and far["physics"]["travel"]["km"] > 1500
    assert "LOI_PHYSIQUE_CINEMATIQUE" not in far["rules_triggered"]                    # shadow : aucun effet
    settings.PHYSICS_MODE = "enforce"
    try:
        client.post("/v1/score", json=tx(32), headers=h)                              # retour à Kinshasa (déjà impossible)
        e = client.post("/v1/score", json=tx(33, location_province="Haut-Katanga",
                                             timestamp="2025-11-01T10:34:00"), headers=h).json()
        assert "LOI_PHYSIQUE_CINEMATIQUE" in e["rules_triggered"] and e["action"] != "APPROVE"
    finally:
        settings.PHYSICS_MODE = "enforce"
    ok = client.post("/v1/score", json=tx(34, timestamp="2025-11-01T10:40:00"), headers=h).json()
    assert ok["physics"]["violated"] in ([], ["CINEMATIQUE"])                         # même province : aucune violation neuve
    settings.PHYSICS_MODE = "off"
    try:
        assert client.post("/v1/score", json=tx(35), headers=h).json()["physics"] is None
    finally:
        settings.PHYSICS_MODE = "enforce"


def test_duplicate_transaction_returns_the_original_decision_without_touching_the_profile(client):
    h = {"X-API-Key": "test-key"}
    first = client.post("/v1/score", json=tx(40, user_id="U-DUP", timestamp="2025-11-02T09:00:00"), headers=h).json()
    assert first["duplicate"] is False
    # la même transaction relancée trois fois (délai dépassé côté opérateur) : même décision, profil intact
    for _ in range(3):
        again = client.post("/v1/score", json=tx(40, user_id="U-DUP", timestamp="2025-11-02T09:00:00"), headers=h).json()
        assert again["duplicate"] is True and again["action"] == first["action"]
        assert again["fraud_probability"] == first["fraud_probability"] and again["features"] == first["features"]
    nxt = client.post("/v1/score", json=tx(41, user_id="U-DUP", timestamp="2025-11-02T09:05:00"), headers=h).json()
    assert nxt["duplicate"] is False
    assert nxt["features"]["tx_count_1h"] == 1.0          # une seule opération précédente : les relances n'ont rien gonflé
    # le même identifiant pour un AUTRE client n'est pas confondu avec la première transaction
    other = client.post("/v1/score", json=tx(40, user_id="U-AUTRE", timestamp="2025-11-02T09:00:00"), headers=h).json()
    assert other["duplicate"] is False


def test_sanity_check_accepts_the_deployed_model_and_refuses_broken_ones(client):
    from types import SimpleNamespace

    from app import main
    assert main.sanity_check(main.state["scorer"]) is None

    def broken(p, degraded=False, thr=0.5):
        return SimpleNamespace(feature_names=["a"], threshold=thr, score=lambda *a, **k: SimpleNamespace(
            probability=p, degraded=degraded, degraded_branches=["lstm_attention"] if degraded else []))
    assert "invalide" in main.sanity_check(broken(float("nan")))
    assert "invalide" in main.sanity_check(broken(1.7))
    assert "indisponibles" in main.sanity_check(broken(0.2, degraded=True))
    assert "seuil" in main.sanity_check(broken(0.2, thr=0.0))
    assert "échec" in main.sanity_check(SimpleNamespace(feature_names=["a"], threshold=0.5,
                                                         score=lambda *a, **k: 1 / 0))


def test_health_reports_a_feature_store_seeded_with_other_artifacts(client):
    from ml.serving.feature_store import scaler_fingerprint
    meta = FAKE.get("fs:meta")
    try:
        FAKE.set("fs:meta", json.dumps({"period_start": "2025-06-01", "scaler_md5": "autre-scaler"}))
        h = client.get("/health").json()
        assert h["feature_store_consistent"] is False and h["status"] == "degraded"
        FAKE.set("fs:meta", json.dumps({"period_start": "2025-06-01",
                                        "scaler_md5": scaler_fingerprint(ROOT / "ml" / "artifacts")}))
        assert client.get("/health").json()["feature_store_consistent"] is True
    finally:
        FAKE.set("fs:meta", meta)
        client.get("/health")


def test_invalid_transaction_is_rejected(client):
    r = client.post("/v1/score", json=tx(6, amount_usd=-5), headers={"X-API-Key": "test-key"})
    assert r.status_code == 422


def test_health_and_metrics(client):
    assert client.get("/health").json()["redis"] is True
    assert "scoring_latency_seconds" in client.get("/metrics").text
