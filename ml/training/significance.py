"""
Outils d'inférence statistique pour comparer des modèles de détection de fraude.

    - Bootstrap PAR CLUSTER (utilisateur) : les transactions d'un même usager sont
      corrélées ; un bootstrap par transaction sous-estimerait la variance et
      donnerait des intervalles de confiance trop étroits.
    - Bootstrap APPARIÉ : tous les modèles sont évalués sur les MÊMES rééchantillons,
      ce qui permet un intervalle de confiance sur la DIFFÉRENCE de performance.
    - Test de McNemar exact : compare deux modèles au seuil opérationnel
      (transactions correctement / incorrectement classées).
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import average_precision_score

from ml.training.evaluation import recall_at_fpr

METRICS: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
    "pr_auc": lambda y, s: float(average_precision_score(y, s)),
    "recall_at_1pct_fpr": lambda y, s: recall_at_fpr(y, s, 0.01),
}


def cluster_resample(groups: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Indices d'un échantillon bootstrap : on tire les usagers avec remise."""
    codes, inverse = np.unique(groups, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    bounds = np.concatenate([[0], np.cumsum(np.bincount(inverse))])
    picked = rng.integers(0, len(codes), size=len(codes))
    return np.concatenate([order[bounds[g]:bounds[g + 1]] for g in picked])


def paired_bootstrap(y: np.ndarray, scores: dict[str, np.ndarray], groups: np.ndarray,
                     reference: str | None = None, n_boot: int = 400, seed: int = 0,
                     metrics: dict | None = None) -> dict:
    """Intervalles de confiance à 95 % de chaque modèle et, si `reference` est donné,
    de la différence (modèle - référence), avec p-value bootstrap bilatérale
    (part de rééchantillons où la différence change de signe)."""
    metrics = metrics or METRICS
    y = np.asarray(y)
    rng = np.random.default_rng(seed)
    draws = {m: {name: [] for name in scores} for m in metrics}
    done = 0
    while done < n_boot:
        idx = cluster_resample(groups, rng)
        if y[idx].sum() == 0 or y[idx].sum() == len(idx):
            continue
        for m, fn in metrics.items():
            for name, s in scores.items():
                draws[m][name].append(fn(y[idx], s[idx]))
        done += 1

    out: dict = {}
    for name, s in scores.items():
        out[name] = {}
        for m, fn in metrics.items():
            d = np.asarray(draws[m][name])
            lo, hi = np.percentile(d, [2.5, 97.5])
            out[name][m] = {"point": round(fn(y, s), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}
    if reference is not None:
        for name in scores:
            if name == reference:
                continue
            for m in metrics:
                diff = np.asarray(draws[m][name]) - np.asarray(draws[m][reference])
                lo, hi = np.percentile(diff, [2.5, 97.5])
                p = 2 * min((diff <= 0).mean(), (diff >= 0).mean())
                out[name][m].update({
                    "diff_vs_reference": round(out[name][m]["point"] - out[reference][m]["point"], 4),
                    "diff_ci95": [round(float(lo), 4), round(float(hi), 4)],
                    "diff_p_value": round(float(max(p, 1.0 / n_boot)), 4),
                    "significant_95": bool(lo > 0 or hi < 0),
                })
    return out


def mcnemar_exact(y: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray) -> dict:
    """Test de McNemar exact (binomial) : a et b sont-ils aussi souvent justes quand ils divergent ?"""
    y, pred_a, pred_b = (np.asarray(v).astype(int) for v in (y, pred_a, pred_b))
    ok_a, ok_b = pred_a == y, pred_b == y
    only_a, only_b = int((ok_a & ~ok_b).sum()), int((~ok_a & ok_b).sum())
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_a, n, 0.5).pvalue)
    return {"only_a_correct": only_a, "only_b_correct": only_b, "p_value": round(p, 6),
            "significant_95": bool(p < 0.05)}
