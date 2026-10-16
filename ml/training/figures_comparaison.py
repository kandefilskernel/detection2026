"""Métriques complètes et graphiques de l'étude comparative des méthodes (mémoire, chapitre II, § II.2.9 h).

Complète ml/training/model_selection.py :
    1. Scores de TEST des 8 méthodes : hybride et composantes lus dans test_predictions.csv ; les 4 méthodes de
       référence (règles, régression logistique, Random Forest, Isolation Forest) sont ré-entraînées à l'identique
       (mêmes fonctions, mêmes périodes, même graine) et leurs PR-AUC sont contrôlées contre phase3_results.json
    2. Métriques au seuil retenu sur la validation : matrice de confusion, précision, rappel, spécificité, F1, F2,
       MCC, exactitude équilibrée, kappa de Cohen, PR-AUC, ROC-AUC, rappel à budget de fausses alertes fixé
    3. Intervalles de confiance à 95 % par bootstrap par usager (PR-AUC, précision, rappel, F1)
    4. Quatorze figures (ml/reports/figures/chapitre2/)

Sorties : ml/reports/figures_comparaison.json, ml/reports/figures_comparaison.md, ml/reports/figures/chapitre2/*.png,
          ml/reports/test_predictions_baselines.csv (cache des scores des méthodes de référence)

Usage : python -m ml.training.figures_comparaison [--n-boot 1000] [--reentrainer]
"""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, cohen_kappa_score, confusion_matrix,
                             fbeta_score, matthews_corrcoef, precision_recall_curve, roc_auc_score, roc_curve)

from ml.training.significance import cluster_resample

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "ml" / "reports"
FIG = REPORTS / "figures" / "chapitre2"
CACHE = REPORTS / "test_predictions_baselines.csv"

# clé -> (libellé, couleur) ; ordre d'affichage = du meilleur au moins bon (Tableau II.23)
METHODES = {
    "hybrid": ("Hybride", "#d62728"),
    "branch_lstm_attention": ("LSTM-attention", "#ff7f0e"),
    "branch_xgboost": ("XGBoost", "#1f77b4"),
    "baseline_random_forest": ("Random Forest", "#2ca02c"),
    "baseline_logreg": ("Régression logistique", "#17becf"),
    "branch_autoencoder": ("Autoencodeur", "#9467bd"),
    "baseline_isolation_forest": ("Isolation Forest", "#7f7f7f"),
    "baseline_rules": ("Règles métier", "#8c564b"),
}
TYPES = {"SIM_SWAP": "Échange de SIM", "SOCIAL_ENGINEERING": "Ingénierie sociale", "ACCOUNT_TAKEOVER": "Prise de contrôle",
         "SMURFING": "Fractionnement", "AGENT_FRAUD": "Fraude d'agent", "CNP_FRAUD": "Carte non présente",
         "TOPUP_DRAIN": "Vidage par rechargement", "CARD_TESTING": "Test de carte"}
BUDGETS = [0.0005, 0.001, 0.005, 0.01]  # taux de faux positifs tolérés

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11, "axes.grid": True,
                     "grid.alpha": .3, "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 200,
                     "savefig.bbox": "tight", "figure.facecolor": "white"})


def lab(k):
    return METHODES[k][0]


def coul(k):
    return METHODES[k][1]


def epais(k):
    return 2.6 if k == "hybrid" else 1.4


