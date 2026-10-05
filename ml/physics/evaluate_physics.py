"""
Évaluation du modèle hybride « données + lois physiques ».

Quatre mesures, avec intervalles de confiance (bootstrap apparié par usager) :

    A. Violations sur les données simulées : à quelle fréquence les lois physiques sont-elles violées par des
       opérations légitimes et par des fraudes ? (Le simulateur ne modélise pas la physique des déplacements :
       un résultat « les lois ne discriminent pas ici » est attendu et ne dit rien des données réelles.)
    B. Valeur ajoutée comme variables : XGBoost avec / sans les valeurs physiques (même split temporel).
    C. Coût en mode « enforce » : part des opérations légitimes qui seraient soumises à vérification.
    D. TEST DE ROBUSTESSE (attaque injectée, jamais vue à l'entraînement) : « session relayée » = un attaquant
       réutilise l'appareil, le type d'opération et le montant habituels de la victime, mais depuis une province
       éloignée, quelques minutes après une opération légitime. Seule la physique trahit l'attaque. On mesure
       ce que détectent le modèle de données seul, la physique seule et l'hybride (OU des deux), et le coût en
       fausses alertes sur les vraies opérations légitimes du test.

ATTENTION : D est un scénario construit par l'équipe, pas une mesure sur des fraudes réelles ; il illustre la
complémentarité des deux modèles face à une attaque nouvelle, pas leur performance réelle.

Usage : python -m ml.physics.evaluate_physics        Sortie : ml/reports/physics_evaluation.json / .md
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml.features.feature_engineering import (FEATURE_NAMES, PHYSICS_NAMES, PROCESSED_DIR, RAW_DIR,
                                             build_feature_table, _period_start)
from ml.models.xgboost_branch import train_xgboost_branch, xgb_logit
from ml.physics.laws import PROVINCE_COORDS, SEVERE_TRAVEL, haversine_km
from ml.preprocessing.train_test_split_normalize import temporal_split
from ml.training.evaluation import best_f1_threshold, recall_at_fpr
from ml.training.significance import paired_bootstrap

REPORTS = Path("ml/reports")
N_INJECT = 300
N_EST = 400


def load_table() -> pd.DataFrame:
    cache = PROCESSED_DIR / "features.csv"
    if cache.exists():
        t = pd.read_csv(cache, parse_dates=["timestamp"], low_memory=False)
        if all(c in t.columns for c in PHYSICS_NAMES):
            return t
    from ml.features.feature_engineering import load_or_build_features
    return load_or_build_features(cache_path=cache)


def severe(t: pd.DataFrame) -> np.ndarray:
    return (t["phys_travel_infeasibility"].to_numpy() >= SEVERE_TRAVEL) | (t["phys_overdraft"].to_numpy() > 0)


def travel_severe(t: pd.DataFrame) -> np.ndarray:
    return t["phys_travel_infeasibility"].to_numpy() >= SEVERE_TRAVEL


def fit(table: pd.DataFrame, cols: list[str], split: np.ndarray, seed: int = 42):
    X = table[cols].to_numpy(np.float32)
    y = table["is_fraud"].to_numpy()
    m = train_xgboost_branch(X[split == 0], y[split == 0], X[split == 1], y[split == 1], N_EST, seed)
    return m, xgb_logit(m, X)


def inject_relay_attacks(n: int, test_from: pd.Timestamp, seed: int = 11) -> pd.DataFrame:
    """Copies « session relayée » d'opérations légitimes de la période de test (voir l'en-tête)."""
    rng = np.random.default_rng(seed)
    tx = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["timestamp"])
    cand = tx[(tx["timestamp"] >= test_from) & (tx["is_fraud"] == 0) & (tx["channel"] == "MOBILE_MONEY")
              & tx["tx_type"].isin(["P2P_SEND", "CASH_OUT", "MERCHANT_PAYMENT"]) & (tx["status"] == "SUCCESS")
              & (tx["balance_before_usd"] > 20)]
    cand = cand.drop_duplicates("user_id").sample(n, random_state=seed)
    rows = []
    for r in cand.to_dict("records"):
        here = PROVINCE_COORDS[r["location_province"]]
        far = sorted(PROVINCE_COORDS, key=lambda p: -haversine_km(here, PROVINCE_COORDS[p]))[:3]   # les 3 plus éloignées
        c = dict(r)
        delay = int(rng.integers(60, 300))
        c.update(transaction_id="ATK" + r["transaction_id"][2:], timestamp=r["timestamp"] + pd.Timedelta(seconds=delay), inject_delay_s=delay,
                 location_province=str(rng.choice(far)), amount_usd=round(r["amount_usd"] * rng.uniform(0.9, 1.1), 2),
                 is_fraud=1, fraud_type="SESSION_RELAYEE", fraud_episode_id="ATK")
        rows.append(c)
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.perf_counter()
    table = load_table()
    split, bounds = temporal_split(table["timestamp"])
    y = table["is_fraud"].to_numpy()
    users = table["user_id"].to_numpy()
    te = split == 3
    R: dict = {"n": int(len(table)), "n_test": int(te.sum()), "split_bounds": bounds}

    # ---------------- A. violations
    sev, tsev = severe(table), travel_severe(table)
    leg = y == 0
    ov = table["phys_overdraft"].to_numpy() > 0
    R["A_violations"] = {
        "cinematique_severe": {"legitimes": int((tsev & leg).sum()), "part_des_legitimes": round(float((tsev & leg).sum() / leg.sum()), 5),
                               "fraudes": int((tsev & ~leg).sum()), "part_des_fraudes": round(float((tsev & ~leg).sum() / (~leg).sum()), 5),
                               "precision": round(float(y[tsev].mean()), 4) if tsev.any() else None},
        "conservation": {"legitimes": int((ov & leg).sum()), "fraudes": int((ov & ~leg).sum()),
                         "precision": round(float(y[ov].mean()), 4) if ov.any() else None},
        "taux_de_fraude_global": round(float(y.mean()), 5),
        "par_type_de_fraude": {str(k): round(float(v), 4) for k, v in
                               pd.Series(tsev[~leg]).groupby(table.loc[~leg, "fraud_type"].to_numpy()).mean().items()},
    }

    # ---------------- B. valeur ajoutée comme variables
    cols_d, cols_p = FEATURE_NAMES, FEATURE_NAMES + PHYSICS_NAMES
    scores = {}
    for name, cols in (("donnees", cols_d), ("donnees+physique", cols_p)):
        _, s = fit(table, cols, split)
        scores[name] = s
    boot = paired_bootstrap(y[te], {k: v[te] for k, v in scores.items()}, users[te], reference="donnees", n_boot=300)
    R["B_valeur_ajoutee_comme_variables"] = boot
    # variance d'entraînement : les IC ci-dessus ne couvrent que l'échantillon de test, pas la graine du modèle
    seeds = {k: [] for k in ("donnees", "donnees+physique")}
    for sd in (42, 7, 13, 21, 99):
        for name, cols in (("donnees", cols_d), ("donnees+physique", cols_p)):
            _, s_ = fit(table, cols, split, seed=sd)
            seeds[name].append(round(float(average_precision_score(y[te], s_[te])), 4))
    R["B_variance_graines"] = {k: {"pr_auc": v, "moyenne": round(float(np.mean(v)), 4), "ecart_type": round(float(np.std(v)), 4)}
                               for k, v in seeds.items()}

    # ---------------- C. coût du mode enforce
    R["C_cout_enforce"] = {"legitimes_soumises_a_verification": round(float((tsev & leg & te).sum() / (leg & te).sum()), 5),
                           "fraudes_deja_alertees_par_la_physique": round(float((tsev & ~leg & te).sum() / max((~leg & te).sum(), 1)), 5)}

    # ---------------- D. attaque injectée (robustesse)
    model, s_data = fit(table, cols_d, split)
    val = split == 2
    thr = best_f1_threshold(y[val], s_data[val])
    thr_1pct = float(np.quantile(s_data[te & leg], 0.99))
    tx_raw = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["timestamp"])
    users_df = pd.read_csv(RAW_DIR / "users.csv")
    atk = inject_relay_attacks(N_INJECT, pd.Timestamp(bounds["test_from"]))
    allt = pd.concat([tx_raw, atk], ignore_index=True)
    feat_all = build_feature_table(allt, users_df, _period_start(allt["timestamp"], RAW_DIR))
    fa = feat_all[feat_all["transaction_id"].isin(set(atk["transaction_id"]))]
    xa = fa[cols_d].to_numpy(np.float32)
    sa = xgb_logit(model, xa)
    flag_data_a = sa >= thr
    flag_data_a_1 = sa >= thr_1pct
    flag_phys_a = travel_severe(fa)
    real_legit = te & leg
    flag_data_r = s_data[real_legit] >= thr
    flag_phys_r = tsev[real_legit]
    flag_hybrid_r = flag_data_r | flag_phys_r
    n = len(fa)
    def rate(m):
        return round(float(np.mean(m)), 4)
    R["D_attaque_session_relayee"] = {
        "n_attaques": int(n), "distance_moyenne_km": round(float(fa["phys_travel_km"].mean()), 0),
        "ecart_moyen_min": round(float(atk["inject_delay_s"].mean() / 60), 1),
        "rappel": {"modele_de_donnees (seuil F1)": rate(flag_data_a), "modele_de_donnees (seuil 1 % de faux positifs)": rate(flag_data_a_1),
                   "physique_seule": rate(flag_phys_a), "hybride (donnees OU physique)": rate(flag_data_a | flag_phys_a)},
        "fausses_alertes_sur_les_vraies_operations_legitimes": {
            "modele_de_donnees (seuil F1)": round(float(flag_data_r.mean()), 5),
            "physique_seule": round(float(flag_phys_r.mean()), 5), "hybride": round(float(flag_hybrid_r.mean()), 5)},
        "rappel_ic95": {},
    }
    rng = np.random.default_rng(0)
    for name, m in (("modele_de_donnees", flag_data_a), ("hybride", flag_data_a | flag_phys_a)):
        bs = [m[rng.integers(0, n, n)].mean() for _ in range(2000)]
        R["D_attaque_session_relayee"]["rappel_ic95"][name] = [round(float(x), 4) for x in np.percentile(bs, [2.5, 97.5])]
    R["duree_s"] = round(time.perf_counter() - t0)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "physics_evaluation.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    (REPORTS / "physics_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    print(to_markdown(R))


def to_markdown(R: dict) -> str:
    A, C, D = R["A_violations"], R["C_cout_enforce"], R["D_attaque_session_relayee"]
    B = R["B_valeur_ajoutee_comme_variables"]
    d, p = B["donnees"], B["donnees+physique"]
    ci = lambda m, k="pr_auc": f"{m[k]['point']:.4f} [{m[k]['ci95'][0]:.4f} ; {m[k]['ci95'][1]:.4f}]"  # noqa: E731
    L = ["# Modèle hybride : données + lois physiques", "",
         "Lois : cinématique (déplacement entre provinces) et conservation (solde). Voir `ml/physics/laws.py`.", "",
         "## A. Violations sur les données simulées", "",
         f"Cinématique nettement violée : {A['cinematique_severe']['legitimes']} opérations légitimes "
         f"({A['cinematique_severe']['part_des_legitimes']:.2%} des légitimes) et {A['cinematique_severe']['fraudes']} fraudes "
         f"({A['cinematique_severe']['part_des_fraudes']:.2%} des fraudes) ; précision des violations : "
         f"{A['cinematique_severe']['precision']} pour un taux de fraude global de {A['taux_de_fraude_global']}.", "",
         (("**Lecture** : les déplacements légitimes de ce jeu respectent la physique (voyages réalistes) ; une violation "
           f"nette de la cinématique est donc un signal fort : {A['cinematique_severe']['precision']:.0%} des opérations "
           "qui la violent sont des fraudes, contre "
           f"{A['taux_de_fraude_global']:.2%} en moyenne.") if A["cinematique_severe"]["part_des_legitimes"] < 0.001 else
          ("**Lecture** : le simulateur ne modélise pas la physique des déplacements (des clients légitimes changent de "
           "province en quelques minutes). La cinématique ne discrimine donc pas dans ces données ; ce n'est pas une "
           "preuve sur des données réelles, où ce déplacement est impossible.")), "",
         f"Conservation (débit supérieur au solde) : {A['conservation']['legitimes']} légitimes, {A['conservation']['fraudes']} fraudes.", "",
         "## B. Les valeurs physiques comme variables du modèle de données", "",
         "| Modèle | PR-AUC test [IC95] | Δ vs données seules |", "|---|---|---|",
         f"| données | {ci(d)} | réf. |",
         f"| données + physique | {ci(p)} | {p['pr_auc']['diff_vs_reference']:+.4f} [{p['pr_auc']['diff_ci95'][0]:+.4f} ; "
         f"{p['pr_auc']['diff_ci95'][1]:+.4f}] ({'significatif' if p['pr_auc']['significant_95'] else 'non significatif'}) |", "",
         f"Sur 5 graines d'entraînement : données {R['B_variance_graines']['donnees']['moyenne']} ± {R['B_variance_graines']['donnees']['ecart_type']}, "
         f"données + physique {R['B_variance_graines']['donnees+physique']['moyenne']} ± {R['B_variance_graines']['donnees+physique']['ecart_type']} "
         "(PR-AUC du test). Un écart du même ordre que l'écart-type est du bruit d'entraînement.", "",
         "## C. Coût du mode « enforce »", "",
         f"{C['legitimes_soumises_a_verification']:.2%} des opérations légitimes du test seraient soumises à vérification ; "
         f"{C['fraudes_deja_alertees_par_la_physique']:.2%} des fraudes seraient signalées par la physique.", "",
         "## D. Robustesse : attaque « session relayée » injectée (jamais vue à l'entraînement)", "",
         f"{D['n_attaques']} attaques : appareil, type d'opération et montant habituels de la victime, mais depuis une province "
         f"à {D['distance_moyenne_km']:.0f} km en moyenne, {D['ecart_moyen_min']} min après une opération légitime.", "",
         "| Détecteur | Attaques détectées | Fausses alertes (vraies opérations légitimes) |", "|---|---|---|"]
    r, f = D["rappel"], D["fausses_alertes_sur_les_vraies_operations_legitimes"]
    L += [f"| Modèle de données (seuil F1) | {r['modele_de_donnees (seuil F1)']:.1%} | {f['modele_de_donnees (seuil F1)']:.2%} |",
          f"| Modèle de données (seuil à 1 % de faux positifs) | {r['modele_de_donnees (seuil 1 % de faux positifs)']:.1%} | 1,00 % |",
          f"| Physique seule | {r['physique_seule']:.1%} | {f['physique_seule']:.2%} |",
          f"| **Hybride (données OU physique)** | **{r['hybride (donnees OU physique)']:.1%}** | {f['hybride']:.2%} |", "",
          f"IC95 du rappel : données {D['rappel_ic95']['modele_de_donnees']} ; hybride {D['rappel_ic95']['hybride']}.", "",
          "**Limites** : D est un scénario construit par l'équipe, pas une mesure sur des fraudes réelles. "
          + ("Les fausses alertes de la physique viennent de déplacements légitimes impossibles produits par le simulateur ; "
             "sur des données réelles elles devraient être bien plus rares. " if f["physique_seule"] >= 0.001 else "")
          + "Les coordonnées sont celles des chefs-lieux.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    import sys as _sys
    if "--markdown-only" in _sys.argv:            # régénère le rapport lisible à partir du JSON existant
        R = json.loads((REPORTS / "physics_evaluation.json").read_text(encoding="utf-8"))
        (REPORTS / "physics_evaluation.md").write_text(to_markdown(R), encoding="utf-8")
    else:
        main()
