"""API partenaires de bout en bout : vraie base PostgreSQL (schéma des migrations Alembic du back-office),
scoring simulé. Vérifie l'authentification par clé, les droits, l'isolement entre institutions, le retour des
fraudes constatées et la supervision du régulateur."""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "integration-layer")]

PG = dict(user=os.getenv("POSTGRES_USER", "nuru_admin"),
          password=os.getenv("POSTGRES_PASSWORD", "nuru_secure_password_2026"),
          host=os.getenv("TEST_POSTGRES_HOST", "localhost"), port=os.getenv("POSTGRES_PORT", "5432"))
TEST_DB = "fraud_test_partners"
os.environ["DATABASE_URL"] = f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{TEST_DB}"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = ""

KEYS = {"rawbank": "nuru_test-rawbank-key", "equity": "nuru_test-equity-key", "bcc": "nuru_test-bcc-key",
        "airtel_mm": "nuru_test-airtel-key"}
TX = {"transaction_id": "RB-0001", "timestamp": "2026-10-06T09:15:00", "user_id": "CLIENT-42",
      "channel": "MOBILE_MONEY", "tx_type": "P2P_SEND", "access_channel": "APP", "amount": 150000,
      "currency": "CDF", "balance_before_usd": 400.0, "device_id": "DEV-1", "location_province": "Kinshasa"}


@pytest.fixture(scope="module")
def client():
    try:
        admin = psycopg2.connect(dbname="postgres", **PG)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL indisponible (lancer docker compose up -d postgres)")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "services" / "backoffice-api",
                   check=True, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True)

    from shared.utils.api_keys import hash_key
    with psycopg2.connect(dbname=TEST_DB, **PG) as c, c.cursor() as cur:
        for code, kind, scopes, providers in (
                ("rawbank", "BANQUE", '["transactions","feedback"]', "[]"),
                ("equity", "BANQUE", '["transactions","feedback"]', "[]"),
                ("bcc", "REGULATEUR", '["supervision"]', "[]"),
                ("airtel_mm", "OPERATEUR_MM", '["transactions"]', '["airtel"]')):
            cur.execute("INSERT INTO institutions (code, name, kind, scopes, providers, key_prefix, key_hash, is_active) "
                        "VALUES (%s, %s, %s, %s, %s, 'nuru_t', %s, true)",
                        (code, code.upper(), kind, scopes, providers, hash_key(KEYS[code])))

    from fastapi.testclient import TestClient
    from app import main

    def scoring(request: httpx.Request) -> httpx.Response:
        tx = __import__("json").loads(request.content)
        scoring.seen.append(tx)
        return httpx.Response(200, json={"transaction_id": tx["transaction_id"], "action": "VERIFY",
                                         "risk_level": "ELEVE", "fraud_probability": 0.71, "reason": "test"})
    scoring.seen = []
    with TestClient(main.app) as c:
        main.state["http"] = httpx.AsyncClient(base_url="http://scoring", transport=httpx.MockTransport(scoring))
        c.scoring = scoring
        yield c
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    admin.close()


def h(code):
    return {"X-API-Key": KEYS[code]}


def persist(tx_id: str, institution: str, action: str = "APPROVE"):
    """Ce que fait le worker persister après le scoring (Kafka n'est pas lancé dans ce test)."""
    with psycopg2.connect(dbname=TEST_DB, **PG) as c, c.cursor() as cur:
        cur.execute("""INSERT INTO scored_transactions (transaction_id, tx_time, scored_at, user_id, channel, tx_type,
                       access_channel, amount, currency, amount_usd, province, device_id, fraud_probability, risk_level,
                       action, reason, rules_triggered, model_version, latency_ms, degraded, explanation, features,
                       institution) VALUES (%s, %s, %s, 'CLIENT-42', 'MOBILE_MONEY', 'P2P_SEND', 'APP', 150000, 'CDF',
                       52.6, 'Kinshasa', 'DEV-1', 0.12, 'FAIBLE', %s, 'test', '[]', 't', 10, false, '{}', '{}', %s)""",
                    (tx_id, datetime(2026, 10, 6, 9, 15), datetime.now(timezone.utc), action, institution))