# ---------------------------------------------------------------- 1. scores de test
def scores_reference(reentrainer: bool) -> pd.DataFrame:
    """Scores de test des 4 méthodes de référence, ré-entraînées comme dans train_model.py (étape 5/5)."""
    if CACHE.exists() and not reentrainer:
        return pd.read_csv(CACHE)
    from ml.models.baselines import (isolation_score, rule_based_score, train_isolation_forest,
                                     train_logistic_regression, train_random_forest)
    from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR, load_processed
    seed = json.loads((REPORTS / "phase3_results.json").read_text(encoding="utf-8"))["config"]["seed"]
    data = load_processed()
    X, y = data.X, data.y
    test, train_all = data.rows("test"), data.rows("train", "early_stop")
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    out = pd.DataFrame({"transaction_id": data.meta.iloc[test]["transaction_id"].to_numpy()})
    print("  règles métier…", flush=True)
    out["score_baseline_rules"] = rule_based_score(scaler.inverse_transform(X[test]))
    print("  régression logistique…", flush=True)
    out["score_baseline_logreg"] = train_logistic_regression(X[train_all], y[train_all], seed).decision_function(X[test])
    print("  random forest…", flush=True)
    out["score_baseline_random_forest"] = train_random_forest(X[train_all], y[train_all], seed).predict_proba(X[test])[:, 1]
    print("  isolation forest…", flush=True)
    out["score_baseline_isolation_forest"] = isolation_score(train_isolation_forest(X[train_all][y[train_all] == 0], seed), X[test])
    out.to_csv(CACHE, index=False)
    return out


# ---------------------------------------------------------------- 2. métriques
def recall_a_fpr(y, s, fpr_max):
    fpr, tpr, _ = roc_curve(y, s)
    return float(tpr[fpr <= fpr_max].max())


def metriques(y, s, seuil):
    p = (s >= seuil).astype(int)
    vn, fp, fn, vp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    prec = vp / (vp + fp) if vp + fp else 0.0
    rap = vp / (vp + fn)
    return {"VP": int(vp), "FP": int(fp), "FN": int(fn), "VN": int(vn), "precision": prec, "rappel": rap,
            "specificite": vn / (vn + fp), "taux_fp": fp / (fp + vn), "f1": 2 * prec * rap / (prec + rap) if prec + rap else 0.0,
            "f2": float(fbeta_score(y, p, beta=2)), "mcc": float(matthews_corrcoef(y, p)),
            "exactitude_equilibree": float(balanced_accuracy_score(y, p)), "kappa": float(cohen_kappa_score(y, p)),
            "pr_auc": float(average_precision_score(y, s)), "roc_auc": float(roc_auc_score(y, s)),
            **{f"rappel_fpr_{b}": recall_a_fpr(y, s, b) for b in BUDGETS}}


def bootstrap(y, scores, seuils, groupes, n_boot, seed=0):
    rng = np.random.default_rng(seed)
    tirages = {k: {m: [] for m in ("pr_auc", "precision", "rappel", "f1")} for k in scores}
    fait = 0
    while fait < n_boot:
        idx = cluster_resample(groupes, rng)
        yy = y[idx]
        if yy.sum() == 0:
            continue
        for k, s in scores.items():
            ss = s[idx]; p = ss >= seuils[k]
            vp = int((p & (yy == 1)).sum()); fp = int((p & (yy == 0)).sum()); fn = int(yy.sum()) - vp
            pr = vp / (vp + fp) if vp + fp else 0.0; rc = vp / (vp + fn)
            t = tirages[k]
            t["pr_auc"].append(average_precision_score(yy, ss)); t["precision"].append(pr); t["rappel"].append(rc)
            t["f1"].append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
        fait += 1
        if fait % 100 == 0:
            print(f"  bootstrap {fait}/{n_boot}", flush=True)
    return {k: {m: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for m, v in t.items()} for k, t in tirages.items()}


# ---------------------------------------------------------------- 3. figures
def virgule(v, _pos=None):
    return f"{v:g}".replace(".", ",").replace("-", "−")


def sauver(fig, nom):
    """Enregistre la figure ; graduations à virgule décimale (usage français) sur les axes linéaires."""
    for ax in fig.axes:
        for axe, echelle in ((ax.xaxis, ax.get_xscale()), (ax.yaxis, ax.get_yscale())):
            if echelle == "linear" and isinstance(axe.get_major_formatter(), matplotlib.ticker.ScalarFormatter):
                axe.set_major_formatter(matplotlib.ticker.FuncFormatter(virgule))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / nom); plt.close(fig)


