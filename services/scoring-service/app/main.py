"""
scoring-service : décision de fraude synchrone, en temps réel.

    POST /v1/score   transaction (schéma pivot) -> probabilité, niveau de risque, action,
                     explication. Le profil comportemental est lu ET mis à jour dans Redis.
    GET  /health     état du service (modèle chargé, Redis joignable)
    GET  /metrics    métriques Prometheus (latence, décisions, erreurs)
"""
from __future__ import annotations

import json
import math
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import redis
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from prometheus_client import Counter, Gauge, Histogram

from shared.utils.metrics import metrics_response
from app.config import settings
from app.events import EventPublisher
from app.schemas import ScoreResponse
from ml.serving.decision import DecisionPolicy
from shared.policy.costs import REDIS_KEY as POLICY_KEY, CostPolicy
from ml.physics.laws import summarize as summarize_physics
from shared.nlp.analyzer import analyze as analyze_text
from ml.serving.feature_store import scaler_fingerprint, PREFIX, RedisFeatureStore
from ml.serving.scorer import HybridScorer
from shared.schemas.unified_transaction import UnifiedTransaction
from shared.logging.logger_config import configure_logging

configure_logging("scoring-service")

LATENCY = Histogram("scoring_latency_seconds", "Latence de /v1/score",
                    buckets=(0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.5, 1))
DECISIONS = Counter("scoring_decisions_total", "Décisions rendues", ["action", "channel"])
RISK = Counter("scoring_risk_levels_total", "Niveaux de risque", ["risk_level"])
DEGRADED = Counter("scoring_degraded_total", "Scores rendus en mode dégradé")
ERRORS = Counter("scoring_errors_total", "Erreurs de scoring", ["kind"])
DUPLICATES = Counter("scoring_duplicates_total", "Transactions reçues plusieurs fois (décision d'origine renvoyée)")
PHYSICS = Counter("scoring_physics_violations_total", "Violations des lois physiques", ["law", "mode"])
PROBA = Histogram("scoring_fraud_probability", "Distribution des probabilités (dérive)",
                  buckets=(0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 0.99))
KAFKA_FAIL = Gauge("scoring_kafka_publish_failures", "Échecs cumulés de publication Kafka",
                   multiprocess_mode="livesum")

state: dict = {}
log = logging.getLogger("scoring")
MODEL_VERSION = Gauge("scoring_model_info", "Version du modèle servie (1 = active)", ["version"],
                      multiprocess_mode="livemax")
RELOADS = Counter("scoring_model_reloads_total", "Rechargements à chaud du modèle")
FS_CONSISTENT = Gauge("scoring_feature_store_consistent",
                      "1 si le feature store Redis a été amorcé avec le même scaler que le modèle servi", multiprocess_mode="livemin")
RELOAD_REFUSED = Counter("scoring_model_reload_refused_total", "Nouveaux modèles refusés par le contrôle de sanité")


def check_feature_store() -> bool:
    """Le feature store a-t-il été amorcé avec les mêmes artefacts que le modèle servi ? Sinon les profils et les
    séquences sont calculés dans une autre échelle (ou jusqu'à une autre date) : les scores dérivent sans erreur
    visible. Constat d'un incident réel (amorçage avec les artefacts d'une image ancienne)."""
    try:
        meta = json.loads(state["redis"].get(f"{PREFIX}:meta") or "{}")
    except Exception:  # noqa: BLE001
        return state.get("fs_consistent", True)
    expected = meta.get("scaler_md5")
    ok = expected is None or expected == scaler_fingerprint(settings.ARTIFACTS_DIR)
    if not ok and state.get("fs_consistent", True):
        log.error("FEATURE STORE INCOHÉRENT : amorcé avec un autre scaler que le modèle servi (amorcé jusqu'au %s) ; "
                  "relancer python -m ml.serving.seed_feature_store avec les artefacts actuels", meta.get("seeded_until"))
    state["fs_consistent"] = ok
    FS_CONSISTENT.set(1 if ok else 0)
    return ok


