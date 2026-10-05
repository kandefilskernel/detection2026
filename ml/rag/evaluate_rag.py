"""
Évaluation du RAG : la mémoire de cas rend-elle les décisions plus fiables ?

Protocole : l'index ne contient que la période d'entraînement ; la validation sert à fixer
les paramètres (k, similarité minimale) ; le test est lu une seule fois. Le « modèle » est la
branche XGBoost du modèle hybride (même variables, même seuil F1 choisi sur la validation).

Questions posées, avec intervalles de confiance (bootstrap par usager) :
    1. Les cas proches savent-ils reconnaître la fraude à eux seuls ? (PR-AUC de la part de fraude)
    2. Quand les cas proches CONFIRMENT une alerte du modèle, celle-ci est-elle plus souvent
       une vraie fraude que lorsqu'ils la CONTREDISENT ? (précision par niveau de cohérence)
    3. Les cas proches retrouvent-ils le bon type de fraude ? (comparé au classifieur de type)
    4. Le drapeau « divergent » isole-t-il bien les fausses alertes, et à quel coût ?

Usage : python -m ml.rag.evaluate_rag
Sortie : ml/reports/rag_evaluation.json et .md
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import average_precision_score

from ml.rag.case_index import INDEX_FILE, load_table, nearest_neighbors
from ml.preprocessing.train_test_split_normalize import ARTIFACTS_DIR
from ml.training.evaluation import best_f1_threshold

REPORTS = Path("ml/reports")
K_MAX = 15
KS = (5, 7, 11)
MIN_SIMS = (0.0, 0.2, 0.3, 0.4, 0.5)


def neighbor_stats(Xq, channels_q, mem, k):
    """Part de fraude pondérée, similarité moyenne et type majoritaire des k voisins (même canal)."""
    n = len(Xq)
    share, msim = np.zeros(n), np.zeros(n)
    top_type = np.full(n, "", dtype=object)
    for ch in np.unique(mem["channel"]):
        q = np.where(channels_q == ch)[0]
        pool = np.where(mem["channel"] == ch)[0]
        idx, dist = nearest_neighbors(Xq[q], mem["X"][pool], k)
        gi = pool[idx]
        sim = 1.0 / (1.0 + dist / mem["ref"])
        w = sim * mem["w"][gi]
        share[q] = (w * mem["y"][gi]).sum(1) / w.sum(1)
        msim[q] = sim.mean(1)
        for row, qi in enumerate(q):
            votes: dict[str, float] = {}
            for j, wj in zip(gi[row], w[row]):
                if mem["y"][j] == 1:
                    votes[mem["ftype"][j]] = votes.get(mem["ftype"][j], 0.0) + wj
            top_type[qi] = max(votes, key=votes.get) if votes else ""
    return share, msim, top_type


def cluster_boot(fn, users, n_boot=200, seed=0):
    rng = np.random.default_rng(seed)
    codes, inv = np.unique(users, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.concatenate([[0], np.cumsum(np.bincount(inv))])
    vals = []
    while len(vals) < n_boot:
        pick = rng.integers(0, len(codes), len(codes))
        idx = np.concatenate([order[bounds[g]:bounds[g + 1]] for g in pick])
        v = fn(idx)
        if v is not None and np.isfinite(v):
            vals.append(v)
    return [round(float(x), 4) for x in np.percentile(vals, [2.5, 97.5])]


def precision_by_agreement(flagged, comparable, nb_fraud, y):
    out = {}
    for name, m in (("COHERENT", flagged & comparable & nb_fraud), ("DIVERGENT", flagged & comparable & ~nb_fraud),
                    ("INSUFFISANT", flagged & ~comparable)):
        out[name] = {"n": int(m.sum()), "vraies_fraudes": int(y[m].sum()),
                     "precision": round(float(y[m].mean()), 4) if m.any() else None}
    return out


def main() -> None:
    t0 = time.perf_counter()
    table, X, split = load_table()
    y = table["is_fraud"].to_numpy().astype(int)
    z = np.load(ARTIFACTS_DIR / INDEX_FILE, allow_pickle=False)
    mem = {"X": z["X"].astype(np.float32), "y": z["y"].astype(int), "w": z["w"], "ftype": z["ftype"],
           "channel": z["channel"], "ref": float(z["ref_dist"])}

    xgb = joblib.load(ARTIFACTS_DIR / "xgb_branch.pkl")
    score = xgb.predict(X, output_margin=True)
    val, test = np.where(split == 2)[0], np.where(split == 3)[0]
    thr = best_f1_threshold(y[val], score[val])
    flagged_v, flagged_t = score[val] >= thr, score[test] >= thr
    ch = table["channel"].to_numpy()
    users = table["user_id"].to_numpy()
    ftrue = table["fraud_type"].fillna("").to_numpy()

    res: dict = {"index_size": int(len(mem["y"])), "threshold_model": round(float(thr), 4),
                 "note": "modèle = branche XGBoost du modèle hybride ; index = période d'entraînement seulement"}

    # ---------------- calibration sur la validation
    grid = []
    stats_val = {k: neighbor_stats(X[val], ch[val], mem, k) for k in KS}
    for k in KS:
        share, msim, _ = stats_val[k]
        for ms in MIN_SIMS:
            comp = msim >= ms
            nbf = share >= 0.5
            pa = precision_by_agreement(flagged_v, comp, nbf, y[val])
            c, d = pa["COHERENT"], pa["DIVERGENT"]
            gap = (c["precision"] or 0) - (d["precision"] if d["precision"] is not None else (c["precision"] or 0))
            coverage = float((flagged_v & comp).sum() / max(flagged_v.sum(), 1))
            grid.append({"k": k, "min_similarity": ms, "coverage_alertes": round(coverage, 3),
                         "precision_coherent": c["precision"], "precision_divergent": d["precision"],
                         "n_divergent": d["n"], "ecart": round(gap, 4)})
    # choix : écart de précision maximal parmi les réglages qui gardent >= 90 % des alertes comparables,
    # avec >= 10 alertes divergentes. Plancher de similarité fixé à 0,2 (sans perte mesurée sur la validation) :
    # il écarte les opérations très éloignées de tout cas connu au lieu de les juger comparables.
    ok = [g for g in grid if g["coverage_alertes"] >= 0.90 and g["n_divergent"] >= 10 and g["min_similarity"] == 0.2]
    best = max(ok or grid, key=lambda g: g["ecart"])
    K, MS = best["k"], best["min_similarity"]
    res["calibration_validation"] = {"grille": grid, "choisi": {"k": K, "min_similarity": MS}}

    # ---------------- test
    share, msim, ntype = neighbor_stats(X[test], ch[test], mem, K)
    comp, nbf = msim >= MS, share >= 0.5
    yt, ut = y[test], users[test]
    res["parametres"] = {"k": K, "min_similarity": MS, "fraud_share_cutoff": 0.5}
    res["cas_proches_seuls"] = {
        "pr_auc": round(float(average_precision_score(yt, share)), 4),
        "pr_auc_ci95": cluster_boot(lambda i: average_precision_score(yt[i], share[i]) if yt[i].sum() else None, ut),
        "pr_auc_modele": round(float(average_precision_score(yt, score[test])), 4),
        "part_comparable": round(float(comp.mean()), 4),
    }
    pa = precision_by_agreement(flagged_t, comp, nbf, yt)
    boots = {}
    for name, m in (("COHERENT", flagged_t & comp & nbf), ("DIVERGENT", flagged_t & comp & ~nbf)):
        boots[name] = cluster_boot(lambda i, m=m: yt[i][m[i]].mean() if m[i].sum() else None, ut)
        pa[name]["precision_ci95"] = boots[name]
    pa["precision_modele_globale"] = round(float(yt[flagged_t].mean()), 4)
    res["alertes_du_modele_par_coherence"] = pa
    miss = ~flagged_t & (yt == 1)
    res["fraudes_manquees_par_le_modele"] = {
        "n": int(miss.sum()), "retrouvees_par_cas_proches": int((miss & comp & nbf).sum()),
        "fausses_alertes_supplementaires_si_on_ajoutait_cet_avis": int((~flagged_t & (yt == 0) & comp & nbf).sum())}

    # ---------------- type de fraude
    fr = (yt == 1) & comp
    types = ftrue[test]
    res["type_par_cas_proches"] = {
        "n_fraudes_comparables": int(fr.sum()),
        "exactitude": round(float((ntype[fr] == types[fr]).mean()), 4) if fr.any() else None,
        "exactitude_classifieur_de_type": json.loads((REPORTS / "fraud_type_results.json").read_text(
            encoding="utf-8"))["accuracy"] if (REPORTS / "fraud_type_results.json").exists() else None,
    }
    sub = flagged_t & (yt == 1) & comp
    # accord type du classifieur / type des voisins parmi les vraies fraudes alertées : exactitude conditionnelle
    res["type_par_cas_proches"]["exactitude_sur_alertes_vraies"] = round(float((ntype[sub] == types[sub]).mean()), 4) \
        if sub.any() else None
    res["duree_s"] = round(time.perf_counter() - t0)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "rag_evaluation.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    c, d, ins = pa["COHERENT"], pa["DIVERGENT"], pa["INSUFFISANT"]
    md = ["# Évaluation du RAG (mémoire de cas)", "",
          f"Index : {res['index_size']:,} cas de la période d'entraînement. Paramètres choisis sur la validation : "
          f"k = {K}, similarité minimale = {MS}. Évaluation sur le test, modèle = XGBoost (seuil F1 de la validation).", "",
          "## Les cas proches reconnaissent-ils la fraude seuls ?", "",
          f"PR-AUC de la part de fraude parmi les voisins : **{res['cas_proches_seuls']['pr_auc']}** "
          f"[IC95 {res['cas_proches_seuls']['pr_auc_ci95'][0]} ; {res['cas_proches_seuls']['pr_auc_ci95'][1]}] "
          f"(modèle : {res['cas_proches_seuls']['pr_auc_modele']}). Opérations comparables aux cas connus : "
          f"{res['cas_proches_seuls']['part_comparable']:.1%}.", "",
          "## Les alertes du modèle selon l'avis des cas proches", "",
          "| Avis des cas proches | Alertes | Vraies fraudes | Précision [IC95] |", "|---|---|---|---|",
          f"| Confirment (COHERENT) | {c['n']} | {c['vraies_fraudes']} | {c['precision']} {c['precision_ci95']} |",
          f"| Contredisent (DIVERGENT) | {d['n']} | {d['vraies_fraudes']} | {d['precision']} {d.get('precision_ci95')} |",
          f"| Peu comparables (INSUFFISANT) | {ins['n']} | {ins['vraies_fraudes']} | {ins['precision']} |", "",
          f"Précision globale des alertes du modèle : {pa['precision_modele_globale']}.", "",
          "## Fraudes manquées par le modèle", "",
          f"{res['fraudes_manquees_par_le_modele']['n']} fraudes du test ne sont pas alertées ; les cas proches en "
          f"retrouvent {res['fraudes_manquees_par_le_modele']['retrouvees_par_cas_proches']}, au prix de "
          f"{res['fraudes_manquees_par_le_modele']['fausses_alertes_supplementaires_si_on_ajoutait_cet_avis']} "
          "fausses alertes supplémentaires si on les ajoutait aux alertes.", "",
          "## Type de fraude", "",
          f"Type majoritaire des cas proches : exactitude {res['type_par_cas_proches']['exactitude']} "
          f"(classifieur de type : {res['type_par_cas_proches']['exactitude_classifieur_de_type']}).", ""]
    (REPORTS / "rag_evaluation.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