def fig_roc(y, scores, res):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5))
    for k in METHODES:
        f, t, _ = roc_curve(y, scores[k])
        a.plot(f, t, color=coul(k), lw=epais(k), label=f"{lab(k)} (ROC-AUC = {res[k]['roc_auc']:.4f})".replace(".", ","))
        b.plot(np.maximum(f, 1e-5), t, color=coul(k), lw=epais(k))
    a.plot([0, 1], [0, 1], "--", color="grey", lw=.8)
    a.set(xlabel="Taux de faux positifs", ylabel="Taux de vrais positifs (rappel)", title="(a) Vue complète")
    b.set_xscale("log"); b.set(xlim=(1e-5, 1), ylim=(0, 1.01), xlabel="Taux de faux positifs (échelle logarithmique)",
                                ylabel="Rappel", title="(b) Zone utile : très peu de fausses alertes")
    for x in (0.001, 0.01):
        b.axvline(x, color="grey", ls=":", lw=.8); b.text(x * 1.1, .03, f"{x:.1%}".replace(".", ","), fontsize=8, color="grey")
    a.legend(fontsize=8, loc="lower right")
    sauver(fig, "fig_II_06_roc.png")


def fig_pr(y, scores, res):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5))
    for k in METHODES:
        p, r, _ = precision_recall_curve(y, scores[k])
        for ax in (a, b):
            ax.plot(r, p, color=coul(k), lw=epais(k), label=f"{lab(k)} (PR-AUC = {res[k]['pr_auc']:.4f})".replace(".", ","))
    a.axhline(y.mean(), color="grey", ls="--", lw=.8)
    a.text(.70, y.mean() + .02, f"hasard ({y.mean():.1%} de fraudes)".replace(".", ","), fontsize=8, color="grey")
    a.set(xlabel="Rappel", ylabel="Précision", title="(a) Vue complète", ylim=(0, 1.02))
    b.set(xlim=(.85, 1.0), ylim=(.80, 1.005), xlabel="Rappel", ylabel="Précision", title="(b) Zoom : rappel ≥ 0,85, précision ≥ 0,80")
    a.legend(fontsize=8, loc="lower left")
    sauver(fig, "fig_II_07_precision_rappel.png")


def fig_barres(res):
    mets = [("precision", "Précision"), ("rappel", "Rappel"), ("f1", "F1"), ("f2", "F2"), ("mcc", "MCC"),
            ("exactitude_equilibree", "Exactitude\néquilibrée"), ("pr_auc", "PR-AUC")]
    fig, ax = plt.subplots(figsize=(13, 5))
    w = .8 / len(METHODES)
    for j, k in enumerate(METHODES):
        xs = np.arange(len(mets)) + (j - len(METHODES) / 2 + .5) * w
        ax.bar(xs, [res[k][m] for m, _ in mets], w, color=coul(k), label=lab(k), edgecolor="black" if k == "hybrid" else "none", lw=1)
    ax.set_xticks(range(len(mets)), [l for _, l in mets]); ax.set_ylim(0, 1.05); ax.set_ylabel("Valeur")
    ax.legend(ncol=4, fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.1)); ax.grid(axis="x", visible=False)
    sauver(fig, "fig_II_08_metriques.png")


