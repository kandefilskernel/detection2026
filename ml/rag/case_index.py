"""
Construit l'index de cas de la mémoire RAG (ml/artifacts/case_index.npz).

    - cas = opérations de la période d'ENTRAÎNEMENT dont le verdict est connu
      (toutes les fraudes + un échantillon des opérations légitimes) ; la validation et le
      test ne sont jamais indexés, ce qui garde l'évaluation honnête
    - les légitimes sont sous-échantillonnés : chaque cas légitime porte un poids
      d'importance (nombre réel / nombre gardé) pour ne pas gonfler artificiellement la part
      de fraude parmi les voisins
    - mêmes variables normalisées que le modèle (scaler.pkl figé) ; les verdicts des analystes
      s'ajoutent à la volée côté back-office (voir app/routers/transactions.py)

Usage : python -m ml.rag.case_index [--max-legit 60000]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_engineering import FEATURE_NAMES, PROCESSED_DIR, load_or_build_features
from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR, CLIP, temporal_split

INDEX_FILE = "case_index.npz"


def load_table() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    cache = PROCESSED_DIR / "features.csv"
    table = (pd.read_csv(cache, parse_dates=["timestamp"], low_memory=False) if cache.exists()
             else load_or_build_features(cache_path=cache))
    table["timestamp"] = pd.to_datetime(table["timestamp"])
    split, _ = temporal_split(table["timestamp"])
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    X = np.clip(scaler.transform(table[FEATURE_NAMES].to_numpy(dtype=np.float32)), -CLIP, CLIP).astype(np.float32)
    return table, X, split


def nearest_neighbors(Xq: np.ndarray, X: np.ndarray, k: int, chunk: int = 2000,
                      exclude_self: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """k plus proches voisins (distance euclidienne) de chaque ligne de Xq dans X, par blocs."""
    sq = (X ** 2).sum(axis=1)
    idx = np.empty((len(Xq), k), dtype=np.int64)
    dist = np.empty((len(Xq), k), dtype=np.float32)
    kk = k + 1 if exclude_self else k
    for s in range(0, len(Xq), chunk):
        q = Xq[s:s + chunk]
        d2 = (q ** 2).sum(axis=1, keepdims=True) - 2.0 * (q @ X.T) + sq[None, :]
        part = np.argpartition(d2, kk - 1, axis=1)[:, :kk]
        order = np.argsort(np.take_along_axis(d2, part, axis=1), axis=1)
        part = np.take_along_axis(part, order, axis=1)
        if exclude_self:
            part = part[:, 1:]
        idx[s:s + chunk] = part
        dist[s:s + chunk] = np.sqrt(np.maximum(np.take_along_axis(d2, part, axis=1), 0.0))
    return idx, dist


def build(max_legit: int = 60000, seed: int = 42) -> dict:
    table, X, split = load_table()
    rng = np.random.default_rng(seed)
    train = split <= 1
    y = table["is_fraud"].to_numpy()
    keep = list(np.where(train & (y == 1))[0])
    w = {}
    legit_idx = np.where(train & (y == 0))[0]
    channel = table["channel"].to_numpy()
    for ch in np.unique(channel):
        pool = legit_idx[channel[legit_idx] == ch]
        n_keep = int(round(max_legit * len(pool) / len(legit_idx)))
        chosen = rng.choice(pool, size=min(n_keep, len(pool)), replace=False)
        keep += list(chosen)
        w[ch] = len(pool) / max(len(chosen), 1)
    keep = np.array(sorted(keep))
    Xk = X[keep]
    wt = np.array([1.0 if y[i] == 1 else w[channel[i]] for i in keep], dtype=np.float32)

    sample = rng.choice(len(keep), size=min(2000, len(keep)), replace=False)
    # le voisin le plus proche d'un point de l'index est lui-même : on prend le 2e
    _, d2 = nearest_neighbors(Xk[sample], Xk, k=2)
    ref = float(np.median(d2[:, 1]))

    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    out = ARTIFACTS_DIR / INDEX_FILE
    np.savez_compressed(
        out, X=Xk.astype(np.float16), y=y[keep].astype(np.int8), w=wt,
        ftype=table["fraud_type"].fillna("").to_numpy()[keep].astype(str),
        ids=table["transaction_id"].to_numpy()[keep].astype(str),
        channel=channel[keep].astype(str), tx_type=table["tx_type"].to_numpy()[keep].astype(str),
        amount=table["amount_usd"].to_numpy(dtype=np.float32)[keep],
        mean=scaler.mean_, scale=scaler.scale_, clip=np.float32(CLIP), ref_dist=np.float32(ref),
        feature_names=json.dumps(FEATURE_NAMES))
    info = {"n": int(len(keep)), "n_fraud": int(y[keep].sum()), "legit_weight": {k: round(v, 2) for k, v in w.items()},
            "ref_dist": round(ref, 4), "file": str(out), "size_mb": round(Path(out).stat().st_size / 1e6, 1)}
    print(json.dumps(info, indent=2))
    return info


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--max-legit", type=int, default=60000)
    build(p.parse_args().max_legit)
