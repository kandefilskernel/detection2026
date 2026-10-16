"""Matrices de confusion du système de détection, sur la période de TEST (jamais vue à l'entraînement).

    1. Détecteur principal (fraude / légitime) au seuil opérationnel : global, Mobile Money, Visa virtuelle
    2. Classifieur de type de fraude (second étage), lignes normalisées (rappel par type)

Entrées  : ml/reports/test_predictions.csv (pred_hybrid), ml/reports/fraud_type_results.json
Sorties  : ml/reports/confusion_matrices.md, ml/reports/figures/confusion_*.png, ml/reports/confusion_matrices.json,
           ml/artifacts/confusion_matrices.json (lu par le tableau de bord)

Usage : python -m ml.training.confusion_report
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "ml" / "reports"
FIGURES = REPORTS / "figures"
ARTIFACTS = ROOT / "ml" / "artifacts"
CHANNELS = {"GLOBAL": "Global", "MOBILE_MONEY": "Mobile Money", "VISA_VIRTUAL": "Visa virtuelle"}


def binary_matrix(y: np.ndarray, p: np.ndarray) -> dict:
    tp = int(((y == 1) & (p == 1)).sum()); fn = int(((y == 1) & (p == 0)).sum())
    fp = int(((y == 0) & (p == 1)).sum()); tn = int(((y == 0) & (p == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "precision": prec, "recall": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "fpr": fp / (fp + tn) if fp + tn else 0.0,
            "accuracy": (tp + tn) / max(tp + tn + fp + fn, 1)}


def plot_binary(m: dict, title: str, path: Path) -> None:
    mat = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
    rows = mat.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.imshow(mat / np.maximum(rows, 1), cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            pct = mat[i, j] / max(rows[i, 0], 1)
            ax.text(j, i, f"{mat[i, j]:,}\n({pct:.2%})".replace(",", " "), ha="center", va="center",
                    color="white" if pct > 0.5 else "black", fontsize=11)
    ax.set_xticks([0, 1], ["Prédit légitime", "Prédit fraude"])
    ax.set_yticks([0, 1], ["Réel légitime", "Réel fraude"])
    ax.set_title(title, fontsize=11)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def plot_types(cm: np.ndarray, classes: list[str], path: Path) -> np.ndarray:
    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(8, 6.8))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]:
                ax.text(j, i, f"{norm[i, j]:.0%}\n{cm[i, j]}", ha="center", va="center", fontsize=8,
                        color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(classes)), classes, fontsize=8)
    ax.set_xlabel("Type prédit"); ax.set_ylabel("Type réel")
    ax.set_title("Matrice de confusion — type de fraude (lignes normalisées)", fontsize=11)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)
    return norm


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(REPORTS / "test_predictions.csv", usecols=["channel", "is_fraud", "pred_hybrid"])
    out: dict = {"binary": {}}
    lines = ["# Matrices de confusion", "",
             f"Période de test (jamais vue à l'entraînement), {f'{len(df):,}'.replace(',', ' ')} transactions, "
             "seuil opérationnel choisi sur la validation. **Données simulées.**", "",
             "## 1. Détecteur principal (fraude / légitime)", "",
             "| Périmètre | VP | FN | FP | VN | Précision | Rappel | F1 | Taux de FP |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, label in CHANNELS.items():
        g = df if key == "GLOBAL" else df[df.channel == key]
        m = binary_matrix(g.is_fraud.to_numpy(), g.pred_hybrid.to_numpy())
        out["binary"][key] = m
        plot_binary(m, f"Détecteur hybride — {label}", FIGURES / f"confusion_{key.lower()}.png")
        lines.append(f"| {label} | {m['tp']:,} | {m['fn']:,} | {m['fp']:,} | {m['tn']:,} | {m['precision']:.2%} | "
                     f"{m['recall']:.2%} | {m['f1']:.4f} | {m['fpr']:.3%} |".replace(",", " "))
    g = out["binary"]["GLOBAL"]
    lines += ["", "Lecture (global) :", "",
              "|  | Prédit légitime | Prédit fraude |", "|---|---|---|",
              f"| **Réel légitime** | {g['tn']:,} (VN) | {g['fp']:,} (FP : fausses alertes) |".replace(",", " "),
              f"| **Réel fraude** | {g['fn']:,} (FN : fraudes manquées) | {g['tp']:,} (VP) |".replace(",", " "), "",
              "Figures : `figures/confusion_global.png`, `figures/confusion_mobile_money.png`, `figures/confusion_visa_virtual.png`.", ""]

    ft = json.loads((REPORTS / "fraud_type_results.json").read_text(encoding="utf-8"))
    classes, cm = ft["classes"], np.array(ft["confusion_matrix"])
    norm = plot_types(cm, classes, FIGURES / "confusion_fraud_type.png")
    out["fraud_type"] = {"classes": classes, "matrix": cm.tolist(), "row_normalized": norm.round(4).tolist()}
    lines += ["## 2. Classifieur de type de fraude (fraudes du test)", "",
              f"Exactitude {ft['accuracy']:.2%}, F1 macro {ft['macro_f1']:.4f}. Lignes = type réel, colonnes = type prédit.", "",
              "| Réel \\ Prédit | " + " | ".join(classes) + " | Rappel |",
              "|---|" + "---|" * (len(classes) + 1)]
    for i, c in enumerate(classes):
        lines.append(f"| **{c}** | " + " | ".join(str(v) for v in cm[i]) + f" | {norm[i, i]:.1%} |")
    lines += ["", "Figure : `figures/confusion_fraud_type.png`."]
    for i, c in enumerate(classes):
        off = [(classes[j], norm[i, j]) for j in range(len(classes)) if j != i and norm[i, j] >= 0.05]
        if off:
            lines.append(f"- {c} confondu avec " + ", ".join(f"{n} ({v:.0%})" for n, v in off))

    (REPORTS / "confusion_matrices.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out["n_test"] = int(len(df))
    out["model_version"] = json.loads((ARTIFACTS / "metadata.json").read_text(encoding="utf-8")).get("trained_at")         if (ARTIFACTS / "metadata.json").exists() else None
    for path in (REPORTS / "confusion_matrices.json", ARTIFACTS / "confusion_matrices.json"):
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
