"""Analyse de réseau : réseaux de fraude (mules, appareils et agents partagés) et voisinage d'un compte.

Le graphe est reconstruit à partir des transactions scorées de la fenêtre demandée, puis gardé en
mémoire quelques secondes (CACHE_TTL_S) : les écrans interrogent plusieurs fois le même instantané.
Suspicion d'une transaction : verdict de l'analyste s'il existe, sinon probabilité de fraude du modèle."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security import get_current_user
from shared.graph.network import KINDS, GraphScores, TransactionGraph, split_node

router = APIRouter(prefix="/network", tags=["réseaux"])

CACHE_TTL_S = 30
CACHE_WINDOWS = 3
MAX_ROWS = 200_000
_cache: dict[int, tuple[float, TransactionGraph, GraphScores, int, bool]] = {}
_lock = threading.Lock()


def _snapshot(db: Session, minutes: int) -> tuple[TransactionGraph, GraphScores, int, bool]:
    with _lock:
        hit = _cache.get(minutes)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1:]
        # agrégation compte x entité en SQL : quelques dizaines de milliers d'arêtes au lieu de centaines de
        # milliers de transactions à parcourir en Python
        rows = db.execute(text("""
            WITH t AS (
                SELECT user_id, tx_type, amount_usd, counterparty_id, device_id, agent_id, merchant_id,
                       least(greatest(COALESCE(label::float, fraud_probability), 0), 1) AS sp
                FROM scored_transactions WHERE scored_at >= now() - make_interval(mins => :m)
                ORDER BY scored_at DESC LIMIT :n),
            e AS (
                SELECT user_id, 'W:' || counterparty_id AS ent, sp, amount_usd FROM t
                  WHERE tx_type IN ('P2P_SEND', 'P2P_RECEIVE') AND counterparty_id <> ''
                UNION ALL SELECT user_id, 'D:' || device_id, sp, amount_usd FROM t WHERE device_id <> ''
                UNION ALL SELECT user_id, 'A:' || agent_id, sp, amount_usd FROM t WHERE agent_id <> ''
                UNION ALL SELECT user_id, 'M:' || merchant_id, sp, amount_usd FROM t WHERE merchant_id <> '')
            SELECT user_id, ent, count(*) AS n, count(sp) AS n_known, sum(sp) AS s, sum(amount_usd) AS amount,
                   (SELECT count(*) FROM t) AS n_tx
            FROM e WHERE user_id <> '' GROUP BY user_id, ent
        """), {"m": minutes, "n": MAX_ROWS + 1}).all()
        n_tx = rows[0].n_tx if rows else 0
        truncated = n_tx > MAX_ROWS
        g = TransactionGraph()
        for r in rows:
            g.add_edge(r.user_id, r.ent, r.n, r.n_known, r.s, r.amount)
        snap = (g, g.compute_scores(), min(n_tx, MAX_ROWS), truncated)
        if len(_cache) >= CACHE_WINDOWS:                    # garde les fenêtres les plus récemment construites
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[minutes] = (time.monotonic(), *snap)
        return snap


def _resolve(g: TransactionGraph, node: str) -> str:
    """Accepte « U:U000123 » ou un identifiant brut (compte, portefeuille, appareil, agent, marchand)."""
    if ":" in node:
        try:
            split_node(node)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return node
    for kind in KINDS:
        cand = f"{kind}:{node}"
        if cand in g.by_account or cand in g.by_entity:
            return cand
    raise HTTPException(404, f"« {node} » n'apparaît dans aucune transaction de la période")


@router.get("/overview")
def overview(minutes: int = Query(60 * 24, ge=5, le=60 * 24 * 30), rings_limit: int = Query(30, ge=1, le=200),
             db: Session = Depends(get_db), _=Depends(get_current_user)):
    g, sc, n_tx, truncated = _snapshot(db, minutes)
    rings = g.rings(sc)
    shared = [e for e, us in g.by_entity.items() if len(us) >= 2]
    top = sorted(shared, key=lambda e: -sc.entity[e])[:20]
    return {
        "window_minutes": minutes, "n_tx": n_tx, "truncated": truncated,
        "n_accounts": len(g.by_account), "n_entities": len(g.by_entity), "n_edges": len(g.edges),
        "n_shared_entities": len(shared), "base_rate": round(sc.base_rate, 5), "n_rings": len(rings),
        "accounts_in_rings": sum(r["n_accounts"] for r in rings),
        "rings": rings[:rings_limit],
        "top_entities": [{
            "id": e, "kind": e[0], "kind_label": KINDS[e[0]], "raw_id": e[2:],
            "score": round(sc.entity[e], 4), "direct": round(sc.direct[e], 4),
            "propagated": round(sc.propagated.get(e, 0.0), 4), "n_accounts": len(g.by_entity[e]),
        } for e in top],
    }


@router.get("/ego")
def ego(node: str = Query(..., min_length=2, max_length=80), minutes: int = Query(60 * 24, ge=5, le=60 * 24 * 30),
        hops: int = Query(2, ge=1, le=3), max_nodes: int = Query(80, ge=10, le=200),
        db: Session = Depends(get_db), _=Depends(get_current_user)):
    g, sc, _, _ = _snapshot(db, minutes)
    return g.ego(_resolve(g, node.strip()), sc, hops=hops, max_nodes=max_nodes)


@router.get("/evaluation")
def evaluation(_=Depends(get_current_user)):
    """Résultats hors ligne (ml/graph/evaluate_graph.py), copiés dans les artefacts."""
    try:
        return json.loads((Path(settings.RAG_INDEX_PATH).parent / "graph_evaluation.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, "évaluation non disponible : lancer python -m ml.graph.evaluate_graph") from None
