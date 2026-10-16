"""
integration-layer : API publique du système, pour toute institution partenaire (opérateurs Mobile Money, banques,
émetteurs de cartes, régulateur). Documentation interactive : /v1/docs.

    POST /v1/transactions              transaction au format commun (toute institution)
    POST /v1/transactions/{provider}   format natif d'un opérateur : vodacom | airtel | orange | visa
        1. authentifie l'institution (X-API-Key, voir app/partners.py) ;
        2. convertit le message vers le schéma pivot (adaptateur) et le rattache à l'institution ;
        3. demande la décision au scoring-service (appel synchrone) ;
        4. renvoie la décision, que l'institution applique : exécuter, faire vérifier ou refuser.
    GET  /v1/transactions/{id}, POST /v1/feedback, GET /v1/stats, GET /v1/supervision/*   (app/partners.py)

Si le scoring est indisponible, la politique de repli est configurable (FAIL_OPEN) :
laisser passer (continuité de service) ou exiger une vérification (prudence).
"""
from __future__ import annotations

import asyncio
import random
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.utils.metrics import metrics_response
from app import partners as partners_mod
from app.adapters.airtel_adapter import AirtelAdapter
from app.adapters.base_adapter import AdapterError
from app.adapters.orange_adapter import OrangeAdapter
from app.adapters.vodacom_adapter import VodacomAdapter
from app.adapters.visa_virtual_adapter import VisaVirtualAdapter
from app.partners import Principal, require_scope
from shared.logging.logger_config import configure_logging
from shared.schemas.unified_transaction import UnifiedTransaction

configure_logging("integration-layer")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    SCORING_URL: str = "http://localhost:8001"
    SCORING_API_KEY: str = "dev-scoring-key"
    SCORING_TIMEOUT_S: float = 0.8
    # Relances : le scoring est idempotent (une transaction relancée renvoie sa décision d'origine), on peut donc
    # retenter sans risque sur un échec TRANSITOIRE (profil client occupé = 503, coupure réseau, délai dépassé)
    # avant d'appliquer la politique de repli. Le tout dans un délai global borné.
    SCORING_RETRIES: int = 2
    SCORING_DEADLINE_S: float = 1.6
    SCORING_RETRY_BACKOFF_S: float = 0.05
    USD_CDF_RATE: float | None = None     # None : taux de l'année de l'opération (shared/utils/fx.py) ; sinon taux fixe
    # clés d'API opérateur -> fournisseur, ex. "vodacom:dev-vodacom-key,airtel:dev-airtel-key"
    OPERATOR_API_KEYS: str = ("vodacom:dev-vodacom-key,airtel:dev-airtel-key,"
                              "orange:dev-orange-key,visa:dev-visa-key")
    FAIL_OPEN: bool = False
    # Kafka : retours des institutions (étiquettes) et journal d'audit ; vide = journalisation locale seulement
    KAFKA_BOOTSTRAP_SERVERS: str = ""


settings = Settings()
ADAPTERS = {a.provider: a for a in (VodacomAdapter(settings.USD_CDF_RATE), AirtelAdapter(settings.USD_CDF_RATE),
                                    OrangeAdapter(settings.USD_CDF_RATE), VisaVirtualAdapter(settings.USD_CDF_RATE))}
KEYS = dict(reversed(pair.split(":", 1)) for pair in settings.OPERATOR_API_KEYS.split(",") if ":" in pair)

REQUESTS = Counter("integration_requests_total", "Messages opérateurs reçus", ["provider", "outcome"])
RETRIES = Counter("integration_scoring_retries_total", "Relances du scoring après un échec transitoire")
LATENCY = Histogram("integration_latency_seconds", "Latence bout-en-bout (adaptateur + scoring)",
                    ["provider"], buckets=(0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.5, 1))

state: dict = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state["http"] = httpx.AsyncClient(base_url=settings.SCORING_URL, timeout=settings.SCORING_TIMEOUT_S,
                                      limits=httpx.Limits(max_connections=200, max_keepalive_connections=50))
    partners_mod.partners = partners_mod.Partners(KEYS, settings.KAFKA_BOOTSTRAP_SERVERS or None)
    yield
    await state["http"].aclose()
    partners_mod.partners.close()


app = FastAPI(title="API partenaires — détection de fraude Mobile Money et cartes virtuelles (RDC)", version="1.1.0",
              description="Scoring en temps réel, retour des fraudes constatées et supervision. "
                          "Authentification : en-tête X-API-Key délivré par l'administrateur du système.",
              lifespan=lifespan, docs_url="/v1/docs", redoc_url="/v1/redoc", openapi_url="/v1/openapi.json")
