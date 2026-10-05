"""
Évaluation de l'analyse de messages sur deux corpus rédigés à la main :
    corpus_dev.json  : sert à régler les lexiques
    corpus_test.json : gelé, lu une seule fois pour le rapport

ATTENTION : ces corpus sont écrits par l'équipe, pas collectés auprès de vrais usagers. Ils servent de
test de non-régression et de mesure indicative ; ils ne prouvent pas la performance sur des messages
réels (lingala, swahili, fautes, argot), qui doit être mesurée sur des signalements réels.

Usage : python -m ml.nlp.evaluate_nlp [--dev]
"""
import argparse
import json
from pathlib import Path

import numpy as np

from shared.nlp.analyzer import analyze

HERE = Path(__file__).parent
THRESHOLDS = {"MOYEN_ou_plus": 0.40, "ELEVE": 0.70}


def prf(y, pred):
    tp, fp, fn = int(((y == 1) & (pred == 1)).sum()), int(((y == 0) & (pred == 1)).sum()), int(((y == 1) & (pred == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "rappel": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def boot(y, pred, fn, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    v = [fn(y[i], pred[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(n))]
    return [round(float(x), 3) for x in np.percentile(v, [2.5, 97.5])]


def run(name: str) -> dict:
    data = json.loads((HERE / f"corpus_{name}.json").read_text(encoding="utf-8"))
    res = [analyze(d["text"]) for d in data]
    y = np.array([d["se"] for d in data])
    score = np.array([r["social_engineering"]["score"] for r in res])
    out = {"corpus": name, "n": len(data), "n_se": int(y.sum())}
    for label, thr in THRESHOLDS.items():
        pred = (score >= thr).astype(int)
        m = prf(y, pred)
        m["f1_ci95"] = boot(y, pred, lambda a, b: prf(a, b)["f1"])
        out[f"ingenierie_sociale_{label}"] = m
    errors = [{"texte": d["text"], "attendu": d["se"], "score": s, "indices": [c["category"] for c in r["social_engineering"]["cues"]]}
              for d, r, s in zip(data, res, score) if (s >= THRESHOLDS["MOYEN_ou_plus"]) != bool(d["se"])]
    out["erreurs_ingenierie_sociale"] = errors
    # Le sentiment est évalué sur les messages RÉDIGÉS PAR DES CLIENTS (hors tentatives d'arnaque, dont le
    # « ton » est un artifice du fraudeur et dépend de l'étiqueteur).
    labels = ["NEGATIF", "NEUTRE", "POSITIF"]
    cust = [(d, r) for d, r in zip(data, res) if d["se"] == 0]
    true = [d["sentiment"] for d, _ in cust]
    pred_s = [r["sentiment"]["label"] for _, r in cust]
    out["erreurs_sentiment"] = [{"texte": d["text"], "attendu": d["sentiment"], "obtenu": r["sentiment"]["label"],
                                 "polarite": r["sentiment"]["polarity"]} for d, r in cust if r["sentiment"]["label"] != d["sentiment"]]
    out["sentiment"] = {"n": len(cust), "exactitude": round(float(np.mean([a == b for a, b in zip(true, pred_s)])), 3),
                        "matrice (lignes=attendu NEG/NEU/POS)": [[sum(1 for a, b in zip(true, pred_s) if a == t and b == p)
                                                                  for p in labels] for t in labels],
                        "negatifs_retrouves": round(float(np.mean([b == "NEGATIF" for a, b in zip(true, pred_s) if a == "NEGATIF"])), 3)}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    a = ap.parse_args()
    r = run("dev" if a.dev else "test")
    print(json.dumps({k: v for k, v in r.items() if not k.startswith("erreurs")}, indent=1, ensure_ascii=False))
    for e in r["erreurs_ingenierie_sociale"]:
        print(("MANQUÉ  " if e["attendu"] else "FAUSSE ALERTE ") + f"{e['score']:.2f} {e['indices']} :: {e['texte'][:110]}")
    for e in r["erreurs_sentiment"]:
        print(f"SENTIMENT attendu {e['attendu']} obtenu {e['obtenu']} ({e['polarite']}) :: {e['texte'][:100]}")
    if not a.dev:
        (Path("ml/reports") / "nlp_evaluation.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