def test_key_is_required_and_checked(client):
    assert client.get("/v1/me").status_code == 422
    assert client.get("/v1/me", headers={"X-API-Key": "nuru_fausse-cle"}).status_code == 401
    me = client.get("/v1/me", headers=h("rawbank")).json()
    assert me["code"] == "rawbank" and me["scopes"] == ["transactions", "feedback"]


def test_unified_transaction_is_scored_and_bound_to_the_institution(client):
    r = client.post("/v1/transactions", headers=h("rawbank"), json={**TX, "institution": "equity"})
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "VERIFY" and r.json()["institution"] == "rawbank"
    sent = client.scoring.seen[-1]
    assert sent["institution"] == "rawbank"                 # imposé par la clé, pas par le client
    assert sent["amount_usd"] > 0                           # CDF converti en USD par le serveur
    bad = client.post("/v1/transactions", headers=h("rawbank"), json={**TX, "tx_type": "INCONNU"})
    assert bad.status_code == 422


def test_scopes_and_native_formats_are_enforced(client):
    assert client.post("/v1/transactions", headers=h("bcc"), json=TX).status_code == 403     # régulateur
    assert client.get("/v1/supervision/summary", headers=h("rawbank")).status_code == 403   # banque
    assert client.post("/v1/transactions/vodacom", headers=h("airtel_mm"), json={}).status_code == 403
    assert client.post("/v1/transactions/inconnu", headers=h("airtel_mm"), json={}).status_code == 404


def test_institutions_only_see_their_own_transactions(client):
    persist("RB-0002", "rawbank")
    assert client.get("/v1/transactions/RB-0002", headers=h("rawbank")).json()["action"] == "APPROVE"
    assert client.get("/v1/transactions/RB-0002", headers=h("equity")).status_code == 404
    assert client.post("/v1/feedback", headers=h("equity"), json={
        "transaction_id": "RB-0002", "verdict": "FRAUDE", "note": "tentative sur une autre banque"}).status_code == 404


def test_feedback_labels_a_missed_fraud_and_closes_the_case(client):
    persist("RB-0003", "rawbank", action="APPROVE")
    r = client.post("/v1/feedback", headers=h("rawbank"), json={
        "transaction_id": "RB-0003", "verdict": "FRAUDE", "fraud_type": "SIM_SWAP",
        "note": "plainte du client : SIM remplacée la veille"})
    assert r.status_code == 201, r.text
    assert r.json()["missed_by_model"] is True
    detail = client.get("/v1/transactions/RB-0003", headers=h("rawbank")).json()
    assert detail["label"] == "FRAUDE" and detail["case_status"] == "FRAUDE_CONFIRMEE"
    again = client.post("/v1/feedback", headers=h("rawbank"), json={
        "transaction_id": "RB-0003", "verdict": "LEGITIME", "note": "doublon du retour"})
    assert again.status_code == 409
    assert client.post("/v1/feedback", headers=h("rawbank"), json={
        "transaction_id": "RB-0002", "verdict": "FRAUDE", "fraud_type": "PIRATAGE", "note": "type inventé"}).status_code == 422


def test_regulator_sees_aggregates_without_personal_data(client):
    persist("EQ-0001", "equity", action="BLOCK")
    r = client.get("/v1/supervision/summary?days=7", headers=h("bcc"))
    assert r.status_code == 200, r.text
    s = r.json()
    by_inst = {row["key"]: row for row in s["by_institution"]}
    assert by_inst["rawbank"]["confirmed_frauds"] == 1 and by_inst["rawbank"]["missed_frauds"] == 1
    assert by_inst["equity"]["blocked"] == 1
    assert "CLIENT-42" not in r.text and "DEV-1" not in r.text
    assert client.get("/v1/supervision/daily?days=7", headers=h("bcc")).json()["series"]
    own = client.get("/v1/stats?days=7", headers=h("equity")).json()
    assert own["institution"] == "equity" and own["totals"]["volume"] == 1 and "by_institution" not in own


def test_revoked_key_stops_working(client):
    from app import partners
    with psycopg2.connect(dbname=TEST_DB, **PG) as c, c.cursor() as cur:
        cur.execute("UPDATE institutions SET is_active = false WHERE code = 'equity'")
    partners.partners.cache.clear()                         # en service : au plus tard après le TTL (30 s)
    assert client.get("/v1/me", headers=h("equity")).status_code == 401
