"""
integration-layer : point d'entrée des opérateurs.

    POST /v1/transactions/{provider}   provider ∈ vodacom | airtel | orange | visa
        1. authentifie l'opérateur (X-API-Key propre à chaque opérateur) ;
        2. convertit le message propriétaire vers le schéma pivot (Adapter) ;
        3. demande la décision au scoring-service (appel synchrone) ;
        4. renvoie la décision à l'opérateur, qui exécute, fait vérifier ou refuse.

Si le scoring est indisponible, la politique de repli est configurable (FAIL_OPEN) :
laisser passer (continuité de service) ou exiger une vérification (prudence).
"""
from __future__ import annotations

import asyncio
import random
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.utils.metrics import metrics_response
from app.adapters.airtel_adapter import AirtelAdapter
from app.adapters.base_adapter import AdapterError
from app.adapters.orange_adapter import OrangeAdapter
from app.adapters.vodacom_adapter import VodacomAdapter
from app.adapters.visa_virtual_adapter import VisaVirtualAdapter
from shared.logging.logger_config import configure_logging

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
    yield
    await state["http"].aclose()


app = FastAPI(title="Integration layer — opérateurs Mobile Money & Visa", version="1.0.0", lifespan=lifespan)


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


@app.post("/v1/transactions/{provider}")
async def ingest(provider: str, request: Request, x_api_key: str = Header(..., alias="X-API-Key")):
    t0 = time.perf_counter()
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise HTTPException(404, f"opérateur inconnu : {provider}")
    if KEYS.get(x_api_key) != provider:
        REQUESTS.labels(provider, "unauthorized").inc()
        raise HTTPException(401, "clé d'API opérateur invalide")
    try:
        tx = adapter.to_unified(await request.json())
    except (AdapterError, ValidationError, ValueError) as e:
        REQUESTS.labels(provider, "invalid").inc()
        raise HTTPException(422, f"message {provider} invalide : {e}")

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
