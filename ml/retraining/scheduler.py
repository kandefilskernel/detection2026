"""
Déclencheur de réentraînement (service « retrainer »).

Toutes les CHECK_INTERVAL secondes, le planificateur relève des SIGNAUX, décide s'il y a une
raison de réentraîner, vérifie qu'il y a assez de données étiquetées pour le faire, puis lance
ml.retraining.retrain (champion / challenger : le nouveau modèle n'est promu que s'il est meilleur).

Raisons de réentraîner :
    nouvelles étiquettes      verdicts d'analystes et plaintes depuis le dernier entraînement
    nouvelles données         beaucoup de transactions scorées depuis le dernier entraînement
    dérive                    la distribution des variables comportementales a changé (Prometheus)
    nouveaux comportements    trop de transactions « jamais vues » pour l'autoencodeur (Prometheus)
    modèle ancien             période maximale sans réentraînement dépassée
    demande manuelle          bouton du tableau de bord (superviseur / administrateur)

Garde-fous :
    - préparation : on n'entraîne pas sans assez d'étiquettes (MIN_LABELED) ni de fraudes
      confirmées (MIN_FRAUDS) ; la raison est alors notée « EN ATTENTE » avec ce qui manque,
      pour que les analystes sachent quoi étiqueter (cf. comportements nouveaux à examiner) ;
    - repos : COOLDOWN_H heures minimum entre deux entraînements automatiques, pour qu'une
      dérive persistante ne relance pas l'entraînement en boucle ;
    - tout est journalisé dans retrain_events (visible dans le tableau de bord).

En production, le même enchaînement est orchestré par Airflow
(ml/retraining/airflow_retraining_dag.py) ; ce planificateur léger évite d'installer
Airflow (≈ 4 Go) sur un poste de développement.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass

import httpx
from sqlalchemy import text

from ml.retraining import retrain
from shared.database.session import make_session_factory
from shared.logging.logger_config import configure_logging

log = logging.getLogger("retrainer")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")


@dataclass
class Config:
    check_interval_s: int = int(os.getenv("RETRAIN_CHECK_INTERVAL_S", "600"))
    new_labels: int = int(os.getenv("RETRAIN_NEW_LABELS", "500"))
    new_tx: int = int(os.getenv("RETRAIN_NEW_TX", "20000"))
    max_age_h: float = float(os.getenv("RETRAIN_MAX_AGE_HOURS", "168"))      # une semaine
    cooldown_h: float = float(os.getenv("RETRAIN_COOLDOWN_H", "6"))
    wait_log_h: float = float(os.getenv("RETRAIN_WAIT_LOG_H", "6"))
    min_labeled: int = retrain.MIN_LABELED
    min_frauds: int = retrain.MIN_FRAUDS


# ---------------------------------------------------------------------- signaux
def prom(query: str) -> float | None:
    try:
        r = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=5)
        res = r.json()["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:  # noqa: BLE001 — Prometheus momentanément indisponible : signal absent, pas de panique
        return None


def collect(engine) -> dict:
    """Relevé des signaux (SQL + Prometheus). Aucune décision ici."""
    with engine.connect() as c:
        last = c.execute(text("SELECT max(created_at) FROM model_registry")).scalar()
        row = c.execute(text("""
            SELECT
              count(*) FILTER (WHERE label IS NOT NULL AND (CAST(:t AS timestamptz) IS NULL OR labeled_at > :t)),
              count(*) FILTER (WHERE label = 1 AND (CAST(:t AS timestamptz) IS NULL OR labeled_at > :t)),
              count(*) FILTER (WHERE CAST(:t AS timestamptz) IS NULL OR scored_at > :t),
              count(*) FILTER (WHERE label IS NOT NULL),
              count(*) FILTER (WHERE label = 1),
              count(*) FILTER (WHERE label IS NULL AND tx_time <= (SELECT max(tx_time) FROM scored_transactions)
                                                      - CAST(:d AS float) * interval '1 day')
            FROM scored_transactions"""), {"t": last, "d": retrain.MATURITY_DAYS}).one()
        # dernier entraînement terminé : journal des événements OU registre des modèles (tout entraînement y laisse une ligne)
        done = c.execute(text("SELECT greatest((SELECT max(ts) FROM retrain_events WHERE status IN "
                              "('CHAMPION','CHALLENGER','REJETE','ERREUR')), (SELECT max(created_at) FROM model_registry))")).scalar()
    now = time.time()
    return {
        "new_labels": int(row[0]), "new_fraud_labels": int(row[1]), "new_tx": int(row[2]),
        "labeled_total": int(row[3]), "frauds_total": int(row[4]), "matured_unlabeled": int(row[5]),
        "age_h": round((now - last.timestamp()) / 3600, 1) if last else None,
        "since_last_run_h": round((now - done.timestamp()) / 3600, 1) if done else None,
        "drift_alarm": bool(prom("max(drift_alarm)") or 0),
        "novelty_alarm": bool(prom("max(novelty_alarm)") or 0),
        "novelty_rate": prom("max(novelty_rate)"),
        "drifted_features": prom("max(drift_features_drifted)"),
    }


# ---------------------------------------------------------------------- décision
def decide(sig: dict, cfg: Config) -> dict:
    """Raisons de réentraîner, préparation des données et repos. Fonction pure (testée)."""
    reasons = []
    if sig["new_labels"] >= cfg.new_labels:
        reasons.append(f"{sig['new_labels']} nouvelles étiquettes")
    if sig["new_tx"] >= cfg.new_tx:
        reasons.append(f"{sig['new_tx']} nouvelles transactions")
    if sig["drift_alarm"]:
        reasons.append("dérive des variables comportementales")
    if sig["novelty_alarm"]:
        reasons.append("nouveaux comportements détectés")
    if sig["age_h"] is not None and sig["age_h"] > cfg.max_age_h:
        reasons.append(f"modèle vieux de {sig['age_h']:.0f} h")
    trainable = sig["labeled_total"] + sig["matured_unlabeled"]
    missing = {"etiquettes": max(0, cfg.min_labeled - trainable),
               "fraudes_confirmees": max(0, cfg.min_frauds - sig["frauds_total"])}
    cooldown = sig["since_last_run_h"] is not None and sig["since_last_run_h"] < cfg.cooldown_h
    return {"reasons": reasons, "ready": not any(missing.values()), "missing": missing, "cooldown": cooldown}


# ---------------------------------------------------------------------- journal
def save_state(engine, sig: dict, decision: dict, cfg: Config) -> None:
    payload = {**sig, "decision": decision, "thresholds": {
        "new_labels": cfg.new_labels, "new_tx": cfg.new_tx, "max_age_h": cfg.max_age_h, "cooldown_h": cfg.cooldown_h,
        "min_labeled": cfg.min_labeled, "min_frauds": cfg.min_frauds}}
    with engine.begin() as c:
        c.execute(text("""INSERT INTO retrain_state (id, updated_at, signals) VALUES (1, now(), CAST(:s AS JSONB))
                          ON CONFLICT (id) DO UPDATE SET updated_at = now(), signals = CAST(:s AS JSONB)"""),
                  {"s": json.dumps(payload, default=str)})


def add_event(engine, trigger: str, reasons: list, status: str, detail: dict, requested_by: str | None = None) -> int:
    with engine.begin() as c:
        return c.execute(text("""INSERT INTO retrain_events (trigger, reasons, status, detail, requested_by, handled_at)
                                 VALUES (:t, CAST(:r AS JSONB), :s, CAST(:d AS JSONB), :u, now()) RETURNING id"""),
                         {"t": trigger, "r": json.dumps(reasons), "s": status,
                          "d": json.dumps(detail, default=str), "u": requested_by}).scalar()


def recently_waiting(engine, reasons: list, cfg: Config) -> bool:
    """Évite d'inscrire la même attente toutes les 10 minutes."""
    with engine.connect() as c:
        row = c.execute(text("SELECT reasons FROM retrain_events WHERE status = 'EN_ATTENTE' "
                             "AND ts > now() - make_interval(hours => :h) ORDER BY ts DESC LIMIT 1"),
                        {"h": cfg.wait_log_h}).first()
    return bool(row) and sorted(row[0]) == sorted(reasons)