def sanity_check(scorer: HybridScorer) -> str | None:
    """Contrôle d'un modèle fraîchement chargé AVANT de l'utiliser : un score doit être fini, entre 0 et 1, et ne
    pas dépendre d'un détail. Renvoie la raison du refus, ou None si le modèle est sain."""
    try:
        x = np.zeros(len(scorer.feature_names), dtype=np.float32)
        a = scorer.score(x, [], explain=False)
        b = scorer.score(x + 0.5, [x], explain=False)
        for r in (a, b):
            if not (math.isfinite(r.probability) and 0.0 <= r.probability <= 1.0):
                return f"probabilité invalide ({r.probability})"
            if r.degraded:
                return f"branches indisponibles : {r.degraded_branches}"
        if not 0.0 < scorer.threshold < 1.0:
            return f"seuil invalide ({scorer.threshold})"
    except Exception as e:  # noqa: BLE001
        return f"échec du scoring de contrôle : {type(e).__name__}: {e}"
    return None


def _watch_model(stop: threading.Event, interval: float = 30.0) -> None:
    """Recharge le modèle à chaud quand le réentraînement promeut un nouveau champion
    (metadata.json est écrit en dernier par ml/retraining/retrain.py)."""
    meta_path = Path(settings.ARTIFACTS_DIR) / "metadata.json"
    while not stop.wait(interval):
        try:
            version = json.loads(meta_path.read_text(encoding="utf-8")).get("trained_at")
            current = state["scorer"].model_version
            if version and version != current and version != state.get("refused_version"):
                new = HybridScorer(settings.ARTIFACTS_DIR)      # chargé à côté, contrôlé, puis échange atomique
                problem = sanity_check(new)
                if problem:
                    state["refused_version"] = version          # on ne réessaie pas en boucle : l'ancien modèle reste actif
                    RELOAD_REFUSED.inc()
                    log.error("nouveau modèle %s REFUSÉ (%s) ; le modèle %s reste en service", version, problem, current)
                    continue
                # nouveau seuil du modèle, même politique de coût
                state["scorer"], state["policy"] = new, DecisionPolicy(threshold=new.threshold, cost=state["policy"].cost)
                MODEL_VERSION.labels(current).set(0)
                MODEL_VERSION.labels(new.model_version).set(1)
                RELOADS.inc()
                check_feature_store()
                log.warning("nouveau modèle chargé à chaud : %s -> %s", current, new.model_version)
        except Exception:  # noqa: BLE001 — fichiers en cours d'écriture : on réessaie plus tard
            log.exception("rechargement du modèle impossible pour l'instant")


def load_cost_policy(r) -> CostPolicy:
    """Politique publiée par le back-office (Redis) ; à défaut, ou si elle est invalide, la politique par défaut."""
    try:
        raw = r.get(POLICY_KEY)
        return CostPolicy.from_dict(json.loads(raw)) if raw else CostPolicy()
    except (redis.RedisError, ValueError, TypeError) as e:
        log.error("politique de coût illisible (%s) : politique par défaut", e)
        return CostPolicy()


