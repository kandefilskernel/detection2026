from datetime import datetime, timezone

import psycopg2
import pytest
from sqlalchemy import insert

from app.db import engine
from shared.database.models import Case, ScoredTransaction

from .conftest import PG, TEST_DB


def seed_alert(tx_id: str, fraud_type: str | None = "SIM_SWAP") -> int:
    tx_time = datetime(2025, 11, 3, 2, 15)
    with engine.begin() as c:
        c.execute(insert(ScoredTransaction).values(
            transaction_id=tx_id, tx_time=tx_time, scored_at=datetime.now(timezone.utc), user_id="U9",
            channel="MOBILE_MONEY", operator="AIRTEL", tx_type="CASH_OUT", access_channel="AGENT", amount=250.0,
            currency="USD", amount_usd=250.0, province="Kinshasa", device_id="D9", fraud_probability=0.93,
            risk_level="CRITIQUE", action="BLOCK", reason="test", rules_triggered=[], model_version="t",
            latency_ms=12.0, degraded=False, explanation={}, features={},
            fraud_type=fraud_type, fraud_type_probability=0.9 if fraud_type else None))
        return c.execute(insert(Case).values(
            transaction_id=tx_id, tx_time=tx_time, user_id="U9", channel="MOBILE_MONEY", tx_type="CASH_OUT",
            amount_usd=250.0, fraud_probability=0.93, risk_level="CRITIQUE", action="BLOCK",
            fraud_type=fraud_type)
            .returning(Case.id)).scalar_one()


def test_login_rejects_bad_password(client):
    assert client.post("/auth/login", data={"username": "admin@test.local", "password": "faux"}).status_code == 401


def test_endpoints_require_token(client):
    assert client.get("/transactions").status_code == 401


def test_rbac_analyst_cannot_manage_users(client, analyst):
    r = client.post("/users", headers=analyst, json={"email": "x@exemple.cd", "full_name": "X",
                                                     "role": "ADMIN", "password": "Password-2026!"})
    assert r.status_code == 403


def test_rbac_analyst_cannot_read_audit(client, analyst):
    assert client.get("/audit", headers=analyst).status_code == 403


def test_case_workflow_sets_label(client, analyst):
    case_id = seed_alert("TX-CASE-1")
    assert client.patch(f"/cases/{case_id}", headers=analyst, json={"status": "EN_COURS"}).json()["status"] == "EN_COURS"
    # note obligatoire pour clore
    assert client.patch(f"/cases/{case_id}", headers=analyst, json={"status": "FAUX_POSITIF"}).status_code == 422
    r = client.patch(f"/cases/{case_id}", headers=analyst,
                     json={"status": "FAUX_POSITIF", "resolution_note": "Client en voyage, opération confirmée"})
    assert r.status_code == 200 and r.json()["resolved_by"] is not None
    detail = client.get("/transactions/TX-CASE-1", headers=analyst).json()
    assert detail["label"] == 0
    # un dossier clos ne peut plus changer d'état
    assert client.patch(f"/cases/{case_id}", headers=analyst, json={"status": "OUVERT"}).status_code == 409


def test_reports_are_available(client, admin):
    k = client.get("/reports/kpis?minutes=60", headers=admin).json()
    assert k["volume"] >= 1 and "alert_rate" in k
    assert client.get("/reports/breakdown?dimension=operator", headers=admin).status_code == 200
    assert client.get("/reports/breakdown?dimension=drop table", headers=admin).status_code == 422


def test_model_comparison_report(client, analyst):
    assert client.get("/reports/model-comparison").status_code == 401
    r = client.get("/reports/model-comparison", headers=analyst)
    assert r.status_code == 200
    body = r.json()
    if body is not None:  # rapport écrit par ml.training.model_selection
        assert body["decision"]["key"] == body["methods"][0]["key"]
        assert len(body["methods"]) == 8 and all("weighted_score" in m for m in body["methods"])


def test_fraud_map_locates_frauds_by_province(client, analyst):
    seed_alert("TX-MAP-1")
    r = client.get("/reports/fraud-map?minutes=60", headers=analyst)
    assert r.status_code == 200
    body = r.json()
    assert "TX-MAP-1" in {f["transaction_id"] for f in body["frauds"]}
    assert all(f["action"] != "APPROVE" or f["label"] == 1 for f in body["frauds"])
    assert any(p["province"] == "Kinshasa" and p["frauds"] >= 1 for p in body["provinces"])
    assert client.get("/reports/fraud-map").status_code == 401


