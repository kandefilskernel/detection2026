"""API partenaires : institutions (opérateurs Mobile Money, banques, émetteurs de cartes, régulateur) qui utilisent
le système de l'extérieur.

Authentification : en-tête X-API-Key. La clé désigne une institution de la table `institutions` (créée par un
administrateur dans le back-office) ; ses droits (scopes) bornent ce qu'elle peut faire :

    transactions   soumettre des transactions, consulter SES décisions et SES statistiques
    feedback       signaler qu'une de SES transactions était (ou non) une fraude -> étiquette de réentraînement
    supervision    statistiques agrégées de toutes les institutions, sans donnée personnelle (régulateur, BCC)

Une institution ne voit jamais les données d'une autre : chaque transaction porte le code de l'institution qui l'a
soumise, fixé par le serveur d'après la clé (jamais par le client).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from prometheus_client import Counter
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from shared.database.models import Case, Institution, ScoredTransaction
from shared.database.session import make_session_factory
from shared.kafka_config.topics import TOPIC_ANALYST_FEEDBACK, TOPIC_AUDIT_LOGS
from shared.utils.api_keys import hash_key

log = logging.getLogger("integration.partners")
RATE_LIMITED = Counter("integration_rate_limited_total", "Requêtes refusées pour dépassement de quota", ["institution"])

FRAUD_TYPES = ("SIM_SWAP", "SOCIAL_ENGINEERING", "ACCOUNT_TAKEOVER", "AGENT_FRAUD", "SMURFING",
               "CARD_TESTING", "CNP_FRAUD", "TOPUP_DRAIN")
FINAL = ("FRAUDE_CONFIRMEE", "FAUX_POSITIF")


@dataclass(frozen=True)
class Principal:
    code: str
    name: str
    kind: str
    scopes: tuple[str, ...]
    providers: tuple[str, ...] = field(default_factory=tuple)
    legacy: bool = False           # clé d'opérateur historique (variable OPERATOR_API_KEYS)
    rate_limit_per_s: int | None = None


DEFAULT_RATE_PER_S = float(os.getenv("PARTNER_RATE_LIMIT_PER_S", "100"))
BURST_FACTOR = float(os.getenv("PARTNER_RATE_BURST_FACTOR", "2"))


class RateLimiter:
    """Seau à jetons PAR INSTITUTION : la limite par IP de Nginx ne suffit pas (une institution peut appeler depuis
    plusieurs adresses, plusieurs institutions peuvent partager une passerelle). Capacité = débit x BURST_FACTOR.
    Compté par processus : avec N workers ou N réplicas, le débit global toléré est au plus N fois la limite."""

    def __init__(self):
        self.buckets: dict[str, tuple[float, float]] = {}       # code -> (jetons, dernier remplissage)
        self.lock = threading.Lock()

    def allow(self, code: str, rate: float, now: float | None = None) -> tuple[bool, float]:
        """(autorisé, secondes avant le prochain jeton)."""
        now = time.monotonic() if now is None else now
        cap = max(rate * BURST_FACTOR, 1.0)
        with self.lock:
            tokens, last = self.buckets.get(code, (cap, now))
            tokens = min(cap, tokens + (now - last) * rate)
            if tokens >= 1.0:
                self.buckets[code] = (tokens - 1.0, now)
                return True, 0.0
            self.buckets[code] = (tokens, now)
            return False, (1.0 - tokens) / rate


class Partners:
    """Accès base + Kafka de l'API partenaires, initialisés au démarrage (voir main.lifespan)."""

    def __init__(self, legacy_keys: dict[str, str], kafka_bootstrap: str | None, cache_ttl_s: float = 30.0):
        self.legacy = legacy_keys                       # clé -> fournisseur (vodacom, airtel, orange, visa)
        self.engine, self.Session = make_session_factory(pool_size=5, max_overflow=5)
        self.cache: dict[str, tuple[float, Principal | None]] = {}
        self.ttl = cache_ttl_s
        self.limiter = RateLimiter()
        self.producer = None
        if kafka_bootstrap:
            try:
                from confluent_kafka import Producer
                self.producer = Producer({"bootstrap.servers": kafka_bootstrap, "acks": "all",
                                          "enable.idempotence": True})
            except Exception as e:  # noqa: BLE001
                log.warning("Kafka indisponible pour l'API partenaires : %s", e)

    # ------------------------------------------------------------------ authentification
    def _lookup(self, key: str) -> Principal | None:
        for k, provider in self.legacy.items():
            if hmac.compare_digest(k, key):
                return Principal(provider, provider.capitalize(), "OPERATEUR_MM", ("transactions",), (provider,), True)
        with self.Session() as db:
            inst = db.scalar(select(Institution).where(Institution.key_hash == hash_key(key)))
        if inst is None or not inst.is_active:
            return None
        return Principal(inst.code, inst.name, inst.kind, tuple(inst.scopes or ()), tuple(inst.providers or ()),
                         rate_limit_per_s=inst.rate_limit_per_s)

    def resolve(self, key: str) -> Principal | None:
        now = time.monotonic()
        hit = self.cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        p = self._lookup(key)
        # une clé révoquée cesse de fonctionner au plus tard après le TTL ; un refus est gardé moins longtemps
        self.cache[key] = (now + (self.ttl if p else 5.0), p)
        if len(self.cache) > 10_000:
            self.cache.clear()
        return p

    # ------------------------------------------------------------------ événements
    def _send(self, topic: str, key: str, payload: dict) -> None:
        if self.producer is None:
            log.info("[%s] %s", topic, payload)
            return
        self.producer.produce(topic, json.dumps(payload, default=str).encode(), key.encode())
        self.producer.poll(0)

    def audit(self, actor: str, action: str, entity: str, entity_id: str | None, details: dict) -> None:
        self._send(TOPIC_AUDIT_LOGS, entity, {
            "event_id": uuid.uuid4().hex, "ts": datetime.now(timezone.utc).isoformat(), "actor": actor,
            "action": action, "entity": entity, "entity_id": entity_id, "details": details})

    def feedback(self, transaction_id: str, label: int, actor: str, case_id: int) -> None:
        self._send(TOPIC_ANALYST_FEEDBACK, transaction_id, {
            "event_id": uuid.uuid4().hex, "ts": datetime.now(timezone.utc).isoformat(),
            "transaction_id": transaction_id, "label": label, "analyst": actor, "case_id": case_id})

    def close(self) -> None:
        if self.producer is not None:
            self.producer.flush(5)
        self.engine.dispose()