app.include_router(partners_mod.router)


def _transient(e: Exception) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (502, 503, 504)
    return isinstance(e, httpx.TransportError)


async def post_with_retries(tx) -> httpx.Response:
    """Appel du scoring avec relances bornées sur les échecs transitoires (voir SCORING_RETRIES)."""
    deadline = time.perf_counter() + settings.SCORING_DEADLINE_S
    attempt = 0
    while True:
        try:
            r = await state["http"].post("/v1/score", content=tx.model_dump_json(),
                                         headers={"X-API-Key": settings.SCORING_API_KEY, "Content-Type": "application/json"})
            r.raise_for_status()
            return r
        except (httpx.HTTPError,) as e:
            pause = settings.SCORING_RETRY_BACKOFF_S * (2 ** attempt) * (0.5 + random.random())
            attempt += 1
            if not _transient(e) or attempt > settings.SCORING_RETRIES or time.perf_counter() + pause >= deadline:
                raise
            RETRIES.inc()
            await asyncio.sleep(pause)


async def decide(tx: UnifiedTransaction, provider: str) -> dict:
    """Décision du scoring, ou politique de repli s'il est indisponible."""
    t0 = time.perf_counter()
    try:
        r = await post_with_retries(tx)
        result = r.json()
        REQUESTS.labels(provider, result["action"]).inc()
    except (httpx.HTTPError, KeyError):
        REQUESTS.labels(provider, "scoring_unavailable").inc()
        result = {"transaction_id": tx.transaction_id,
                  "action": "APPROVE" if settings.FAIL_OPEN else "VERIFY",
                  "risk_level": "INCONNU", "reason": "scoring indisponible (politique de repli)",
                  "fraud_probability": None}
    LATENCY.labels(provider).observe(time.perf_counter() - t0)
    result["provider"] = provider
    result["institution"] = tx.institution
    return result


@app.post("/v1/transactions", summary="Scorer une transaction au format commun")
async def ingest_unified(request: Request, principal: Principal = Depends(require_scope("transactions"))):
    """Format commun (schéma pivot) : toute institution peut l'utiliser sans adaptateur spécifique. Le champ
    `institution` est fixé par le serveur d'après la clé d'API."""
    t0 = time.perf_counter()
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("objet JSON attendu")
        payload = {**payload, "institution": principal.code}
        if payload.get("amount_usd") is None and payload.get("currency") in ("USD", "CDF") and payload.get("amount"):
            # montant en USD facultatif : converti au taux de l'année de l'opération, comme les adaptateurs
            when = ADAPTERS["vodacom"].parse_time(str(payload.get("timestamp")))
            payload["amount_usd"] = round(ADAPTERS["vodacom"].to_usd(float(payload["amount"]), payload["currency"], when), 4)
        tx = UnifiedTransaction.model_validate(payload)
    except (ValidationError, ValueError, AdapterError) as e:
        REQUESTS.labels("unified", "invalid").inc()
        raise HTTPException(422, f"transaction invalide : {e}")
    result = await decide(tx, "unified")
    result["end_to_end_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return result


@app.post("/v1/transactions/{provider}", summary="Scorer une transaction au format natif d'un opérateur")
async def ingest(provider: str, request: Request, principal: Principal = Depends(require_scope("transactions"))):
    t0 = time.perf_counter()
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(404, f"format inconnu : {provider} (formats : {', '.join(ADAPTERS)})")
    if provider not in principal.providers:
        REQUESTS.labels(provider, "unauthorized").inc()
        raise HTTPException(403, f"le format {provider} n'est pas autorisé pour l'institution {principal.code}")
    try:
        tx = adapter.to_unified(await request.json())
    except (AdapterError, ValidationError, ValueError) as e:
        REQUESTS.labels(provider, "invalid").inc()
        raise HTTPException(422, f"message {provider} invalide : {e}")
    tx = tx.model_copy(update={"institution": principal.code})
    result = await decide(tx, provider)
    result["end_to_end_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return result


@app.get("/health")
async def health():
    try:
        r = await state["http"].get("/health")
        scoring = r.json().get("status")
    except httpx.HTTPError:
        scoring = "unreachable"
    return {"status": "ok", "service": "integration-layer", "scoring": scoring,
            "providers": sorted(ADAPTERS)}


@app.get("/metrics")
def metrics():
    return metrics_response()
