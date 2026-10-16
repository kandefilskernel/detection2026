"""Sécurité du back-office : double authentification (TOTP), verrouillage, quatre yeux sur les déblocages."""
import base64
from datetime import datetime, timezone

from sqlalchemy import insert, select

from app import totp
from app.config import settings
from app.db import engine
from shared.database.models import Case, ScoredTransaction

from .conftest import login


def make_user(client, admin, email, role, password="Securite-2026!"):
    r = client.post("/users", headers=admin, json={"email": email, "full_name": email.split("@")[0],
                                                   "role": role, "password": password})
    assert r.status_code in (201, 409), r.text
    return password


def raw_login(client, email, password, otp=None):
    data = {"username": email, "password": password}
    if otp is not None:
        data["otp"] = otp
    return client.post("/auth/login", data=data)


def test_totp_matches_rfc6238_reference_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode()
    # RFC 6238, annexe B (SHA-1, 8 chiffres) : on garde les 6 derniers
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.verify(secret, "287082", None, now=59) == 1
    assert totp.verify(secret, "287082", 1, now=59) is None         # déjà utilisé : rejeu refusé
    assert totp.decrypt(totp.encrypt(secret)) == secret and totp.decrypt("abîmé") is None


def test_mandatory_two_factor_setup_then_login_with_code(client, admin, monkeypatch):
    pwd = make_user(client, admin, "chef2fa@exemple.cd", "SUPERVISEUR")
    monkeypatch.setattr(settings, "REQUIRE_2FA_ROLES", "SUPERVISEUR,ADMIN")

    r = raw_login(client, "chef2fa@exemple.cd", pwd)
    assert r.status_code == 200 and r.json()["two_factor_setup_required"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/cases", headers=h).status_code == 403
    assert client.get("/cases", headers=h).json()["detail"] == "2FA_SETUP_REQUIRED"
    assert client.get("/auth/me", headers=h).json()["two_factor_setup_required"] is True

    secret = client.post("/auth/2fa/setup", headers=h).json()["secret"]
    assert client.post("/auth/2fa/enable", headers=h, json={"code": "000000"}).status_code == 422
    step = totp.current_step()
    r = client.post("/auth/2fa/enable", headers=h, json={"code": totp.code_at(secret, step)})
    assert r.status_code == 200, r.text
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/cases", headers=h2).status_code == 200
    assert client.get("/cases", headers=h).status_code == 401        # ancienne session sans code : invalidée

    assert raw_login(client, "chef2fa@exemple.cd", pwd).json()["detail"] == "TOTP_REQUIRED"
    assert raw_login(client, "chef2fa@exemple.cd", pwd, totp.code_at(secret, step)).status_code == 401  # rejeu
    r = raw_login(client, "chef2fa@exemple.cd", pwd, totp.code_at(secret, step + 1))
    assert r.status_code == 200, r.text
    # rôle tenu à la 2FA : impossible de la désactiver soi-même ; l'administrateur peut la réinitialiser
    h3 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/auth/2fa/disable", headers=h3, json={"code": "123456"}).status_code == 403
    uid = r.json()["user"]["id"]
    monkeypatch.setattr(settings, "REQUIRE_2FA_ROLES", "")
    assert client.patch(f"/users/{uid}", headers=admin, json={"reset_totp": True}).json()["totp_enabled"] is False


def test_account_locks_after_repeated_failures_and_admin_unlocks(client, admin):
    pwd = make_user(client, admin, "verrou@exemple.cd", "ANALYSTE")
    for _ in range(settings.MAX_FAILED_LOGINS):
        assert raw_login(client, "verrou@exemple.cd", "mauvais-mot-de-passe").status_code == 401
    r = raw_login(client, "verrou@exemple.cd", pwd)
    assert r.status_code == 429 and "Retry-After" in r.headers
    uid = next(u["id"] for u in client.get("/users", headers=admin).json() if u["email"] == "verrou@exemple.cd")
    assert client.patch(f"/users/{uid}", headers=admin, json={"unlock": True}).status_code == 200
    assert raw_login(client, "verrou@exemple.cd", pwd).status_code == 200


def seed_block_case(tx_id: str, amount: float) -> int:
    with engine.begin() as c:
        c.execute(insert(ScoredTransaction).values(
            transaction_id=tx_id, tx_time=datetime(2025, 11, 5, 9, 0), scored_at=datetime.now(timezone.utc),
            user_id="U4Y", channel="MOBILE_MONEY", operator="AIRTEL", tx_type="CASH_OUT", access_channel="AGENT",
            amount=amount, currency="USD", amount_usd=amount, province="Kinshasa", device_id="D4Y",
            fraud_probability=0.97, risk_level="CRITIQUE", action="BLOCK", reason="test", rules_triggered=[],
            model_version="t", latency_ms=5.0, degraded=False, explanation={}, features={}))
        return c.execute(insert(Case).values(
            transaction_id=tx_id, tx_time=datetime(2025, 11, 5, 9, 0), user_id="U4Y", channel="MOBILE_MONEY",
            tx_type="CASH_OUT", amount_usd=amount, fraud_probability=0.97, risk_level="CRITIQUE", action="BLOCK")
            .returning(Case.id)).scalar_one()


def label_of(tx_id: str):
    with engine.connect() as c:
        return c.execute(select(ScoredTransaction.label).where(ScoredTransaction.transaction_id == tx_id)).scalar()


def test_large_unblock_needs_a_second_supervisor(client, admin, analyst):
    sup_a = login(client, "chefa@exemple.cd", make_user(client, admin, "chefa@exemple.cd", "SUPERVISEUR"))
    small = seed_block_case("TX-4Y-SMALL", 50.0)
    big = seed_block_case("TX-4Y-BIG", 900.0)
    note = {"status": "FAUX_POSITIF", "resolution_note": "client joint, opération reconnue"}

    assert client.patch(f"/cases/{small}", headers=analyst, json=note).status_code == 200      # sous le seuil : direct
    assert label_of("TX-4Y-SMALL") == 0

    r = client.patch(f"/cases/{big}", headers=analyst, json=note)
    assert r.status_code == 202 and r.json()["four_eyes"] is True, r.text
    req = r.json()["request"]["id"]
    assert label_of("TX-4Y-BIG") is None
    assert client.get(f"/cases/{big}", headers=analyst).json()["status"] == "EN_COURS"
    assert client.patch(f"/cases/{big}", headers=analyst, json=note).status_code == 409          # déjà en attente
    pending = client.get("/cases/unblock-requests", headers=sup_a).json()
    assert pending["can_decide"] and any(x["id"] == req for x in pending["items"])

    decision = {"approve": True, "note": "pièces vérifiées, déblocage accordé"}
    assert client.post(f"/cases/unblock-requests/{req}/decision", headers=analyst, json=decision).status_code == 403
    r = client.post(f"/cases/unblock-requests/{req}/decision", headers=sup_a, json=decision)
    assert r.status_code == 200 and r.json()["status"] == "APPROUVEE"
    assert label_of("TX-4Y-BIG") == 0
    assert client.get(f"/cases/{big}", headers=analyst).json()["status"] == "FAUX_POSITIF"
    assert client.post(f"/cases/unblock-requests/{req}/decision", headers=sup_a, json=decision).status_code == 409


def test_requester_cannot_approve_own_unblock(client, admin):
    sup_b = login(client, "chefb@exemple.cd", make_user(client, admin, "chefb@exemple.cd", "SUPERVISEUR"))
    case = seed_block_case("TX-4Y-SELF", 2000.0)
    r = client.patch(f"/cases/{case}", headers=sup_b, json={"status": "FAUX_POSITIF", "resolution_note": "je débloque moi-même"})
    assert r.status_code == 202
    req = r.json()["request"]["id"]
    r = client.post(f"/cases/unblock-requests/{req}/decision", headers=sup_b,
                    json={"approve": True, "note": "auto-validation interdite"})
    assert r.status_code == 403
    r = client.post(f"/cases/unblock-requests/{req}/decision", headers=admin,
                    json={"approve": False, "note": "justificatifs insuffisants"})
    assert r.status_code == 200 and r.json()["status"] == "REJETEE"
    assert label_of("TX-4Y-SELF") is None