def test_fraud_type_is_exposed_filterable_and_aggregated(client, analyst):
    seed_alert("TX-TYPE-1", "SMURFING")
    detail = client.get("/transactions/TX-TYPE-1", headers=analyst).json()
    assert detail["fraud_type"] == "SMURFING" and detail["fraud_type_probability"] == 0.9
    only = client.get("/transactions?fraud_type=SMURFING", headers=analyst).json()
    assert only["total"] >= 1 and {i["fraud_type"] for i in only["items"]} == {"SMURFING"}
    cases = client.get("/cases?fraud_type=SMURFING", headers=analyst).json()
    assert cases["items"] and {c["fraud_type"] for c in cases["items"]} == {"SMURFING"}
    by_type = {r["fraud_type"]: r for r in client.get("/reports/fraud-types?minutes=60", headers=analyst).json()}
    assert by_type["SMURFING"]["frauds"] >= 1
    assert client.get("/reports/fraud-types").status_code == 401


def test_evidence_rag_returns_cases_and_knowledge(client, analyst):
    from pathlib import Path
    if not (Path(__file__).resolve().parents[3] / "ml/artifacts/case_index.npz").exists():
        pytest.skip("mémoire de cas absente (python -m ml.rag.case_index)")
    seed_alert("TX-RAG-1", "SMURFING")
    r = client.get("/transactions/TX-RAG-1/evidence", headers=analyst)
    assert r.status_code == 200, r.text
    ev = r.json()
    assert 1 <= len(ev["neighbors"]) <= 5 and ev["agreement"] in ("COHERENT", "DIVERGENT", "INSUFFISANT")
    assert all(n["similarity"] > 0 and n["source"] for n in ev["neighbors"])
    assert ev["knowledge"][0]["section"] == "Définition" and "Fractionnement" in ev["knowledge"][0]["title"]
    assert ev["summary"]
    assert client.get("/transactions/INCONNU/evidence", headers=analyst).status_code == 404
    assert client.get("/transactions/TX-RAG-1/evidence").status_code == 401


def test_nlp_analyze_and_complaint_deduces_social_engineering(client, analyst):
    r = client.post("/nlp/analyze", headers=analyst,
                    json={"text": "Felicitations vous avez gagne 1000 USD, envoyez votre pin pour recevoir le lot"})
    assert r.status_code == 200 and r.json()["social_engineering"]["level"] == "ELEVE"
    assert client.post("/nlp/analyze", json={"text": "bonjour"}).status_code == 401
    seed_alert("TX-NLP-1", None)
    note = "Un faux agent Vodacom m'a appele, j'ai donne mon code PIN, j'ai peur, on a retire mon argent"
    c = client.post("/cases/complaint/TX-NLP-1", headers=analyst, json={"note": note})
    assert c.status_code == 201 and c.json()["fraud_type"] == "SOCIAL_ENGINEERING"
    assert client.get("/transactions/TX-NLP-1", headers=analyst).json()["fraud_type"] == "SOCIAL_ENGINEERING"


def test_retraining_status_trigger_and_review(client, analyst, admin):
    from sqlalchemy import text
    st = client.get("/retraining/status", headers=analyst)
    assert st.status_code == 200 and st.json()["events"] == [] and st.json()["signals"] is None
    # un analyste ne peut pas demander un réentraînement ; un administrateur oui, une seule fois à la fois
    assert client.post("/retraining/trigger", headers=analyst).status_code == 403
    ev = client.post("/retraining/trigger", headers=admin)
    assert ev.status_code == 202 and ev.json()["status"] == "DEMANDEE" and ev.json()["trigger"] == "MANUEL"
    assert client.post("/retraining/trigger", headers=admin).status_code == 409
    assert client.get("/retraining/status", headers=analyst).json()["pending_request"] is True
    # le planificateur journalise un résultat : l'état l'expose
    with engine.begin() as c:
        c.execute(text("UPDATE retrain_events SET status = 'IGNORE', handled_at = now(), "
                       "detail = '{\"manque\": {\"etiquettes\": 5}}'"))
        c.execute(text("INSERT INTO retrain_state (id, signals) VALUES (1, '{\"new_labels\": 3}')"))
    st = client.get("/retraining/status", headers=analyst).json()
    assert st["pending_request"] is False and st["events"][0]["status"] == "IGNORE" and st["signals"]["new_labels"] == 3
    # comportements nouveaux à examiner, puis revue d'analyste qui étiquette
    assert client.get("/retraining/novel-behaviors", headers=analyst).status_code == 200
    seed_alert("TX-REV-1", None)
    r = client.post("/cases/review/TX-REV-1", headers=analyst, json={"verdict": "LEGITIME", "note": "Client en voyage, confirmé"})
    assert r.status_code == 201 and r.json()["status"] == "FAUX_POSITIF"
    assert client.get("/transactions/TX-REV-1", headers=analyst).json()["label"] == 0
    assert client.post("/cases/review/TX-REV-1", headers=analyst,
                       json={"verdict": "FRAUDE", "note": "déjà revu"}).status_code == 409
    assert client.post("/cases/review/TX-REV-1", headers=analyst, json={"verdict": "X", "note": "abcde"}).status_code == 422