def outcome(report: dict) -> tuple[str, dict]:
    status = report.get("status", "ERREUR")
    keys = ("version", "reason", "champion", "challenger", "diagnostics", "n_labeled_production", "n_frauds_production", "duration_s")
    return status, {k: report.get(k) for k in keys if report.get(k) is not None}


# ---------------------------------------------------------------------- cycle
def run_training(engine, trigger: str, reasons: list, requested_by: str | None = None, event_id: int | None = None) -> str:
    log.info("réentraînement lancé (%s) : %s", trigger, ", ".join(reasons))
    try:
        status, detail = outcome(retrain.run(engine))
    except Exception as e:  # noqa: BLE001
        log.exception("échec du réentraînement")
        status, detail = "ERREUR", {"erreur": f"{type(e).__name__}: {e}"[:500]}
    if event_id is None:
        add_event(engine, trigger, reasons, status, detail, requested_by)
    else:
        with engine.begin() as c:
            c.execute(text("UPDATE retrain_events SET status = :s, detail = CAST(:d AS JSONB), handled_at = now() "
                           "WHERE id = :i"), {"s": status, "d": json.dumps(detail, default=str), "i": event_id})
    log.info("résultat : %s", status)
    return status


def cycle(engine, cfg: Config) -> None:
    sig = collect(engine)
    dec = decide(sig, cfg)
    save_state(engine, sig, dec, cfg)

    # 1. demande manuelle : prioritaire, ignore le repos et les raisons, mais pas la préparation des données
    with engine.connect() as c:
        pending = c.execute(text("SELECT id, requested_by FROM retrain_events WHERE status = 'DEMANDEE' "
                                 "AND handled_at IS NULL ORDER BY ts LIMIT 1")).first()
    if pending:
        if dec["ready"]:
            run_training(engine, "MANUEL", ["demande manuelle"], pending[1], event_id=pending[0])
        else:
            with engine.begin() as c:
                c.execute(text("UPDATE retrain_events SET status = 'IGNORE', handled_at = now(), "
                               "detail = CAST(:d AS JSONB) WHERE id = :i"),
                          {"d": json.dumps({"reason": "pas assez de données étiquetées", "manque": dec["missing"]}),
                           "i": pending[0]})
            log.info("demande manuelle refusée : données insuffisantes %s", dec["missing"])
        return

    # 2. déclenchement automatique
    if not dec["reasons"]:
        log.info("rien à faire (signaux : %s)", {k: sig[k] for k in ("new_labels", "new_tx", "drift_alarm", "novelty_alarm")})
        return
    if dec["cooldown"]:
        log.info("raisons %s mais repos en cours (%.1f h < %.0f h)", dec["reasons"], sig["since_last_run_h"], cfg.cooldown_h)
        return
    if not dec["ready"]:
        log.info("raisons %s mais données insuffisantes : manque %s", dec["reasons"], dec["missing"])
        if not recently_waiting(engine, dec["reasons"], cfg):
            add_event(engine, "AUTO", dec["reasons"], "EN_ATTENTE", {"manque": dec["missing"]})
        return
    run_training(engine, "AUTO", dec["reasons"])


def main():
    configure_logging("retrainer")
    engine, _ = make_session_factory()
    cfg = Config()
    log.info("planificateur démarré : contrôle toutes les %ds ; seuils %s", cfg.check_interval_s, cfg)
    while True:
        try:
            cycle(engine, cfg)
        except Exception:  # noqa: BLE001
            log.exception("échec du cycle de réentraînement")
        # une demande manuelle est prise en charge en moins d'une minute, sans attendre l'intervalle complet
        waited = 0
        while waited < cfg.check_interval_s:
            time.sleep(30)
            waited += 30
            try:
                with engine.connect() as c:
                    if c.execute(text("SELECT 1 FROM retrain_events WHERE status = 'DEMANDEE' AND handled_at IS NULL "
                                      "LIMIT 1")).first():
                        break
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