def fig_ic(res, ic):
    """Haut : les 8 méthodes à l'échelle complète ; bas : zoom sur les 4 meilleures, où les écarts sont faibles."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), gridspec_kw={"height_ratios": [2, 1.1]})
    ordre = list(METHODES)[::-1]
    for col, (m, titre) in enumerate([("pr_auc", "PR-AUC"), ("f1", "F1 au seuil retenu")]):
        for lig, ks in enumerate([ordre, ordre[-4:]]):
            ax = axes[lig, col]
            for i, k in enumerate(ks):
                lo, hi = ic[k][m]; v = res[k][m]
                ax.errorbar(v, i, xerr=[[v - lo], [hi - v]], fmt="o", color=coul(k), capsize=4, ms=7 if k == "hybrid" else 5, lw=2)
                ax.annotate(f"{v:.4f}".replace(".", ","), (hi, i), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8)
            ax.set_yticks(range(len(ks)), [lab(k) for k in ks]); ax.set_ylim(-.6, len(ks) - .4)
            if lig == 0:
                ax.set_xlim(0, 1.1); ax.set_title(f"{titre} : intervalles de confiance à 95 %")
            else:
                lo = min(ic[k][m][0] for k in ks); hi = max(ic[k][m][1] for k in ks)
                ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6))
                ax.set_xlim(lo - (hi - lo) * .05, hi + (hi - lo) * .25); ax.set_title("Zoom sur les quatre meilleures méthodes", fontsize=10)
    fig.tight_layout()
    sauver(fig, "fig_II_09_intervalles_confiance.png")


def fig_confusion(res):
    fig, axes = plt.subplots(2, 4, figsize=(14, 7))
    for ax, k in zip(axes.ravel(), METHODES):
        r = res[k]; m = np.array([[r["VN"], r["FP"]], [r["FN"], r["VP"]]])
        ligne = m / m.sum(axis=1, keepdims=True)
        ax.imshow(ligne, cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{m[i, j]:,}".replace(",", " ") + f"\n{ligne[i, j]:.2%}".replace(".", ","), ha="center", va="center",
                        fontsize=9, color="white" if ligne[i, j] > .5 else "black", fontweight="bold")
        ax.set_xticks([0, 1], ["Prédit légitime", "Prédit fraude"], fontsize=8); ax.set_yticks([0, 1], ["Légitime", "Fraude"], fontsize=8)
        ax.set_title(lab(k), color=coul(k) if k == "hybrid" else "black", fontweight="bold" if k == "hybrid" else "normal"); ax.grid(False)
    fig.suptitle("Effectifs et pourcentage de chaque classe réelle (test : 183 240 opérations, 2 437 fraudes)", fontsize=10)
    sauver(fig, "fig_II_10_matrices_confusion.png")


def fig_erreurs(res):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ks = list(METHODES); x = np.arange(len(ks))
    b1 = ax.bar(x - .2, [res[k]["FP"] for k in ks], .4, color="#e377c2", label="Fausses alertes (FP)")
    b2 = ax.bar(x + .2, [res[k]["FN"] for k in ks], .4, color="#bcbd22", label="Fraudes manquées (FN)")
    ax.bar_label(b1, fontsize=8); ax.bar_label(b2, fontsize=8)
    ax.set_yscale("log"); ax.set_ylabel("Nombre d'erreurs (échelle logarithmique)")
    ax.set_xticks(x, [lab(k) for k in ks], rotation=20, ha="right"); ax.legend(); ax.grid(axis="x", visible=False)
    sauver(fig, "fig_II_11_erreurs.png")


def fig_types(phase3):
    ks = list(METHODES); types = list(TYPES)
    M = np.array([[phase3[k]["test_recall_by_fraud_type"][t]["recall"] for t in types] for k in ks])
    n = [phase3["hybrid"]["test_recall_by_fraud_type"][t]["n"] for t in types]
    fig, ax = plt.subplots(figsize=(12, 5.2))
    ax.imshow(M, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    for i in range(len(ks)):
        for j in range(len(types)):
            ax.text(j, i, f"{M[i, j]:.0%}" if M[i, j] in (0, 1) else f"{M[i, j]:.1%}".replace(".", ","), ha="center", va="center", fontsize=8)
    ax.set_xticks(range(len(types)), [f"{textwrap.fill(TYPES[t], 13)}\n(n = {c})" for t, c in zip(types, n)], fontsize=8, rotation=0)
    ax.set_yticks(range(len(ks)), [lab(k) for k in ks]); ax.grid(False)
    ax.add_patch(plt.Rectangle((-.5, -.5), len(types), 1, fill=False, ec="black", lw=2))
    sauver(fig, "fig_II_12_rappel_par_typologie.png")


def fig_canal(phase3):
    ks = list(METHODES); x = np.arange(len(ks))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for d, (c, nom, col) in zip((-.2, .2), [("MOBILE_MONEY", "Mobile Money", "#1f77b4"), ("VISA_VIRTUAL", "Carte Visa virtuelle", "#ff7f0e")]):
        b = ax.bar(x + d, [phase3[k]["test_by_channel"][c]["pr_auc"] for k in ks], .4, color=col, label=nom)
        ax.bar_label(b, fmt="%.3f", fontsize=7)
    ax.set_xticks(x, [lab(k) for k in ks], rotation=20, ha="right"); ax.set_ylim(0, 1.1); ax.set_ylabel("PR-AUC")
    ax.legend(loc="upper right"); ax.grid(axis="x", visible=False)
    sauver(fig, "fig_II_13_pr_auc_par_canal.png")


def fig_budget(res):
    ks = list(METHODES); x = np.arange(len(BUDGETS))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    w = .8 / len(ks)
    for j, k in enumerate(ks):
        ax.bar(x + (j - len(ks) / 2 + .5) * w, [res[k][f"rappel_fpr_{b}"] for b in BUDGETS], w, color=coul(k), label=lab(k),
               edgecolor="black" if k == "hybrid" else "none")
    ax.set_xticks(x, [f"{b:.2%}".replace(".", ",") + " de légitimes alertés" for b in BUDGETS])
    ax.set_ylabel("Rappel (part des fraudes détectées)"); ax.set_ylim(0, 1.05)
    ax.legend(ncol=4, fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.1)); ax.grid(axis="x", visible=False)
    sauver(fig, "fig_II_14_rappel_budget_alertes.png")


def fig_ablation(phase3):
    lignes = [("hybrid", "Hybride complet"), ("ablation_without_lstm_attention", "Sans LSTM-attention"),
              ("ablation_without_xgboost", "Sans XGBoost"), ("ablation_without_autoencoder", "Sans autoencodeur")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, (m, titre, fmt) in zip(axes, [("pr_auc", "PR-AUC", "{:.4f}"), ("f1", "F1", "{:.3f}"), ("false_positive_rate", "Taux de faux positifs", "{:.3%}")]):
        v = [phase3[k]["test"][m] for k, _ in lignes]
        b = ax.bar(range(4), v, color=["#d62728", "#999999", "#999999", "#999999"])
        ax.bar_label(b, labels=[fmt.format(x).replace(".", ",") for x in v], fontsize=8)
        lo = min(v); hi = max(v); ax.set_ylim(lo - (hi - lo) * 1.5, hi + (hi - lo) * .6)
        ax.set_xticks(range(4), [l for _, l in lignes], rotation=20, ha="right", fontsize=8); ax.set_title(titre); ax.grid(axis="x", visible=False)
    axes[2].set_title("Taux de faux positifs (plus bas = meilleur)")
    sauver(fig, "fig_II_15_ablation.png")


def fig_seuil(y, s, seuil):
    ts = np.linspace(.01, .99, 197)
    P, R, F = [], [], []
    for t in ts:
        p = s >= t; vp = (p & (y == 1)).sum(); fp = (p & (y == 0)).sum()
        pr = vp / (vp + fp) if vp + fp else 1.0; rc = vp / y.sum(); P.append(pr); R.append(rc); F.append(2 * pr * rc / (pr + rc) if pr + rc else 0)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(ts, P, label="Précision", color="#1f77b4", lw=2); ax.plot(ts, R, label="Rappel", color="#2ca02c", lw=2)
    ax.plot(ts, F, label="F1", color="#d62728", lw=2.5)
    ax.axvline(seuil, color="black", ls="--"); ax.text(seuil - .01, .995, f"τ* = {seuil:.3f}\n(choisi sur la validation)".replace(".", ","), fontsize=8, ha="right", va="top")
    ax.set(xlabel="Seuil de décision sur la probabilité de fraude", ylabel="Valeur sur le test", ylim=(.85, 1.0)); ax.legend(loc="lower left")
    sauver(fig, "fig_II_16_choix_seuil.png")


def fig_distribution(y, s, seuil):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bins = np.linspace(0, 1, 51)
    ax.hist(s[y == 0], bins, color="#1f77b4", alpha=.7, label=f"Légitimes (n = {(y == 0).sum():,})".replace(",", " "))
    ax.hist(s[y == 1], bins, color="#d62728", alpha=.7, label=f"Fraudes (n = {(y == 1).sum():,})".replace(",", " "))
    ax.axvline(seuil, color="black", ls="--", label="Seuil τ*"); ax.set_yscale("log")
    ax.set(xlabel="Probabilité de fraude donnée par l'hybride", ylabel="Nombre d'opérations (échelle log)"); ax.legend()
    sauver(fig, "fig_II_17_distribution_scores.png")


def fig_calibration(y, s):
    bords = np.array([0, .01, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, .99, 1.0001])
    b = np.digitize(s, bords) - 1
    pts = [(s[b == i].mean(), y[b == i].mean(), (b == i).sum()) for i in range(len(bords) - 1) if (b == i).sum() >= 20]
    brier = float(np.mean((s - y) ** 2))
    fig, ax = plt.subplots(figsize=(6, 5.5))
    ax.plot([0, 1], [0, 1], "--", color="grey", label="Calibration parfaite")
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color="#d62728", lw=2, label=f"Hybride (Brier = {brier:.5f})".replace(".", ","))
    ax.set(xlabel="Probabilité prédite moyenne", ylabel="Taux de fraude observé", xlim=(0, 1), ylim=(0, 1)); ax.legend(loc="upper left")
    sauver(fig, "fig_II_18_calibration.png")
    return brier


def fig_multicritere(sel):
    crit = sel["criteria"]; meth = sel["methods"]
    ordre = sorted(meth, key=lambda m: -m["weighted_score"])
    M = np.array([[m["notes"][c["key"]] for c in crit] for m in ordre])
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.imshow(np.c_[M, [m["weighted_score"] for m in ordre]], cmap="RdYlGn", vmin=1, vmax=5, aspect="auto")
    for i, m in enumerate(ordre):
        for j in range(len(crit)):
            ax.text(j, i, str(M[i, j]), ha="center", va="center", fontsize=10)
        ax.text(len(crit), i, f"{m['weighted_score']:.2f}".replace(".", ","), ha="center", va="center", fontsize=10, fontweight="bold")
    ax.set_xticks(range(len(crit) + 1), [f"{textwrap.fill(c['label'], 14)}\n({c['weight']:.0%})" for c in crit] + ["Score\npondéré / 5"], fontsize=8)
    ax.set_yticks(range(len(ordre)), [m["label"] for m in ordre]); ax.grid(False)
    ax.axvline(len(crit) - .5, color="black", lw=2)
    sauver(fig, "fig_II_19_matrice_multicritere.png")


# ---------------------------------------------------------------- programme principal
def main(n_boot: int, reentrainer: bool):
    phase3 = json.loads((REPORTS / "phase3_results.json").read_text(encoding="utf-8"))["results"]
    sel = json.loads((REPORTS / "model_selection.json").read_text(encoding="utf-8"))
    preds = pd.read_csv(REPORTS / "test_predictions.csv")
    print("Scores des méthodes de référence…", flush=True)
    ref = scores_reference(reentrainer)
    assert (ref["transaction_id"].to_numpy() == preds["transaction_id"].to_numpy()).all(), "ordre des transactions différent"
    y = preds["is_fraud"].to_numpy().astype(int)
    scores = {k: (ref if k.startswith("baseline") else preds)[f"score_{k}"].to_numpy().astype(float) for k in METHODES}
    seuils = {k: phase3[k]["threshold"] for k in METHODES}

    res = {k: metriques(y, scores[k], seuils[k]) for k in METHODES}
    controle = {lab(k): {"pr_auc_recalcule": round(res[k]["pr_auc"], 4), "pr_auc_phase3": phase3[k]["test"]["pr_auc"],
                         "f1_recalcule": round(res[k]["f1"], 4), "f1_phase3": phase3[k]["test"]["f1"]} for k in METHODES}
    for nom, c in controle.items():
        ok = abs(c["pr_auc_recalcule"] - c["pr_auc_phase3"]) < 6e-4 and abs(c["f1_recalcule"] - c["f1_phase3"]) < 6e-4
        print(f"  contrôle {nom:<22} PR-AUC {c['pr_auc_recalcule']:.4f} / {c['pr_auc_phase3']:.4f}  "
              f"F1 {c['f1_recalcule']:.4f} / {c['f1_phase3']:.4f}  {'OK' if ok else 'ÉCART'}")
        c["identique"] = bool(ok)

    print(f"Bootstrap par usager ({n_boot} tirages)…", flush=True)
    ic = bootstrap(y, scores, seuils, preds["user_id"].to_numpy(), n_boot)

    print("Figures…", flush=True)
    fig_roc(y, scores, res); fig_pr(y, scores, res); fig_barres(res); fig_ic(res, ic); fig_confusion(res); fig_erreurs(res)
    fig_types(phase3); fig_canal(phase3); fig_budget(res); fig_ablation(phase3)
    fig_seuil(y, scores["hybrid"], seuils["hybrid"]); fig_distribution(y, scores["hybrid"], seuils["hybrid"])
    brier = fig_calibration(y, scores["hybrid"]); fig_multicritere(sel)

    json.dump({"n_test": int(len(y)), "n_fraudes": int(y.sum()), "n_boot": n_boot, "controle_reproduction": controle,
               "brier_hybride": brier, "metriques": {lab(k): res[k] for k in METHODES}, "ic95": {lab(k): ic[k] for k in METHODES}},
              open(REPORTS / "figures_comparaison.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    f = lambda v, d=4: f"{v:.{d}f}".replace(".", ",")  # noqa: E731
    md = ["# Métriques complètes des méthodes comparées (test)", "",
          "| Méthode | VP | FP | FN | VN | Précision | Rappel | Spécificité | F1 | F2 | MCC | Exact. équil. | Kappa | PR-AUC | ROC-AUC |",
          "|---|" + "---|" * 14]
    md += [f"| {lab(k)} | {r['VP']} | {r['FP']} | {r['FN']} | {r['VN']} | {f(r['precision'])} | {f(r['rappel'])} | {f(r['specificite'])} | "
           f"{f(r['f1'])} | {f(r['f2'])} | {f(r['mcc'])} | {f(r['exactitude_equilibree'])} | {f(r['kappa'])} | {f(r['pr_auc'])} | {f(r['roc_auc'])} |"
           for k, r in res.items()]
    md += ["", "| Méthode | IC 95 % PR-AUC | IC 95 % précision | IC 95 % rappel | IC 95 % F1 |", "|---|---|---|---|---|"]
    md += [f"| {lab(k)} | " + " | ".join(f"[{f(ic[k][m][0])} ; {f(ic[k][m][1])}]" for m in ("pr_auc", "precision", "rappel", "f1")) + " |" for k in METHODES]
    md += ["", "| Méthode | " + " | ".join(f"Rappel à {f(b * 100, 2)} % FP" for b in BUDGETS) + " |", "|---|" + "---|" * len(BUDGETS)]
    md += [f"| {lab(k)} | " + " | ".join(f(res[k][f'rappel_fpr_{b}']) for b in BUDGETS) + " |" for k in METHODES]
    md += ["", f"Score de Brier de l'hybride : {f(brier, 5)}"]
    (REPORTS / "figures_comparaison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nFigures : {FIG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--reentrainer", action="store_true", help="ré-entraîner les méthodes de référence même si le cache existe")
    a = ap.parse_args()
    main(a.n_boot, a.reentrainer)