def test_audit_log_is_append_only():
    conn = psycopg2.connect(dbname=TEST_DB, **PG)
    with conn, conn.cursor() as cur:
        cur.execute("INSERT INTO audit_log (ts, actor, action, entity, details, prev_hash, hash) "
                    "VALUES (now(), 'test', 'X', 'y', '{}', 'a', 'b')")
    with pytest.raises(psycopg2.Error):
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE audit_log SET actor = 'pirate'")
    conn.close()


def test_customer_complaint_labels_missed_fraud(client, analyst):
    """Fraude laissée passer (APPROVE) puis signalée par le client : étiquette 1 + dossier clos."""
    with engine.begin() as c:
        c.execute(insert(ScoredTransaction).values(
            transaction_id="TX-MISSED", tx_time=datetime(2025, 11, 4, 9, 0), scored_at=datetime.now(timezone.utc),
            user_id="U10", channel="MOBILE_MONEY", operator="ORANGE", tx_type="P2P_SEND", access_channel="USSD",
            amount=40.0, currency="USD", amount_usd=40.0, province="Kinshasa", device_id="D10",
            fraud_probability=0.02, risk_level="FAIBLE", action="APPROVE", reason="test", rules_triggered=[],
            model_version="t", latency_ms=8.0, degraded=False, explanation={}, features={}))
    r = client.post("/cases/complaint/TX-MISSED", headers=analyst, json={"note": "Opération non reconnue"})
    assert r.status_code == 201 and r.json()["status"] == "FRAUDE_CONFIRMEE"
    assert client.get("/transactions/TX-MISSED", headers=analyst).json()["label"] == 1
    # une seconde plainte sur un dossier clos est refusée
    assert client.post("/cases/complaint/TX-MISSED", headers=analyst, json={"note": "doublon"}).status_code == 409
    assert client.post("/cases/complaint/INCONNUE", headers=analyst, json={"note": "xxxxx"}).status_code == 404