def _watch_policy(stop: threading.Event, interval: float = 10.0) -> None:
    """Recharge à chaud la politique de coût modifiée dans le back-office."""
    while not stop.wait(interval):
        new = load_cost_policy(state["redis"])
        old = state["policy"]
        if new.to_dict() != old.cost.to_dict():
            state["policy"] = DecisionPolicy(threshold=old.threshold, cost=new)
            log.warning("politique de coût rechargée : %s -> %s", old.cost.version, new.version)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    r = redis.Redis.from_url(settings.REDIS_URL)
    meta_raw = r.get(f"{PREFIX}:meta")
    if meta_raw is None:
        raise RuntimeError("Feature store vide : lancer python -m ml.serving.seed_feature_store")
    meta = json.loads(meta_raw)
    scorer = HybridScorer(settings.ARTIFACTS_DIR)
    state.update(
        redis=r,
        scorer=scorer,
        store=RedisFeatureStore(r, pd.Timestamp(meta["period_start"]).timestamp(), seq_len=scorer.seq_len),
        policy=DecisionPolicy(threshold=scorer.threshold, cost=load_cost_policy(r)),
        events=EventPublisher(settings.KAFKA_BOOTSTRAP_SERVERS, settings.KAFKA_ENABLED),
        api_keys={k.strip() for k in settings.SCORING_API_KEYS.split(",") if k.strip()},
    )
    MODEL_VERSION.labels(scorer.model_version).set(1)
    check_feature_store()
    stop = threading.Event()
    threading.Thread(target=_watch_model, args=(stop,), daemon=True).start()
    threading.Thread(target=_watch_policy, args=(stop,), daemon=True).start()
    yield
    stop.set()
    state["events"].flush()


app = FastAPI(title="Scoring de fraude — Mobile Money RDC & Visa virtuelle", version="1.0.0",
              lifespan=lifespan)


def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    if x_api_key not in state["api_keys"]:
        raise HTTPException(status_code=401, detail="clé d'API invalide")


def _score(tx: UnifiedTransaction) -> dict:
    scorer: HybridScorer = state["scorer"]
    t0 = time.perf_counter()
    # En temps réel le statut est inconnu (transaction pas encore exécutée) : le profil
    # enregistre la transaction comme réussie, ou échouée si elle est bloquée.
    tx_in = tx.to_feature_input(tx.status)
    text = analyze_text(tx.memo)      # None si la transaction n'a pas de texte

    physics_box: dict = {}

    def decide(feats, x, history):
        res = scorer.score(x, history, explain="auto", top_k=settings.EXPLAIN_TOP_K,
                           channel=tx.channel.value)
        phys = summarize_physics(feats) if settings.PHYSICS_MODE != "off" else None
        dec = state["policy"].decide(res.probability, tx.amount_usd, tx.channel.value, feats, tx_in, text,
                                     phys if settings.PHYSICS_MODE == "enforce" else None, operator=tx.operator)
        physics_box.update(phys or {})
        return (res, dec), ("FAILED" if dec["action"] == "BLOCK" else "SUCCESS")

    def build(out: dict) -> dict:
        return _build_result(tx, text, physics_box, out, t0)

    out = state["store"].compute(tx_in, scorer.scale, decide, idem_key=f"fs:res:{tx.user_id}:{tx.transaction_id}",
                                 result_fn=build, idem_ttl=settings.IDEMPOTENCY_TTL_S)
    if "cached" in out:
        return {**out["cached"], "duplicate": True}
    return out["result"]


def _build_result(tx: UnifiedTransaction, text: dict | None, physics_box: dict, out: dict, t0: float) -> dict:
    scorer: HybridScorer = state["scorer"]
    res, decision = out["decided"]
    latency_ms = (time.perf_counter() - t0) * 1000
    # la typologie n'a de sens que pour une transaction signalée (alerte ou prédite frauduleuse)
    flagged = decision["action"] != "APPROVE" or res.probability >= scorer.threshold
    ftype, fprob, fcands = res.fraud_type, res.fraud_type_probability, res.fraud_type_candidates or []
    type_source = "modele"
    if flagged and text and text["social_engineering"]["level"] == "ELEVE" and tx.channel.value == "MOBILE_MONEY":
        # preuve directe dans le message : la typologie « ingénierie sociale » prime sur l'estimation du modèle
        ftype, fprob, type_source = "SOCIAL_ENGINEERING", text["social_engineering"]["score"], "texte"
        fcands = [{"type": ftype, "probability": fprob}] + [c for c in fcands if c["type"] != ftype][:2]
    return {
        "transaction_id": tx.transaction_id,
        "duplicate": False,
        "fraud_probability": round(res.probability, 6),
        "is_fraud_predicted": res.probability >= scorer.threshold,
        "threshold": round(scorer.threshold, 6),
        **decision,
        "fraud_type": ftype if flagged else None,
        "fraud_type_probability": fprob if flagged else None,
        "fraud_type_candidates": fcands if flagged else [],
        "fraud_type_source": type_source if flagged else None,
        "text_analysis": text,
        "physics": ({**physics_box, "mode": settings.PHYSICS_MODE} if physics_box else None),
        "known_user": out["known_user"],
        "explanation": {
            "top_features": res.top_features,
            "branch_scores": res.branch_scores,
            "branch_contributions": res.branch_contributions,
            "attention_on_history": res.attention,
        },
        "degraded": res.degraded,
        "degraded_branches": res.degraded_branches,
        "model_version": scorer.model_version,
        "latency_ms": round(latency_ms, 2),
        "features": {k: round(float(v), 5) for k, v in out["features"].items() if not k.startswith("phys_")},
    }


