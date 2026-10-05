"""
Distribution de référence pour la détection de dérive.

    - variables brutes : échantillon de la période d'ENTRAÎNEMENT ;
    - scores du modèle hybride : échantillon de la période de VALIDATION (hors
      entraînement des branches, donc représentatif des scores en production).

    - erreurs de reconstruction de l'autoencodeur (ae_scores) sur la même validation : référence
      de la détection de NOUVEAUTÉ (comportements jamais vus).

Écrit ml/artifacts/drift_reference.npz (lu par drift_detector.py).
Usage : python -m ml.monitoring.build_reference
        python -m ml.monitoring.build_reference --ae-only   # ajoute seulement ae_scores à une référence existante
"""
from __future__ import annotations

import argparse

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_engineering import FEATURE_NAMES
from ml.models.hybrid_ensemble import HybridEnsemble

ARTIFACTS = "ml/artifacts"
N = 10_000


def main(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    split = np.load("ml/data/processed/split.npy")
    train_rows = np.flatnonzero(split <= 1)
    val_rows = np.flatnonzero(split == 2)

    feats = pd.read_csv("ml/data/processed/features.csv", usecols=FEATURE_NAMES).to_numpy(np.float32)
    ref_features = feats[rng.choice(train_rows, size=min(N, len(train_rows)), replace=False)]

    X = np.load("ml/data/processed/X_all.npy")
    seq = np.load("ml/data/processed/seq_idx.npy")
    model = HybridEnsemble.load(ARTIFACTS)
    rows = np.sort(rng.choice(val_rows, size=min(N, len(val_rows)), replace=False))
    ref_scores = model.predict_proba(X, seq, rows).astype(np.float32)
    ref_ae = model.branch_scores(X, seq, rows)[:, 2].astype(np.float32)

    np.savez_compressed(f"{ARTIFACTS}/drift_reference.npz", features=ref_features, scores=ref_scores,
                        ae_scores=ref_ae, feature_names=np.array(FEATURE_NAMES))
    print(f"[OK] référence de dérive : {len(ref_features)} transactions (entraînement), "
          f"{len(ref_scores)} scores (validation) -> {ARTIFACTS}/drift_reference.npz")


def add_ae_scores(seed: int = 42) -> None:
    """Ajoute ae_scores à la référence existante sans toucher aux autres tableaux : l'autoencodeur
    ne demande que les variables normalisées (features.csv + scaler.pkl), pas les séquences."""
    from ml.models.autoencoder_branch import ae_score
    from ml.preprocessing.train_test_split_normalize import CLIP, temporal_split
    path = f"{ARTIFACTS}/drift_reference.npz"
    ref = dict(np.load(path, allow_pickle=False))
    table = pd.read_csv("ml/data/processed/features.csv", usecols=["timestamp", *FEATURE_NAMES],
                        parse_dates=["timestamp"])
    split, _ = temporal_split(table["timestamp"])
    val_rows = np.flatnonzero(split == 2)
    rows = np.sort(np.random.default_rng(seed).choice(val_rows, size=min(N, len(val_rows)), replace=False))
    scaler = joblib.load(f"{ARTIFACTS}/scaler.pkl")
    X = np.clip(scaler.transform(table[FEATURE_NAMES].to_numpy(np.float32)[rows]), -CLIP, CLIP).astype(np.float32)
    model = HybridEnsemble.load(ARTIFACTS)
    ref["ae_scores"] = ae_score(model.ae, X)
    np.savez_compressed(path, **ref)
    print(f"[OK] ae_scores ajoutés : {len(X)} scores (validation) ; centile 99 = {np.quantile(ref['ae_scores'], 0.99):.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ae-only", action="store_true")
    add_ae_scores() if ap.parse_args().ae_only else main()