def test_institution_api_key_lifecycle(client, admin, analyst):
    from shared.utils.api_keys import hash_key
    body = {"code": "rawbank", "name": "Rawbank", "kind": "BANQUE", "contact_email": "fraude@rawbank.cd"}
    assert client.post("/institutions", headers=analyst, json=body).status_code == 403
    r = client.post("/institutions", headers=admin, json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    key = created["api_key"]
    assert key.startswith("nuru_") and created["scopes"] == ["transactions", "feedback"]
    assert client.post("/institutions", headers=admin, json=body).status_code == 409
    # la clé n'est jamais stockée ni relue : seulement son empreinte et un préfixe
    listed = next(i for i in client.get("/institutions", headers=admin).json() if i["code"] == "rawbank")
    assert "api_key" not in listed and key.startswith(listed["key_prefix"])
    with psycopg2.connect(dbname=TEST_DB, **PG) as c, c.cursor() as cur:
        cur.execute("SELECT key_hash FROM institutions WHERE code = 'rawbank'")
        assert cur.fetchone()[0] == hash_key(key)
    # renouvellement : nouvelle clé, l'ancienne ne correspond plus
    new_key = client.post(f"/institutions/{created['id']}/rotate-key", headers=admin).json()["api_key"]
    assert new_key != key
    with psycopg2.connect(dbname=TEST_DB, **PG) as c, c.cursor() as cur:
        cur.execute("SELECT key_hash FROM institutions WHERE code = 'rawbank'")
        assert cur.fetchone()[0] == hash_key(new_key)
    # un régulateur supervise par défaut, il ne soumet pas de transactions
    bcc = client.post("/institutions", headers=admin, json={"code": "bcc", "name": "Banque Centrale du Congo",
                                                            "kind": "REGULATEUR"}).json()
    assert bcc["scopes"] == ["supervision"]
    assert client.post("/institutions", headers=admin, json={"code": "x1", "name": "X", "kind": "BANQUE",
                                                             "scopes": ["tout"]}).status_code == 422
    r = client.patch(f"/institutions/{created['id']}", headers=admin, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


def test_network_detects_shared_mule_and_returns_ego_graph(client, analyst):
    """Trois comptes envoient vers le même portefeuille, deux transactions bloquées : réseau détecté."""
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        for i, (user, prob, label) in enumerate([("UNET1", 0.95, 1), ("UNET2", 0.9, None), ("UNET3", 0.2, None)]):
            c.execute(insert(ScoredTransaction).values(
                transaction_id=f"TX-NET-{i}", tx_time=datetime(2025, 11, 3, 3, i), scored_at=now, user_id=user,
                channel="MOBILE_MONEY", operator="VODACOM", tx_type="P2P_SEND", access_channel="APP", amount=80.0,
                currency="USD", amount_usd=80.0, province="Kinshasa", device_id=f"DNET{i}", counterparty_id="243700000999",
                fraud_probability=prob, risk_level="ELEVE", action="BLOCK" if prob > 0.5 else "APPROVE", reason="test",
                rules_triggered=[], model_version="t", latency_ms=10.0, degraded=False, explanation={}, features={},
                label=label))
    r = client.get("/network/overview?minutes=60", headers=analyst)
    assert r.status_code == 200, r.text
    body = r.json()
    ring = next(x for x in body["rings"] if x["id"] == "W:243700000999")
    assert ring["n_accounts"] == 3
    ego = client.get("/network/ego?node=243700000999&minutes=60", headers=analyst).json()
    assert ego["center"] == "W:243700000999"
    assert {"U:UNET1", "U:UNET2", "U:UNET3"} <= {n["id"] for n in ego["nodes"]}
    assert client.get("/network/ego?node=inconnu-xyz&minutes=60", headers=analyst).status_code == 404
    assert client.get("/network/overview").status_code == 401


def seed_scored(tx_id: str, prob: float, action: str = "APPROVE", user: str = "UFB", **extra) -> None:
    with engine.begin() as c:
        c.execute(insert(ScoredTransaction).values(
            transaction_id=tx_id, tx_time=datetime(2025, 11, 4, 10, 0), scored_at=datetime.now(timezone.utc),
            user_id=user, channel="MOBILE_MONEY", operator="ORANGE", tx_type="P2P_SEND", access_channel="APP",
            amount=20.0, currency="USD", amount_usd=20.0, province="Kinshasa", device_id=f"D-{tx_id}",
            fraud_probability=prob, risk_level="FAIBLE" if action == "APPROVE" else "ELEVE", action=action,
            reason="test", rules_triggered=[], model_version="t", latency_ms=5.0, degraded=False,
            explanation={"branch_scores": {"autoencoder": prob * 10}}, features={}, **extra))


def test_feedback_queue_proposes_unreviewed_approved_transactions(client, analyst):
    seed_scored("TX-FB-UNC", 0.49)          # au plus près du seuil
    seed_scored("TX-FB-LOW", 0.001)
    seed_scored("TX-FB-ALERT", 0.95, action="BLOCK")
    r = client.get("/feedback/queue?days=1&per_reason=50", headers=analyst)
    assert r.status_code == 200, r.text
    q = r.json()["reasons"]
    assert set(q) == {"INCERTITUDE", "NOUVEAUTE", "RESEAU", "TEMOIN"}
    unc = [x["transaction_id"] for x in q["INCERTITUDE"]]
    assert unc.index("TX-FB-UNC") < unc.index("TX-FB-LOW")
    assert all(x["action"] == "APPROVE" for k in q for x in q[k])
    assert "TX-FB-ALERT" not in {x["transaction_id"] for k in q for x in q[k]}


def test_control_sample_review_feeds_missed_fraud_estimate(client, analyst):
    seed_scored("TX-FB-T1", 0.02)
    seed_scored("TX-FB-T2", 0.03)
    seed_scored("TX-FB-AL", 0.9, action="VERIFY", label=1)
    for tx, verdict in (("TX-FB-T1", "FRAUDE"), ("TX-FB-T2", "LEGITIME")):
        r = client.post(f"/cases/review/{tx}", headers=analyst,
                        json={"verdict": verdict, "note": "échantillon témoin vérifié", "reason": "TEMOIN"})
        assert r.status_code == 201, r.text
        assert r.json()["review_reason"] == "TEMOIN"
    assert client.post("/cases/review/TX-FB-UNC", headers=analyst,
                       json={"verdict": "LEGITIME", "note": "motif inconnu", "reason": "AUTRE"}).status_code == 422
    q = client.get("/feedback/quality?days=1", headers=analyst)
    assert q.status_code == 200, q.text
    body = q.json()
    assert body["control_sample"]["n"] == 2 and body["control_sample"]["k"] == 1
    assert body["control_sample"]["low"] < 0.5 < body["control_sample"]["high"]
    assert body["alert_precision"]["n"] >= 1 and body["estimate"]["missed_frauds"] > 0
    assert 0 < body["estimate"]["recall"] < 1
    assert any(r["reason"] == "TEMOIN" and r["n"] == 2 for r in body["labels_by_reason"])
    # retirées de la file une fois revues
    q2 = client.get("/feedback/queue?days=1&per_reason=50", headers=analyst).json()["reasons"]
    assert "TX-FB-T1" not in {x["transaction_id"] for k in q2 for x in q2[k]}


def test_cost_policy_simulate_save_and_history(client, analyst, admin):
    for i, (p, amt) in enumerate([(0.3, 400.0), (0.3, 5.0), (0.002, 30.0), (0.99, 80.0)]):
        with engine.begin() as c:
            c.execute(insert(ScoredTransaction).values(
                transaction_id=f"TX-POL-{i}", tx_time=datetime(2025, 11, 6, 8, i), scored_at=datetime.now(timezone.utc),
                user_id="UPOL", channel="MOBILE_MONEY", operator="AIRTEL", tx_type="P2P_SEND", access_channel="APP",
                amount=amt, currency="USD", amount_usd=amt, province="Kinshasa", device_id="DPOL", fraud_probability=p,
                risk_level="MOYEN", action="APPROVE", reason="t", rules_triggered=[], model_version="t", latency_ms=1.0,
                degraded=False, explanation={}, features={}))
    base = client.get("/policy", headers=analyst).json()
    assert base["active_id"] is None and base["active"] == base["defaults"]

    cand = base["defaults"]
    cand["costs"]["MOBILE_MONEY"]["false_block_usd"] = 0.0
    cand["costs"]["MOBILE_MONEY"]["false_block_amount_share"] = 0.0
    sim = client.post("/policy/simulate", headers=analyst, json={"params": cand, "days": 1})
    assert sim.status_code == 200, sim.text
    body = sim.json()
    assert body["changed"] >= 1 and body["candidate"]["actions"]["BLOCK"] > body["current"]["actions"]["BLOCK"]

    bad = {**cand, "block_floor": 0.1}
    assert client.post("/policy/simulate", headers=analyst, json={"params": bad}).status_code == 422
    save = {"params": cand, "note": "test : blocage sans coût pour les clients honnêtes"}
    assert client.put("/policy", headers=analyst, json=save).status_code == 403
    r = client.put("/policy", headers=admin, json=save)
    assert r.status_code == 200, r.text
    assert r.json()["published"] is False            # Redis injoignable en test : rien n'atteint le scoring réel
    after = client.get("/policy", headers=analyst).json()
    assert after["active_id"] == r.json()["id"] and after["active"]["version"] == r.json()["version"]
    assert after["history"][0]["simulation"]["changed"] >= 1


def test_fairness_live_flags_overalerted_group(client, analyst):
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        for prov, n, alerts in (("Equateur", 400, 40), ("Maniema", 400, 2)):
            for i in range(n):
                c.execute(insert(ScoredTransaction).values(
                    transaction_id=f"TX-EQ-{prov}-{i}", tx_time=datetime(2025, 11, 7, 9, 0), scored_at=now,
                    user_id=f"UEQ{prov}", channel="MOBILE_MONEY", operator="ORANGE", tx_type="P2P_SEND",
                    access_channel="USSD", amount=10.0, currency="USD", amount_usd=10.0, province=prov, device_id="DEQ",
                    fraud_probability=0.5, risk_level="MOYEN", action="VERIFY" if i < alerts else "APPROVE", reason="t",
                    rules_triggered=[], model_version="t", latency_ms=1.0, degraded=False, explanation={},
                    features={"kyc_level": 1, "is_smartphone": 0}))
    r = client.get("/fairness/live?dimension=province&days=1", headers=analyst)
    assert r.status_code == 200, r.text
    g = {x["group"]: x for x in r.json()["groups"]}
    assert g["Equateur"]["flagged"] is True and g["Maniema"]["flagged"] is False
    assert g["Equateur"]["alert_ci"][0] < 0.1 < g["Equateur"]["alert_ci"][1]
    assert client.get("/fairness/live?dimension=kyc_level&days=1", headers=analyst).status_code == 200
    assert client.get("/fairness/live?dimension=revenu", headers=analyst).status_code == 422