@app.post("/v1/score", response_model=ScoreResponse, dependencies=[Depends(require_api_key)])
async def score(tx: UnifiedTransaction):
    with LATENCY.time():
        try:
            result = await run_in_threadpool(_score, tx)
        except TimeoutError:
            ERRORS.labels("lock_timeout").inc()
            raise HTTPException(status_code=503, detail="profil client occupé, réessayer")
        except redis.RedisError:
            ERRORS.labels("redis").inc()
            raise HTTPException(status_code=503, detail="feature store indisponible")
        except Exception:  # noqa: BLE001 — jamais de 500 muet : l'appelant applique sa politique de repli
            ERRORS.labels("internal").inc()
            log.exception("échec du scoring", extra={"transaction_id": tx.transaction_id})
            raise HTTPException(status_code=500, detail="erreur interne du scoring")
    if result.get("duplicate"):
        DUPLICATES.inc()                  # relance d'un opérateur : même décision, profil et Kafka intacts
        return result
    DECISIONS.labels(result["action"], tx.channel.value).inc()
    RISK.labels(result["risk_level"]).inc()
    PROBA.observe(result["fraud_probability"])
    if result["degraded"]:
        DEGRADED.inc()
    for law in (result["physics"] or {}).get("violated", []):
        PHYSICS.labels(law, settings.PHYSICS_MODE).inc()
    if result["action"] != "APPROVE":
        log.warning("alerte %s", result["action"], extra={
            "transaction_id": tx.transaction_id, "user_id": tx.user_id, "action": result["action"],
            "latency_ms": result["latency_ms"]})

    event = {
        "event_id": uuid.uuid4().hex,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "transaction": tx.model_dump(mode="json", exclude={"memo"}),   # le texte brut ne circule pas dans Kafka
        "decision": {k: result[k] for k in ("action", "risk_level", "reason", "rules_triggered",
                                            "fraud_probability", "is_fraud_predicted", "threshold",
                                            "model_version", "latency_ms", "degraded",
                                            "fraud_type", "fraud_type_probability",
                                            "fraud_type_candidates")},
        "explanation": {**result["explanation"], "text_analysis": result["text_analysis"],
                        "physics": result["physics"],
                        "fraud_type_source": result["fraud_type_source"]},
        "features": result["features"],
    }
    state["events"].publish(event)
    KAFKA_FAIL.set(state["events"].failures)
    return result


@app.get("/health")
def health():
    try:
        state["redis"].ping()
        redis_ok = True
    except redis.RedisError:
        redis_ok = False
    fs_ok = check_feature_store() if redis_ok else False
    return {"status": "ok" if redis_ok and fs_ok else "degraded", "service": settings.SERVICE_NAME,
            "model_version": state["scorer"].model_version, "redis": redis_ok,
            "feature_store_consistent": fs_ok, "kafka": state["events"].producer is not None}


@app.get("/metrics")
def metrics():
    return metrics_response()
