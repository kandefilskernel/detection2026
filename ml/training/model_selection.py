"""Étude comparative des méthodes d'apprentissage et choix du modèle retenu (mémoire, § II.2.9).

    1. Performances des 8 méthodes sur la période de TEST (même jeu, seuils choisis sur la validation)
    2. Significativité : hybride contre chacune de ses composantes (bootstrap apparié par usager + McNemar exact),
       et rappel des écarts XGBoost / autres familles (évaluation H3)
    3. Erreurs au seuil retenu (fausses alertes, fraudes manquées) et rappel par typologie
    4. Matrice de décision multicritère, robustesse de la décision à la pondération (tirages de Dirichlet)

Entrées  : ml/reports/phase3_results.json, ml/reports/test_predictions.csv (train_model.py),
           ml/reports/research_evaluation.json (research_evaluation.py), ml/reports/realtime_replay.json,
           ml/reports/physics_evaluation.json
Sorties  : ml/reports/model_selection.md, ml/reports/model_selection.json,
           ml/reports/figures/comparaison_modeles.png, ml/reports/figures/courbes_precision_rappel.png,
           ml/artifacts/model_selection.json (lu par le tableau de bord)

Usage : python -m ml.training.model_selection [--n-boot 1000]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import precision_recall_curve

from ml.training.significance import METRICS, mcnemar_exact, paired_bootstrap

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "ml" / "reports"
FIGURES = REPORTS / "figures"
ARTIFACTS = ROOT / "ml" / "artifacts"

# clé dans phase3_results.json -> (libellé, famille, colonne de score dans test_predictions.csv ou None)
METHODS = {
    "hybrid": ("Hybride", "Empilement (XGBoost + LSTM + autoencodeur)", "score_hybrid"),
    "branch_xgboost": ("XGBoost", "Ensemble d'arbres (boosting)", "score_branch_xgboost"),
    "branch_lstm_attention": ("LSTM-attention", "Réseau récurrent", "score_branch_lstm_attention"),
    "baseline_random_forest": ("Random Forest", "Ensemble d'arbres (bagging)", None),
    "baseline_logreg": ("Régression logistique", "Linéaire", None),
    "branch_autoencoder": ("Autoencodeur", "Anomalie (non supervisé)", "score_branch_autoencoder"),
    "baseline_isolation_forest": ("Isolation Forest", "Anomalie (non supervisé)", None),
    "baseline_rules": ("Règles métier", "Système expert", None),
}
H3_KEYS = {"random_forest": "Random Forest", "regression_logistique": "Régression logistique",
           "isolation_forest": "Isolation Forest", "regles_metier": "Règles métier"}

# Critères fixés avant l'expérimentation (poids = importance pour le métier). Les deux premiers sont notés
# automatiquement à partir des mesures ; les quatre autres sont des appréciations justifiées (JUSTIFICATIONS).
CRITERIA = {"pr_auc": ("PR-AUC", 0.30), "f1": ("F1 / fausses alertes", 0.20),
            "explicabilite": ("Explicabilité", 0.15), "temps_reel": ("Temps réel et simplicité", 0.15),
            "dynamique": ("Dynamique (séquence)", 0.10), "inedit": ("Fraudes inédites", 0.10)}
QUALITATIVE = {  # explicabilité, temps réel, dynamique, inédit (1 = faible, 5 = excellent)
    "hybrid": (4, 3, 5, 4), "branch_xgboost": (4, 5, 2, 1), "branch_lstm_attention": (2, 3, 5, 2),
    "baseline_random_forest": (3, 4, 1, 1), "baseline_logreg": (5, 5, 1, 1),
    "branch_autoencoder": (2, 4, 1, 5), "baseline_isolation_forest": (2, 4, 1, 4), "baseline_rules": (5, 5, 1, 2),
}
JUSTIFICATIONS = {
    "explicabilite": "règles et régression logistique transparentes (5) ; TreeSHAP exact pour XGBoost, conservé par "
                     "l'hybride avec la contribution des composantes et l'attention (4) ; Random Forest (3) ; "
                     "attention seule ou score d'anomalie global (2)",
    "temps_reel": "modèles linéaires et arbres très rapides (4-5) ; LSTM et hybride plus coûteux en calcul et en "
                  "maintenance (3)",
    "dynamique": "seuls le LSTM et l'hybride lisent la séquence des opérations (5) ; XGBoost n'en voit qu'un résumé "
                 "par les variables de fréquence (2)",
    "inedit": "autoencodeur et Isolation Forest apprennent sans étiquette (5, 4) ; l'hybride hérite de l'autoencodeur "
              "et des lois physiques (4) ; méthodes supervisées limitées aux fraudes connues (1)",
}
PR_AUC_BINS = [(0.995, 5), (0.98, 4), (0.94, 3), (0.6, 2)]
F1_BINS = [(0.96, 5), (0.93, 4), (0.85, 3), (0.6, 2)]


def to_score(value: float, bins: list[tuple[float, int]]) -> int:
    return next((s for t, s in bins if value >= t), 1)


def fmt(x: float, d: int = 4) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def fmt_signed(x: float) -> str:
    return ("+" if x >= 0 else "−") + fmt(abs(x))


def fmt_p(p: float) -> str:
    if p >= 1e-3:
        return fmt(p, 3)
    m, e = f"{p:.1e}".split("e")
    return f"{m.replace('.', ',')} × 10^{int(e)}"


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def plot_comparison(rows: list[dict], path: Path) -> None:
    rows = sorted(rows, key=lambda r: r["pr_auc"])
    fig, ax = plt.subplots(figsize=(8, 4.6))
    yy, h = np.arange(len(rows)), 0.38
    ax.barh(yy + h / 2, [r["pr_auc"] for r in rows], h, label="PR-AUC", color="#2563EB")
    ax.barh(yy - h / 2, [r["f1"] for r in rows], h, label="F1 (seuil retenu)", color="#94A3B8")
    for i, r in enumerate(rows):
        ax.text(r["pr_auc"] + 0.005, i + h / 2, f"{r['pr_auc']:.3f}", va="center", fontsize=8)
    ax.set_yticks(yy, [r["label"] for r in rows]); ax.set_xlim(0, 1.08)
    ax.set_xlabel("Score sur la période de test"); ax.legend(loc="lower right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False); ax.set_title("Comparaison des méthodes d'apprentissage")
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def plot_pr_curves(y: np.ndarray, scores: dict[str, np.ndarray], pr_auc: dict[str, float], path: Path) -> None:
    colors = {"hybrid": "#2563EB", "branch_xgboost": "#F59E0B", "branch_lstm_attention": "#10B981",
              "branch_autoencoder": "#94A3B8"}
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    for key, s in scores.items():
        p, r, _ = precision_recall_curve(y, s)
        ax.plot(r, p, color=colors[key], lw=1.6, label=f"{METHODS[key][0]} (PR-AUC {pr_auc[key]:.4f})")
    ax.set_xlabel("Rappel"); ax.set_ylabel("Précision"); ax.set_ylim(0, 1.02); ax.legend(loc="lower left", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False); ax.set_title("Courbes précision-rappel (test)")
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def main(n_boot: int = 1000) -> dict:
    FIGURES.mkdir(parents=True, exist_ok=True)
    phase3 = json.loads((REPORTS / "phase3_results.json").read_text(encoding="utf-8"))["results"]
    preds = pd.read_csv(REPORTS / "test_predictions.csv")
    y, users = preds.is_fraud.to_numpy(), preds.user_id.to_numpy()

    # ------------------------------------------------------------- 1. performances
    rows = []
    for key, (label, family, _) in METHODS.items():
        t = phase3[key]["test"]
        rows.append({"key": key, "label": label, "family": family, "pr_auc": t["pr_auc"], "roc_auc": t["roc_auc"],
                     "precision": t["precision"], "recall": t["recall"], "f1": t["f1"],
                     "false_positive_rate": t["false_positive_rate"], "threshold": phase3[key]["threshold"]})

    # ------------------------------------------------------------- 2. significativité (hybride vs composantes)
    scored = {k: preds[c].to_numpy() for k, (_, _, c) in METHODS.items() if c}
    boot = paired_bootstrap(y, scored, users, reference="hybrid", n_boot=n_boot, seed=42,
                            metrics={"pr_auc": METRICS["pr_auc"]})
    pred = {k: (s >= phase3[k]["threshold"]).astype(int) for k, s in scored.items()}
    significance = []
    for k in scored:
        if k == "hybrid":
            continue
        b = boot[k]["pr_auc"]   # différence modèle - hybride : on l'inverse pour lire « hybride - modèle »
        mc = mcnemar_exact(y, pred["hybrid"], pred[k])
        n_disc = mc["only_a_correct"] + mc["only_b_correct"]  # p exacte, sans l'arrondi à 6 décimales
        p_exact = float(binomtest(mc["only_a_correct"], n_disc, 0.5).pvalue) if n_disc else 1.0
        significance.append({"versus": METHODS[k][0], "diff_pr_auc": round(-b["diff_vs_reference"], 4),
                             "ci95": [round(-b["diff_ci95"][1], 4), round(-b["diff_ci95"][0], 4)],
                             "significant_95": b["significant_95"], "mcnemar_hybride_seul_juste": mc["only_a_correct"],
                             "mcnemar_autre_seul_juste": mc["only_b_correct"], "mcnemar_p": p_exact})
    h3 = []
    research = REPORTS / "research_evaluation.json"
    if research.exists():
        tg = json.loads(research.read_text(encoding="utf-8"))["H3"]["test_global"]
        for k, label in H3_KEYS.items():
            if k in tg and "diff_ci95" in tg[k]["pr_auc"]:
                p = tg[k]["pr_auc"]
                h3.append({"versus": label, "diff_pr_auc": round(-p["diff_vs_reference"], 4),
                           "ci95": [round(-p["diff_ci95"][1], 4), round(-p["diff_ci95"][0], 4)],
                           "significant_95": p["significant_95"]})

    # ------------------------------------------------------------- 3. erreurs et typologies
    errors = {METHODS[k][0]: {"fausses_alertes": int(((p == 1) & (y == 0)).sum()),
                              "fraudes_manquees": int(((p == 0) & (y == 1)).sum())} for k, p in pred.items()}
    fraud = preds.is_fraud == 1
    by_type = {}
    for ftype, idx in preds[fraud].groupby("fraud_type").groups.items():
        by_type[ftype] = {"n": int(len(idx)), **{METHODS[k][0]: round(float(p[idx].mean()), 4) for k, p in pred.items()}}

    # ------------------------------------------------------------- 4. décision multicritère
    weights = np.array([w for _, w in CRITERIA.values()])
    matrix = {}
    for r in rows:
        notes = [to_score(r["pr_auc"], PR_AUC_BINS), to_score(r["f1"], F1_BINS), *QUALITATIVE[r["key"]]]
        r["notes"] = dict(zip(CRITERIA, notes))
        r["weighted_score"] = round(float(np.dot(notes, weights)), 2)
        r["equal_weight_score"] = round(float(np.mean(notes)), 2)
        matrix[r["key"]] = notes
    keys, A = list(matrix), np.array(list(matrix.values()), dtype=float)
    rng, n_draws = np.random.default_rng(1), 2000
    wins = np.bincount([int(np.argmax(A @ rng.dirichlet(np.ones(len(CRITERIA))))) for _ in range(n_draws)],
                       minlength=len(keys))
    for r in rows:
        r["rank1_share"] = round(float(wins[keys.index(r["key"])] / n_draws), 4)
    rows.sort(key=lambda r: -r["weighted_score"])
    chosen = rows[0]

    replay = REPORTS / "realtime_replay.json"
    latency = json.loads(replay.read_text(encoding="utf-8"))["_meta"] if replay.exists() else {}
    physics = REPORTS / "physics_evaluation.json"
    relay = (json.loads(physics.read_text(encoding="utf-8"))["D_attaque_session_relayee"]["rappel"]
             if physics.exists() else {})

    hyb_err, xgb_err = errors["Hybride"], errors["XGBoost"]
    reasons = [
        f"meilleure PR-AUC ({fmt(chosen['pr_auc'])}) et meilleur F1 ({fmt(chosen['f1'], 3)}) sur la période de test",
        "supériorité significative sur chacune des composantes seules (IC 95 % excluant 0, McNemar p < 0,05)"
        if all(s["significant_95"] and s["mcnemar_p"] < 0.05 for s in significance) else
        "supériorité non significative sur au moins une composante : voir le tableau de significativité",
        f"{100 * (1 - hyb_err['fausses_alertes'] / xgb_err['fausses_alertes']):.0f} % de fausses alertes et "
        f"{100 * (1 - hyb_err['fraudes_manquees'] / xgb_err['fraudes_manquees']):.0f} % de fraudes manquées en moins "
        "que XGBoost seul",
        "couvre le profil instantané (XGBoost), la dynamique (LSTM) et l'anomalie (autoencodeur)",
        "reste explicable (TreeSHAP, contribution des composantes, attention) et compatible avec le temps réel",
    ]
    out = {
        "n_test": int(len(preds)), "n_fraud_test": int(y.sum()), "n_boot": n_boot,
        "criteria": [{"key": k, "label": lab, "weight": w} for k, (lab, w) in CRITERIA.items()],
        "justifications": JUSTIFICATIONS, "methods": rows, "significance": significance, "h3_xgboost_vs": h3,
        "errors": errors, "recall_by_type": by_type, "sensitivity_draws": n_draws,
        "latency_ms": {k.replace("latence_", "").replace("_ms", ""): v for k, v in latency.items() if "latence" in k},
        "relay_attack_recall": relay,
        "decision": {"key": chosen["key"], "label": chosen["label"], "weighted_score": chosen["weighted_score"],
                     "runner_up": rows[1]["label"], "runner_up_score": rows[1]["weighted_score"],
                     "rank1_share": chosen["rank1_share"], "reasons": reasons},
    }

    # ------------------------------------------------------------- figures et rapport
    plot_comparison(rows, FIGURES / "comparaison_modeles.png")
    plot_pr_curves(y, scored, {k: next(r["pr_auc"] for r in rows if r["key"] == k) for k in scored},
                   FIGURES / "courbes_precision_rappel.png")

    L = ["# Étude comparative des méthodes d'apprentissage et choix du modèle", "",
         f"Période de test jamais vue à l'entraînement : {fmt_int(len(preds))} transactions, {fmt_int(int(y.sum()))} fraudes. "
         "Seuils choisis sur la validation. **Données simulées.**", "",
         "## 1. Performances", "",
         "| Méthode | Famille | PR-AUC | ROC-AUC | Précision | Rappel | F1 | Taux de FP |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -r["pr_auc"]):
        L.append(f"| {r['label']} | {r['family']} | {fmt(r['pr_auc'])} | {fmt(r['roc_auc'])} | {fmt(r['precision'], 3)} | "
                 f"{fmt(r['recall'], 3)} | {fmt(r['f1'], 3)} | {fmt(100 * r['false_positive_rate'], 3)} % |")
    L += ["", "Figures : `figures/comparaison_modeles.png`, `figures/courbes_precision_rappel.png`.", "",
          f"## 2. Significativité (bootstrap apparié par usager, {fmt_int(n_boot)} tirages ; McNemar exact)", "",
          "| Comparaison | Écart de PR-AUC [IC 95 %] | McNemar (seul juste) | p | Significatif |", "|---|---|---|---|---|"]
    for s in significance:
        L.append(f"| Hybride − {s['versus']} | {fmt_signed(s['diff_pr_auc'])} [{fmt_signed(s['ci95'][0])} ; {fmt_signed(s['ci95'][1])}] | "
                 f"{s['mcnemar_hybride_seul_juste']} contre {s['mcnemar_autre_seul_juste']} | {fmt_p(s['mcnemar_p'])} | "
                 f"{'oui' if s['significant_95'] and s['mcnemar_p'] < 0.05 else 'non'} |")
    for s in h3:
        L.append(f"| XGBoost − {s['versus']} | {fmt_signed(s['diff_pr_auc'])} [{fmt_signed(s['ci95'][0])} ; {fmt_signed(s['ci95'][1])}] | — | — | "
                 f"{'oui' if s['significant_95'] else 'non'} |")
    L += ["", "## 3. Erreurs au seuil retenu", "", "| Méthode | Fausses alertes | Fraudes manquées |", "|---|---|---|"]
    L += [f"| {k} | {v['fausses_alertes']} | {v['fraudes_manquees']} |" for k, v in errors.items()]
    names = [METHODS[k][0] for k in pred]
    L += ["", "## 4. Rappel par typologie", "", "| Typologie | n | " + " | ".join(names) + " |",
          "|---|---|" + "---|" * len(names)]
    for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]["n"]):
        L.append(f"| {t} | {v['n']} | " + " | ".join(fmt(v[n], 3) for n in names) + " |")
    L += ["", "## 5. Matrice de décision multicritère (notes de 1 à 5)", "",
          "| Méthode | " + " | ".join(f"{lab} ({100 * w:.0f} %)" for lab, w in CRITERIA.values())
          + " | Score pondéré | Poids égaux | 1er sur tirages |", "|---|" + "---|" * (len(CRITERIA) + 3)]
    for r in rows:
        L.append(f"| {r['label']} | " + " | ".join(str(n) for n in r["notes"].values())
                 + f" | **{fmt(r['weighted_score'], 2)}** | {fmt(r['equal_weight_score'], 2)} | {100 * r['rank1_share']:.0f} % |")
    L += ["", "Notes de PR-AUC et de F1 calculées à partir des mesures (seuils "
          f"{PR_AUC_BINS} et {F1_BINS}). Justification des autres notes :", ""]
    L += [f"- **{CRITERIA[k][0]}** : {v}." for k, v in JUSTIFICATIONS.items()]
    L += ["", f"Robustesse : {fmt_int(n_draws)} pondérations tirées au hasard (Dirichlet) ; colonne « 1er sur tirages ».", "",
          "## 6. Décision", "", f"**Modèle retenu : {chosen['label']}** (score {fmt(chosen['weighted_score'], 2)} / 5, "
          f"contre {fmt(rows[1]['weighted_score'], 2)} pour {rows[1]['label']}).", ""]
    L += [f"{i}. {r}" for i, r in enumerate(reasons, 1)]
    if latency:
        L += ["", f"Latence de bout en bout (rejeu) : médiane {fmt(latency['latence_p50_ms'], 1)} ms, "
              f"95ᵉ centile {fmt(latency['latence_p95_ms'], 1)} ms."]
    if relay:
        L += [f"Attaque par relais inédite : rappel {fmt(100 * relay.get('modele_de_donnees (seuil F1)', 0), 1)} % pour le modèle de "
              f"données seul, {fmt(100 * relay.get('hybride (donnees OU physique)', 0), 0)} % avec les lois physiques."]

    (REPORTS / "model_selection.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    for path in (REPORTS / "model_selection.json", ARTIFACTS / "model_selection.json"):
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-boot", type=int, default=1000)
    main(ap.parse_args().n_boot)