partners: Partners | None = None


def get_partners() -> Partners:
    if partners is None:
        raise HTTPException(503, "API partenaires indisponible")
    return partners


async def current_principal(x_api_key: str = Header(..., alias="X-API-Key"),
                            p: Partners = Depends(get_partners)) -> Principal:
    try:
        principal = await run_in_threadpool(p.resolve, x_api_key)
    except Exception:  # noqa: BLE001 — base indisponible : refuser proprement plutôt qu'une erreur 500
        log.exception("vérification de clé impossible")
        raise HTTPException(503, "vérification de la clé impossible, réessayer")
    if principal is None:
        raise HTTPException(401, "clé d'API invalide ou révoquée")
    ok, wait = p.limiter.allow(principal.code, float(principal.rate_limit_per_s or DEFAULT_RATE_PER_S))
    if not ok:
        RATE_LIMITED.labels(principal.code).inc()
        raise HTTPException(429, f"quota de débit dépassé pour {principal.code}",
                            headers={"Retry-After": str(max(1, round(wait + 0.5)))})
    return principal


def require_scope(scope: str):
    async def dep(principal: Principal = Depends(current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(403, f"droit « {scope} » non accordé à l'institution {principal.code}")
        return principal
    return dep


# ====================================================================== routes
router = APIRouter(prefix="/v1", tags=["partenaires"])


class FeedbackIn(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=64)
    verdict: Literal["FRAUDE", "LEGITIME"]
    note: str = Field(..., min_length=5, max_length=2000, description="Ce qui a été constaté (plainte, enquête…)")
    fraud_type: str | None = Field(None, description="Type constaté, si connu : " + ", ".join(FRAUD_TYPES))


@router.get("/me", summary="Institution associée à la clé et droits accordés")
async def me(principal: Principal = Depends(current_principal)):
    return {"code": principal.code, "name": principal.name, "kind": principal.kind,
            "scopes": list(principal.scopes), "providers": list(principal.providers)}


@router.get("/transactions/{transaction_id}", summary="Décision enregistrée pour une de vos transactions")
async def get_transaction(transaction_id: str, principal: Principal = Depends(require_scope("transactions")),
                          p: Partners = Depends(get_partners)):
    def q():
        with p.Session() as db:
            row = db.execute(select(ScoredTransaction, Case.status).outerjoin(
                Case, Case.transaction_id == ScoredTransaction.transaction_id).where(
                ScoredTransaction.transaction_id == transaction_id,
                ScoredTransaction.institution == principal.code)).first()
            if row is None:
                return None
            t, status = row
            return {"transaction_id": t.transaction_id, "timestamp": t.tx_time, "scored_at": t.scored_at,
                    "channel": t.channel, "tx_type": t.tx_type, "amount_usd": t.amount_usd,
                    "action": t.action, "risk_level": t.risk_level, "fraud_probability": t.fraud_probability,
                    "fraud_type": t.fraud_type, "reason": t.reason, "model_version": t.model_version,
                    "case_status": status, "label": {None: None, 1: "FRAUDE", 0: "LEGITIME"}[t.label]}
    out = await run_in_threadpool(q)
    if out is None:   # même réponse qu'elle soit inconnue ou à une autre institution : rien ne fuit
        raise HTTPException(404, "transaction inconnue (ou pas encore enregistrée : réessayer dans quelques secondes)")
    return out


@router.post("/feedback", status_code=201, summary="Signaler qu'une de vos transactions était, ou non, une fraude")
async def feedback(body: FeedbackIn, principal: Principal = Depends(require_scope("feedback")),
                   p: Partners = Depends(get_partners)):
    """Plainte d'un client, enquête interne, rétrofacturation… Le verdict clôt le dossier et devient une étiquette pour
    le prochain réentraînement du modèle (une fraude non détectée enseigne au modèle ce qu'il a manqué)."""
    if body.fraud_type and body.fraud_type not in FRAUD_TYPES:
        raise HTTPException(422, f"type de fraude inconnu : {body.fraud_type}")
    actor = f"api:{principal.code}"

    def apply():
        with p.Session() as db:
            tx = db.scalar(select(ScoredTransaction).where(ScoredTransaction.transaction_id == body.transaction_id,
                                                           ScoredTransaction.institution == principal.code))
            if tx is None:
                raise HTTPException(404, "transaction inconnue (ou pas encore enregistrée : réessayer)")
            if tx.label is not None:
                raise HTTPException(409, "transaction déjà étiquetée")
            c = db.scalar(select(Case).where(Case.transaction_id == tx.transaction_id).with_for_update())
            if c is None:
                c = Case(transaction_id=tx.transaction_id, tx_time=tx.tx_time, user_id=tx.user_id, channel=tx.channel,
                         tx_type=tx.tx_type, amount_usd=tx.amount_usd, fraud_probability=tx.fraud_probability,
                         risk_level=tx.risk_level, action=tx.action, fraud_type=tx.fraud_type,
                         institution=principal.code)
                db.add(c)
            elif c.status in FINAL:
                raise HTTPException(409, "dossier déjà clos")
            fraud = body.verdict == "FRAUDE"
            now = datetime.now(timezone.utc)
            c.status = "FRAUDE_CONFIRMEE" if fraud else "FAUX_POSITIF"
            c.resolution_note = (f"Retour de {principal.name}"
                                 + (f" (type constaté : {body.fraud_type})" if body.fraud_type else "") + f" : {body.note}")
            c.resolved_at = now
            tx.label, tx.labeled_at = int(fraud), now
            db.commit()
            return c.id, tx.action, fraud
    case_id, model_action, fraud = await run_in_threadpool(apply)
    p.feedback(body.transaction_id, int(fraud), actor, case_id)
    p.audit(actor, "RETOUR_INSTITUTION", "transaction", body.transaction_id,
            {"case_id": case_id, "verdict": body.verdict, "decision_modele": model_action,
             "fraud_type_constate": body.fraud_type,
             "fraude_manquee": fraud and model_action == "APPROVE"})
    return {"transaction_id": body.transaction_id, "case_id": case_id, "verdict": body.verdict,
            "missed_by_model": fraud and model_action == "APPROVE"}


# ---------------------------------------------------------------------- statistiques
SUMMARY_SQL = """
    SELECT {group} count(*) AS volume,
           count(*) FILTER (WHERE action <> 'APPROVE')                         AS alerts,
           count(*) FILTER (WHERE action = 'BLOCK')                            AS blocked,
           coalesce(round(sum(amount_usd)::numeric, 2), 0)                     AS amount_usd,
           coalesce(round((sum(amount_usd) FILTER (WHERE action = 'BLOCK'))::numeric, 2), 0) AS amount_blocked_usd,
           count(*) FILTER (WHERE label = 1)                                   AS confirmed_frauds,
           count(*) FILTER (WHERE label = 1 AND action = 'APPROVE')            AS missed_frauds,
           count(*) FILTER (WHERE label = 0 AND action <> 'APPROVE')           AS false_alerts
    FROM scored_transactions
    WHERE scored_at >= now() - CAST(:d AS float) * interval '1 day' {where}
    {groupby}
"""


def _summary(p: Partners, days: int, institution: str | None) -> dict:
    where = "AND institution = :inst" if institution else ""
    params = {"d": days, "inst": institution}

    def rows(dim: str | None) -> list[dict]:
        sql = SUMMARY_SQL.format(group=f"coalesce({dim}, 'INCONNU') AS key," if dim else "", where=where,
                                 groupby=f"GROUP BY 1 ORDER BY volume DESC" if dim else "")
        with p.engine.connect() as c:
            out = [dict(r._mapping) for r in c.execute(text(sql), params)]
        for r in out:
            for k, v in r.items():
                if k != "key" and v is not None:
                    r[k] = float(v) if "amount" in k else int(v)
            r["alert_rate"] = round(r["alerts"] / r["volume"], 5) if r["volume"] else 0.0
        return out

    total = rows(None)[0]
    res = {"period_days": days, "generated_at": datetime.now(timezone.utc).isoformat(), "totals": total,
           "by_channel": rows("channel"), "by_tx_type": rows("tx_type"), "by_province": rows("province"),
           "by_fraud_type": [r for r in rows("fraud_type") if r["key"] != "INCONNU"]}
    if institution is None:
        res["by_institution"] = rows("institution")
    return res


@router.get("/stats", summary="Statistiques de VOTRE institution")
async def own_stats(days: int = Query(30, ge=1, le=366), principal: Principal = Depends(require_scope("transactions")),
                    p: Partners = Depends(get_partners)):
    return {"institution": principal.code, **await run_in_threadpool(_summary, p, days, principal.code)}


@router.get("/supervision/summary", summary="Supervision (régulateur) : agrégats de toutes les institutions")
async def supervision_summary(days: int = Query(30, ge=1, le=366),
                              principal: Principal = Depends(require_scope("supervision")),
                              p: Partners = Depends(get_partners)):
    """Volumes, alertes, montants bloqués, fraudes confirmées et manquées, par institution, canal, opération, province
    et type de fraude. Aucune donnée personnelle : ni client, ni appareil, ni numéro."""
    out = await run_in_threadpool(_summary, p, days, None)
    p.audit(f"api:{principal.code}", "CONSULTATION_SUPERVISION", "supervision", None, {"days": days})
    return out


@router.get("/supervision/daily", summary="Supervision (régulateur) : évolution quotidienne")
async def supervision_daily(days: int = Query(90, ge=1, le=366), institution: str | None = Query(None, max_length=32),
                            _: Principal = Depends(require_scope("supervision")), p: Partners = Depends(get_partners)):
    sql = """
        SELECT date_trunc('day', scored_at)::date AS day, count(*) AS volume,
               count(*) FILTER (WHERE action <> 'APPROVE') AS alerts, count(*) FILTER (WHERE action = 'BLOCK') AS blocked,
               count(*) FILTER (WHERE label = 1) AS confirmed_frauds
        FROM scored_transactions
        WHERE scored_at >= now() - CAST(:d AS float) * interval '1 day' AND (CAST(:inst AS text) IS NULL OR institution = :inst)
        GROUP BY 1 ORDER BY 1"""

    def q():
        with p.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), {"d": days, "inst": institution})]
    return {"period_days": days, "institution": institution, "series": await run_in_threadpool(q)}
