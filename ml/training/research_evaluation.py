"""
Évaluation de recherche : teste les hypothèses H1-H4 et répond aux questions RQ1-RQ5.

Chaque conclusion repose sur un intervalle de confiance (bootstrap apparié par usager)
ou un test d'hypothèse, jamais sur un point isolé. Protocole commun :
    - split TEMPOREL (train / early_stop / val / test), identique à la phase 3
    - seuil de décision choisi sur la VALIDATION uniquement ; test évalué une seule fois
    - le modèle contrôlé est XGBoost (un seul facteur change à la fois : les variables
      ou les données d'entraînement) ; l'hybride complet reste évalué par train_model.py

    H1  Le profilage comportemental bat l'approche statique
        - règles métier (seuils fixes) et XGBoost SANS historique de l'usager (« statique »)
          contre XGBoost avec les variables de profilage ; différences + IC95 + McNemar
    H2  Les variables temporelles, fréquentielles et contextuelles discriminent
        - ablation « retirer une famille » et « ajouter une famille à un socle »
        - AUC univariée de chaque variable (et alerte de fuite d'information si AUC > 0,97)
    H3  Les performances varient selon la famille de modèles et les variables
        - règles, régression logistique, Random Forest, Isolation Forest, XGBoost,
          avec IC95 ; variance selon la graine d'entraînement
    H4  Transposition Mobile Money -> carte Visa virtuelle
        - entraînement sur Mobile Money SEUL puis test sur la Visa (sans réentraîner),
          avec une variante limitée aux variables communes aux deux canaux
        - adaptation avec 5 % / 20 % des données Visa, référence Visa seule et mixte
        - sens inverse (Visa -> Mobile Money)

Usage (depuis la racine du projet) :
    python -m ml.training.research_evaluation           # complet
    python -m ml.training.research_evaluation --quick   # essai rapide
Sorties : ml/reports/research_evaluation.json et research_evaluation.md
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from ml.features.feature_engineering import (FEATURE_GROUPS, FEATURE_NAMES, PROCESSED_DIR,
                                             load_or_build_features)
from ml.models.baselines import (isolation_score, rule_based_score, train_isolation_forest,
                                 train_logistic_regression, train_random_forest)
from ml.models.xgboost_branch import train_xgboost_branch, xgb_logit
from ml.preprocessing.train_test_split_normalize import CLIP, temporal_split
from ml.training.evaluation import best_f1_threshold, evaluate, recall_by_fraud_type
from ml.training.significance import mcnemar_exact, paired_bootstrap

REPORTS_DIR = Path("ml/reports")
LEAK_AUC = 0.97  # une seule variable aussi discriminante est suspecte (fuite ou simulation triviale)

# Variables calculables SANS historique de l'usager : le « statique » (H1).
STATIC_FEATURES = (
    ["log_amount_usd", "amount_to_balance", "is_near_full_drain", "amount_to_kyc_limit",
     "log_balance_before", "is_smartphone", "access_app", "access_ussd", "access_agent",
     "is_foreign_ip", "hour_sin", "hour_cos", "is_night", "is_weekend", "is_month_end",
     "is_high_risk_merchant", "is_foreign_merchant", "is_card"]
    + FEATURE_GROUPS["kyc_profile"] + FEATURE_GROUPS["tx_type"]
)
# Familles comportementales (H2) ; « socle » = ce qui décrit le client et le type d'opération
FAMILIES = {
    "temporelles": FEATURE_GROUPS["temporal"],
    "fréquentielles": FEATURE_GROUPS["velocity"],
    "contextuelles": FEATURE_GROUPS["device"] + FEATURE_GROUPS["location"] + FEATURE_GROUPS["counterparty"],
    "montants": FEATURE_GROUPS["amount"],
}
BASE = FEATURE_GROUPS["kyc_profile"] + FEATURE_GROUPS["tx_type"] + FEATURE_GROUPS["cross_channel"]
# Variables qui n'existent que pour la carte (exclues du test de transfert « variables communes »)
CARD_ONLY = ["is_card", "type_CARD_TOPUP", "type_CARD_PURCHASE", "log_mins_since_topup",
             "purchase_to_topup_ratio"]

CH_MM, CH_VISA = "MOBILE_MONEY", "VISA_VIRTUAL"
IDX = {n: i for i, n in enumerate(FEATURE_NAMES)}


def log(msg: str) -> None:
    print(msg, flush=True)


def cols(names: list[str]) -> list[int]:
    missing = [n for n in names if n not in IDX]
    assert not missing, f"variables inconnues : {missing}"
    return sorted({IDX[n] for n in names})


def _py(o):
    if isinstance(o, dict):
        return {str(k): _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_py(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    return o


class Study:
    def __init__(self, quick: bool):
        self.quick = quick
        self.n_est = 120 if quick else 600
        self.n_boot = 60 if quick else 300
        self.seeds = [42, 7] if quick else [42, 7, 13, 21, 99]
        cache = PROCESSED_DIR / "features.csv"
        table = (pd.read_csv(cache, parse_dates=["timestamp"], low_memory=False) if cache.exists()
                 else load_or_build_features(cache_path=cache))
        table["timestamp"] = pd.to_datetime(table["timestamp"])
        assert table["timestamp"].is_monotonic_increasing, "features.csv doit être chronologique"
        self.table = table
        self.split, self.bounds = temporal_split(table["timestamp"])
        self.X = table[FEATURE_NAMES].to_numpy(dtype=np.float32)
        self.y = table["is_fraud"].to_numpy(dtype=np.int8)
        self.channel = table["channel"].to_numpy()
        self.users = table["user_id"].to_numpy()
        self.ftype = table["fraud_type"].to_numpy()
        self.scores: dict[str, np.ndarray] = {}
        self.thr: dict[str, float] = {}
        s = self.split
        self.fit, self.es, self.val, self.test = (s == 0), (s == 1), (s == 2), (s == 3)
        self.mm, self.visa = self.channel == CH_MM, self.channel == CH_VISA
        self.rng = np.random.default_rng(0)

    # ------------------------------------------------------------------ modèles
    def fit_xgb(self, name: str, features: list[str], fit: np.ndarray, es: np.ndarray, seed: int = 42,
                val: np.ndarray | None = None) -> None:
        c = cols(features)
        model = train_xgboost_branch(self.X[fit][:, c], self.y[fit], self.X[es][:, c], self.y[es],
                                     n_estimators=self.n_est, seed=seed)
        self.scores[name] = xgb_logit(model, self.X[:, c])
        v = self.val if val is None else val
        self.thr[name] = best_f1_threshold(self.y[v], self.scores[name][v])

    def set_scores(self, name: str, s: np.ndarray, val: np.ndarray | None = None) -> None:
        self.scores[name] = s.astype(np.float32)
        v = self.val if val is None else val
        self.thr[name] = best_f1_threshold(self.y[v], self.scores[name][v])

    # ------------------------------------------------------------------ évaluation
    def compare(self, names: list[str], mask: np.ndarray, reference: str | None = None,
                n_boot: int | None = None, thresholds: dict[str, float] | None = None) -> dict:
        """IC95 appariés + métriques opérationnelles de chaque modèle sur `mask`."""
        thresholds = thresholds or self.thr
        y, g = self.y[mask], self.users[mask]
        sc = {n: self.scores[n][mask] for n in names}
        boot = paired_bootstrap(y, sc, g, reference=reference, n_boot=n_boot or self.n_boot)
        for n in names:
            boot[n]["operational"] = evaluate(y, sc[n], thresholds[n])
        return boot

    def mcnemar(self, a: str, b: str, mask: np.ndarray) -> dict:
        y = self.y[mask]
        return mcnemar_exact(y, self.scores[a][mask] >= self.thr[a], self.scores[b][mask] >= self.thr[b])

    # ------------------------------------------------------------------ RQ1 / RQ2 : descriptif
    def descriptive(self) -> dict:
        t = self.table
        out = {}
        for ch in (CH_MM, CH_VISA):
            d = t[t.channel == ch]
            leg, fr = d[d.is_fraud == 0], d[d.is_fraud == 1]
            row = lambda f: {"legitime": round(float(f(leg)), 4), "fraude": round(float(f(fr)), 4)}  # noqa: E731
            out[ch] = {
                "n": int(len(d)), "n_fraud": int(len(fr)), "fraud_rate": round(float(d.is_fraud.mean()), 5),
                "montant_median_usd": row(lambda x: x.amount_usd.median()),
                "part_nuit": row(lambda x: x.is_night.mean()),
                "part_nouvel_appareil": row(lambda x: x.is_new_device.mean()),
                "part_ip_etrangere": row(lambda x: x.is_foreign_ip.mean()),
                "part_nouveau_destinataire": row(lambda x: x.is_new_counterparty.mean()),
                "part_vidage_du_solde": row(lambda x: x.is_near_full_drain.mean()),
                "ratio_montant_habitude_median": row(lambda x: np.expm1(x.amount_ratio_user_mean.median())),
                "tx_24h_median": row(lambda x: x.tx_count_24h.median()),
                "melange_types": {k: round(float(v), 4) for k, v in
                                  d.tx_type.value_counts(normalize=True).items()},
            }
        return out

    def univariate(self) -> dict:
        train = self.fit | self.es
        out = {}
        for ch, m in ((CH_MM, self.mm), (CH_VISA, self.visa), ("TOUS", np.ones_like(self.mm))):
            rows = train & m
            res = []
            for name, i in IDX.items():
                x = self.X[rows, i]
                auc = 0.5 if np.ptp(x) == 0 else float(roc_auc_score(self.y[rows], x))
                res.append({"variable": name, "auc": round(auc, 4), "separation": round(max(auc, 1 - auc), 4),
                            "sens": "+" if auc >= 0.5 else "-"})
            res.sort(key=lambda r: -r["separation"])
            out[ch] = {"top": res[:15], "suspects_fuite": [r for r in res if r["separation"] > LEAK_AUC]}
        return out

    # ------------------------------------------------------------------ H1
    def h1(self) -> dict:
        log("[H1] profilage comportemental vs statique")
        self.set_scores("regles_metier", rule_based_score(self.X))
        for seed in self.seeds:
            self.fit_xgb(f"statique_s{seed}", STATIC_FEATURES, self.fit, self.es, seed)
            self.fit_xgb(f"profilage_s{seed}", FEATURE_NAMES, self.fit, self.es, seed)
        self.scores["profilage"], self.thr["profilage"] = self.scores["profilage_s42"], self.thr["profilage_s42"]
        self.scores["statique"], self.thr["statique"] = self.scores["statique_s42"], self.thr["statique_s42"]
        names = ["profilage", "statique", "regles_metier"]
        res = {"test_global": self.compare(names, self.test, reference="profilage"),
               "test_mobile_money": self.compare(names, self.test & self.mm, reference="profilage"),
               "test_visa_virtual": self.compare(names, self.test & self.visa, reference="profilage"),
               "mcnemar_profilage_vs_statique": self.mcnemar("profilage", "statique", self.test),
               "mcnemar_profilage_vs_regles": self.mcnemar("profilage", "regles_metier", self.test)}
        by_seed = {}
        for kind in ("profilage", "statique"):
            vals = []
            for seed in self.seeds:
                n = f"{kind}_s{seed}"
                vals.append(evaluate(self.y[self.test], self.scores[n][self.test], self.thr[n])["pr_auc"])
            by_seed[kind] = {"pr_auc_par_graine": vals, "moyenne": round(float(np.mean(vals)), 4),
                             "ecart_type": round(float(np.std(vals)), 4)}
        res["variance_graines"] = by_seed
        res["recall_par_typologie"] = {
            n: recall_by_fraud_type(self.y[self.test], self.scores[n][self.test], self.thr[n],
                                    self.ftype[self.test]) for n in names}
        return res

    # ------------------------------------------------------------------ H2
    def h2(self) -> dict:
        log("[H2] ablation par famille de variables")
        base_cols = set(BASE)
        names = ["profilage"]
        for fam, feats in FAMILIES.items():
            self.fit_xgb(f"sans_{fam}", [f for f in FEATURE_NAMES if f not in set(feats)], self.fit, self.es)
            self.fit_xgb(f"socle+{fam}", sorted(base_cols | set(feats)), self.fit, self.es)
            names += [f"sans_{fam}", f"socle+{fam}"]
        self.fit_xgb("socle_seul", sorted(base_cols), self.fit, self.es)
        names.append("socle_seul")
        return {"familles": {k: v for k, v in FAMILIES.items()},
                "socle": BASE,
                "test_global": self.compare(names, self.test, reference="profilage", n_boot=max(self.n_boot // 2, 40)),
                "univariee": self.univariate()}

    # ------------------------------------------------------------------ H3
    def h3(self) -> dict:
        log("[H3] familles de modèles")
        train = self.fit | self.es
        sc = StandardScaler().fit(self.X[train])
        Xs = np.clip(sc.transform(self.X), -CLIP, CLIP).astype(np.float32)
        lr = train_logistic_regression(Xs[self.fit], self.y[self.fit])
        self.set_scores("regression_logistique", lr.decision_function(Xs))
        log("  random forest...")
        rf = train_random_forest(self.X[self.fit], self.y[self.fit]) if not self.quick else \
            train_random_forest(self.X[self.fit][::4], self.y[self.fit][::4])
        self.set_scores("random_forest", rf.predict_proba(self.X)[:, 1])
        iso = train_isolation_forest(Xs[self.fit & (self.y == 0)])
        self.set_scores("isolation_forest", isolation_score(iso, Xs))
        self.scores["xgboost"], self.thr["xgboost"] = self.scores["profilage"], self.thr["profilage"]
        names = ["xgboost", "random_forest", "regression_logistique", "isolation_forest", "regles_metier"]
        return {"test_global": self.compare(names, self.test, reference="xgboost"),
                "test_mobile_money": self.compare(names, self.test & self.mm, reference="xgboost"),
                "test_visa_virtual": self.compare(names, self.test & self.visa, reference="xgboost")}

    # ------------------------------------------------------------------ H4
    def h4(self) -> dict:
        log("[H4] transposition Mobile Money -> Visa virtuelle")
        common = [f for f in FEATURE_NAMES if f not in CARD_ONLY]
        mm_fit, mm_es = self.fit & self.mm, self.es & self.mm
        v_fit, v_es = self.fit & self.visa, self.es & self.visa
        self.fit_xgb("mm_seul", FEATURE_NAMES, mm_fit, mm_es, val=self.val & self.mm)
        self.fit_xgb("mm_seul_vars_communes", common, mm_fit, mm_es, val=self.val & self.mm)
        self.fit_xgb("visa_seule", FEATURE_NAMES, v_fit, v_es, val=self.val & self.visa)
        for frac in (0.05, 0.20):
            pick = lambda m: m & (self.rng.random(len(m)) < frac)  # noqa: E731
            self.fit_xgb(f"mm+{int(frac * 100)}%visa", FEATURE_NAMES, mm_fit | pick(v_fit), mm_es | pick(v_es),
                         val=self.val)
        # « mixte » = le modèle de profilage entraîné sur les deux canaux (référence en domaine)
        self.scores["mixte"], self.thr["mixte"] = self.scores["profilage"], self.thr["profilage"]
        models = ["mm_seul", "mm_seul_vars_communes", "mm+5%visa", "mm+20%visa", "visa_seule", "mixte",
                  "regles_metier"]
        vt = self.test & self.visa
        # seuil « honnête » (appris sur le Mobile Money) et seuil recalibré sur la Visa (oracle)
        thr_visa = {n: best_f1_threshold(self.y[self.val & self.visa], self.scores[n][self.val & self.visa])
                    for n in models}
        on_visa = self.compare(models, vt, reference="mixte")
        for n in models:
            on_visa[n]["operational_seuil_recalibre_visa"] = evaluate(self.y[vt], self.scores[n][vt], thr_visa[n])
        mt = self.test & self.mm
        on_mm = self.compare(["mixte", "mm_seul", "visa_seule", "regles_metier"], mt, reference="mixte")
        prev = float(self.y[vt].mean())
        zero = on_visa["mm_seul"]["pr_auc"]["point"]
        ref = on_visa["mixte"]["pr_auc"]["point"]
        ratio = zero / ref if ref else float("nan")
        return {
            "prevalence_visa_test": round(prev, 5), "n_fraud_visa_test": int(self.y[vt].sum()),
            "variables_communes_exclues": CARD_ONLY,
            "sur_visa_test": on_visa, "sur_mobile_money_test": on_mm,
            "ratio_transfert_pr_auc": round(ratio, 4),
            "niveau_transposabilite": ("forte" if ratio >= 0.9 else "partielle" if ratio >= 0.6 else "faible"),
            "gain_par_rapport_a_l_aleatoire": round(zero / prev, 1),
        }


def md_table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def ci(m: dict, key: str = "pr_auc") -> str:
    d = m[key]
    return f"{d['point']:.4f} [{d['ci95'][0]:.4f} ; {d['ci95'][1]:.4f}]"


def diff(m: dict, key: str = "pr_auc") -> str:
    d = m[key]
    if "diff_vs_reference" not in d:
        return "réf."
    flag = "significatif" if d["significant_95"] else "non significatif"
    return f"{d['diff_vs_reference']:+.4f} [{d['diff_ci95'][0]:+.4f} ; {d['diff_ci95'][1]:+.4f}] ({flag})"


def build_markdown(R: dict) -> str:
    h1, h2, h3, h4 = R["H1"], R["H2"], R["H3"], R["H4"]
    L = ["# Évaluation de recherche : profilage comportemental (Mobile Money RDC et Visa virtuelle)", "",
         f"Données : {R['data']['n']:,} transactions synthétiques, période {R['data']['bounds']['start'][:10]} "
         f"→ {R['data']['bounds']['end'][:10]}, test = {R['data']['bounds']['test_from'][:10]} → fin "
         f"({R['data']['n_test']:,} transactions, {R['data']['n_test_fraud']} fraudes).",
         "Les intervalles [IC95] sont des bootstraps appariés par usager ; les seuils sont choisis sur la "
         "validation. **Les données sont simulées : les résultats mesurent la capacité à retrouver des "
         "fraudes injectées, pas la fraude réelle.**", ""]

    # ---- H1
    g = h1["test_global"]
    L += ["## H1 — Le profilage comportemental améliore la détection par rapport aux approches statiques", "",
          "« Statique » = règles métier à seuils fixes, et XGBoost limité aux variables calculables sans "
          "historique de l'usager. « Profilage » = XGBoost avec toutes les variables comportementales.", "",
          md_table(["Modèle", "PR-AUC [IC95]", "Δ PR-AUC vs profilage", "Rappel à 1 % FP [IC95]"],
                   [[n, ci(g[n]), diff(g[n]), ci(g[n], "recall_at_1pct_fpr")]
                    for n in ("profilage", "statique", "regles_metier")]), ""]
    mc1, mc2 = h1["mcnemar_profilage_vs_statique"], h1["mcnemar_profilage_vs_regles"]
    L += [f"McNemar au seuil opérationnel : profilage vs statique p = {mc1['p_value']} ; "
          f"profilage vs règles p = {mc2['p_value']}.", ""]
    vs = h1["variance_graines"]
    L += [f"Variance selon la graine : profilage {vs['profilage']['moyenne']} ± {vs['profilage']['ecart_type']}, "
          f"statique {vs['statique']['moyenne']} ± {vs['statique']['ecart_type']} (PR-AUC test).", ""]
    ok1 = (g["statique"]["pr_auc"]["significant_95"] and g["statique"]["pr_auc"]["diff_vs_reference"] < 0
           and g["regles_metier"]["pr_auc"]["significant_95"] and g["regles_metier"]["pr_auc"]["diff_vs_reference"] < 0)
    L += [f"**Conclusion H1 : {'CONFIRMÉE' if ok1 else 'NON CONFIRMÉE'} sur ces données** "
          "(le profilage est significativement supérieur aux deux approches statiques)." if ok1 else
          "**Conclusion H1 : NON CONFIRMÉE** (au moins une approche statique n'est pas significativement battue).", ""]
    L += ["Rappel par typologie de fraude (test) :", "",
          md_table(["Typologie", "n", "Profilage", "Statique", "Règles"],
                   [[t, h1["recall_par_typologie"]["profilage"][t]["n"]] +
                    [h1["recall_par_typologie"][m].get(t, {}).get("recall", "-")
                     for m in ("profilage", "statique", "regles_metier")]
                    for t in sorted(h1["recall_par_typologie"]["profilage"])]), ""]

    # ---- H2
    t2 = h2["test_global"]
    L += ["## H2 — Les variables temporelles, fréquentielles et contextuelles discriminent", "",
          "Ablation : PR-AUC du modèle complet moins celui d'un modèle SANS la famille ; "
          "ajout : socle (profil client + type d'opération) auquel on AJOUTE une famille.", "",
          md_table(["Famille", "PR-AUC sans la famille", "Δ vs complet", "PR-AUC socle + famille"],
                   [[f, ci(t2[f"sans_{f}"]), diff(t2[f"sans_{f}"]), ci(t2[f"socle+{f}"])] for f in FAMILIES]
                   + [["socle seul", "-", "-", ci(t2["socle_seul"])]]), ""]
    useful = [f for f in ("temporelles", "fréquentielles", "contextuelles")
              if t2[f"socle+{f}"]["pr_auc"]["point"] > t2["socle_seul"]["pr_auc"]["point"] + 0.005]
    abl = [f for f in ("temporelles", "fréquentielles", "contextuelles")
           if t2[f"sans_{f}"]["pr_auc"]["significant_95"] and t2[f"sans_{f}"]["pr_auc"]["diff_vs_reference"] < 0]
    L += [f"Familles qui améliorent nettement le socle (> +0,005 de PR-AUC) : {', '.join(useful) or 'aucune'}.",
          f"Familles dont le retrait dégrade significativement le modèle complet : {', '.join(abl) or 'aucune'}.",
          "Une ablation peut rester faible quand les familles se compensent (redondance) : lire les deux colonnes.",
          f"**Conclusion H2 : {'CONFIRMÉE' if set(useful) | set(abl) == {'temporelles', 'fréquentielles', 'contextuelles'} else 'PARTIELLEMENT CONFIRMÉE'}** "
          "(chacune des trois familles contribue si elle apparaît dans l'une des deux listes ci-dessus ; "
          "une contribution temporelle très faible en ablation indique de la redondance avec les autres familles).", ""]
    uni = h2["univariee"]
    for ch in ("MOBILE_MONEY", "VISA_VIRTUAL"):
        L += [f"AUC univariée — {ch} (15 meilleures variables, période d'entraînement) :", "",
              md_table(["Variable", "AUC", "Sens (+ = plus élevé en fraude)"],
                       [[r["variable"], r["auc"], r["sens"]] for r in uni[ch]["top"]]), ""]
    sus = {ch: [r["variable"] for r in uni[ch]["suspects_fuite"]] for ch in uni}
    L += ["Contrôle de fuite d'information (variable seule d'AUC > "
          f"{LEAK_AUC}) : " + ("aucune variable suspecte." if not any(sus.values()) else
                               "; ".join(f"{c}: {v}" for c, v in sus.items() if v)), ""]

    # ---- H3
    t3 = h3["test_global"]
    L += ["## H3 — Les performances varient selon la famille de modèles", "",
          md_table(["Modèle", "PR-AUC [IC95]", "Δ vs XGBoost", "Rappel à 1 % FP [IC95]"],
                   [[n, ci(t3[n]), diff(t3[n]), ci(t3[n], "recall_at_1pct_fpr")] for n in t3]), "",
          "Par canal (PR-AUC) :", "",
          md_table(["Modèle", "Mobile Money", "Visa virtuelle"],
                   [[n, ci(h3["test_mobile_money"][n]), ci(h3["test_visa_virtual"][n])] for n in t3]), ""]
    sig = [n for n in t3 if n != "xgboost" and t3[n]["pr_auc"]["significant_95"]]
    L += [f"**Conclusion H3 : {'CONFIRMÉE' if sig else 'NON CONFIRMÉE'}** — modèles significativement différents "
          f"de XGBoost : {', '.join(sig) or 'aucun'}. Le modèle hybride (XGBoost + LSTM + autoencodeur) est "
          "évalué par `train_model.py` (voir phase3_model_comparison.csv).", ""]

    # ---- H4
    v, mmr = h4["sur_visa_test"], h4["sur_mobile_money_test"]
    L += ["## H4 — Transposition du Mobile Money vers la Visa virtuelle", "",
          f"Test Visa : {h4['n_fraud_visa_test']} fraudes seulement (prévalence {h4['prevalence_visa_test']}) : "
          "lire les IC, qui sont larges. Seuil « honnête » = appris sur le Mobile Money.", "",
          md_table(["Entraînement", "PR-AUC Visa [IC95]", "Δ vs mixte", "Rappel à 1 % FP [IC95]",
                    "F1 (seuil MM)", "F1 (seuil recalibré Visa)"],
                   [[n, ci(v[n]), diff(v[n]), ci(v[n], "recall_at_1pct_fpr"), v[n]["operational"].get("f1"),
                     v[n]["operational_seuil_recalibre_visa"].get("f1")]
                    for n in ("mm_seul", "mm_seul_vars_communes", "mm+5%visa", "mm+20%visa", "visa_seule", "mixte",
                              "regles_metier")]), "",
          "Sens inverse et oubli (test Mobile Money) :", "",
          md_table(["Entraînement", "PR-AUC Mobile Money [IC95]", "Δ vs mixte"],
                   [[n, ci(mmr[n]), diff(mmr[n])] for n in ("mixte", "mm_seul", "visa_seule", "regles_metier")]), "",
          f"Rapport de transfert (PR-AUC Mobile Money seul / modèle mixte, sur la Visa) = "
          f"{h4['ratio_transfert_pr_auc']} → transposabilité **{h4['niveau_transposabilite']}** "
          f"(≥ 0,9 forte ; 0,6-0,9 partielle ; < 0,6 faible — convention de ce rapport). "
          f"Le modèle Mobile Money seul est {h4['gain_par_rapport_a_l_aleatoire']}× meilleur que le hasard "
          "(PR-AUC / prévalence).", ""]
    ad = [n for n in ("mm+5%visa", "mm+20%visa") if not v[n]["pr_auc"].get("significant_95", False)]
    f1_mm, f1_re = v["mm_seul"]["operational"].get("f1"), v["mm_seul"]["operational_seuil_recalibre_visa"].get("f1")
    L += [f"**Conclusion H4** : transposabilité {h4['niveau_transposabilite']} du CLASSEMENT des transactions "
          f"(PR-AUC {v['mm_seul']['pr_auc']['point']:.4f} sans aucune donnée Visa). Le SEUIL, lui, se transpose "
          f"moins bien : F1 {f1_mm} avec le seuil Mobile Money contre {f1_re} une fois recalibré sur la Visa. "
          + (f"Avec adaptation ({', '.join(ad)}), l'écart au modèle mixte n'est plus significatif. " if ad else
             "L'adaptation testée (5 %, 20 %) ne ramène pas l'écart sous le seuil de significativité. ")
          + "Attention à l'effet plafond : la PR-AUC Visa du modèle mixte est proche de 1 ; la Visa simulée "
            "est très séparable (voir la variable d'AUC univariée > 0,95 dans H2), ce qui peut surestimer la transposabilité.", ""]

    # ---- RQ1
    L += ["## RQ1 — Comportements transactionnels observables (échantillon complet)", ""]
    for ch, d in R["descriptif"].items():
        rows = [[k, d[k]["legitime"], d[k]["fraude"]] for k in d
                if isinstance(d[k], dict) and "legitime" in d[k]]
        L += [f"**{ch}** — {d['n']:,} transactions, taux de fraude {d['fraud_rate']:.2%}", "",
              md_table(["Indicateur", "Légitime", "Fraude"], rows), ""]

    L += ["## Limites", "",
          "- Données synthétiques : validité externe non démontrée ; à confirmer sur des données réelles d'opérateur.",
          "- Test Visa petit (peu de fraudes) : conclusions H4 à nuancer par les IC.",
          "- Une seule période et un seul découpage temporel ; la variance liée aux données n'est pas mesurée.",
          "- Le test « statique » est défini ici par l'absence d'historique de l'usager ; une autre définition "
          "pourrait changer l'écart.", ""]
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true")
    a = p.parse_args()
    t0 = time.perf_counter()
    S = Study(a.quick)
    R: dict = {"data": {"n": int(len(S.y)), "n_test": int(S.test.sum()), "n_test_fraud": int(S.y[S.test].sum()),
                        "bounds": S.bounds, "quick": a.quick, "static_features": STATIC_FEATURES}}
    R["descriptif"] = S.descriptive()
    R["H1"] = S.h1()
    R["H2"] = S.h2()
    R["H3"] = S.h3()
    R["H4"] = S.h4()
    R["duree_s"] = round(time.perf_counter() - t0)
    REPORTS_DIR.mkdir(exist_ok=True)
    suffix = "_quick" if a.quick else ""
    (REPORTS_DIR / f"research_evaluation{suffix}.json").write_text(
        json.dumps(_py(R), indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS_DIR / f"research_evaluation{suffix}.md").write_text(build_markdown(_py(R)), encoding="utf-8")
    log(f"[OK] rapport -> {REPORTS_DIR}/research_evaluation{suffix}.md ({R['duree_s']} s)")


if __name__ == "__main__":
    main()
