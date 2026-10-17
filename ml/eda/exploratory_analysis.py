"""
Analyse exploratoire du jeu de données (chapitre III, § I.1 du mémoire).

Décrit le jeu de transactions simulées AVANT toute modélisation : qualité des données, volumes, déséquilibre des
classes, répartition des fraudes (typologie, année, canal, province), distribution des montants et des horaires,
structure par client, et corrélations entre les variables comportementales. Chaque constat est chiffré et chaque
figure est produite à partir des fichiers bruts (ml/data/raw) et des variables (ml/data/processed).

Usage : python -m ml.eda.exploratory_analysis
Sortie : ml/reports/eda.json, ml/reports/eda.md, ml/reports/figures/chapitre3/fig_III_*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAW = Path("ml/data/raw")
PROCESSED = Path("ml/data/processed")
ARTIFACTS = Path("ml/artifacts")
REPORTS = Path("ml/reports")
FIGS = REPORTS / "figures" / "chapitre3"
LEG, FRA = "#2b6cb0", "#c53030"
TYPES = {"SIM_SWAP": "Échange de SIM", "SOCIAL_ENGINEERING": "Ingénierie sociale", "ACCOUNT_TAKEOVER": "Prise de contrôle",
         "AGENT_FRAUD": "Fraude d'agent", "SMURFING": "Fractionnement", "CARD_TESTING": "Test de carte",
         "CNP_FRAUD": "Carte non présente", "TOPUP_DRAIN": "Vidage par rechargement"}
PALETTE = ["#2b6cb0", "#c53030", "#d69e2e", "#2f855a", "#805ad5", "#dd6b20", "#319795", "#718096"]

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": .25, "figure.dpi": 130, "savefig.bbox": "tight"})


def rate_table(df: pd.DataFrame, col: str) -> list[dict]:
    g = df.groupby(col, dropna=False).agg(n=("is_fraud", "size"), frauds=("is_fraud", "sum"))
    g["share"] = g["n"] / len(df)
    g["fraud_rate"] = g["frauds"] / g["n"]
    return [{"group": str(k), "n": int(r.n), "share": float(r.share), "frauds": int(r.frauds), "fraud_rate": float(r.fraud_rate)}
            for k, r in g.sort_values("n", ascending=False).iterrows()]


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    tx = pd.read_csv(RAW / "transactions.csv", parse_dates=["timestamp"], low_memory=False)
    users = pd.read_csv(RAW / "users.csv")
    tx["year"], tx["month"] = tx["timestamp"].dt.year, tx["timestamp"].dt.to_period("M")
    tx["hour"], tx["dow"] = tx["timestamp"].dt.hour, tx["timestamp"].dt.dayofweek
    tx = tx.merge(users[["user_id", "segment", "kyc_level", "monthly_income_usd"]], on="user_id", how="left")
    R: dict = {}

    # ---------------------------------------------------------------- 1. qualité
    nulls = tx.isna().sum()
    R["quality"] = {
        "n_rows": int(len(tx)), "n_columns": int(tx.shape[1]), "period": [str(tx.timestamp.min()), str(tx.timestamp.max())],
        "duplicate_ids": int(tx.transaction_id.duplicated().sum()), "non_positive_amounts": int((tx.amount_usd <= 0).sum()),
        "null_timestamps": int(tx.timestamp.isna().sum()), "negative_balances": int((tx.balance_before_usd < 0).sum()),
        "failed_share": float((tx.status != "SUCCESS").mean()), "n_users": int(tx.user_id.nunique()),
        "n_agents_used": int(tx.agent_id.nunique()), "n_merchants_used": int(tx.merchant_id.nunique()),
        "n_devices": int(tx.device_id.nunique()),
        "missing": {c: {"n": int(v), "share": float(v / len(tx))} for c, v in nulls.items() if v > 0 and not c.startswith("fraud_")},
    }
    # un champ vide est-il structurel (propre au type d'opération) ? part de lignes manquantes par type d'opération
    structural = {}
    for col in ("counterparty_id", "merchant_id", "agent_id", "ip_country", "card_id"):
        by_type = tx.groupby("tx_type")[col].apply(lambda s: s.isna().mean())
        structural[col] = {k: float(v) for k, v in by_type.items()}
    R["quality"]["structural_missing_by_type"] = structural

    # ---------------------------------------------------------------- 2. déséquilibre, volumes
    R["balance"] = {"fraud_rate": float(tx.is_fraud.mean()), "n_fraud": int(tx.is_fraud.sum()),
                    "ratio_legit_per_fraud": float((1 - tx.is_fraud.mean()) / tx.is_fraud.mean()),
                    "naive_accuracy": float(1 - tx.is_fraud.mean())}
    yr = tx.groupby("year").agg(n=("is_fraud", "size"), frauds=("is_fraud", "sum"), usd=("amount_usd", "sum"))
    yr["rate"] = yr.frauds / yr.n
    R["by_year"] = [{"year": int(y), "n": int(r.n), "frauds": int(r.frauds), "rate": float(r.rate), "usd": float(r.usd)} for y, r in yr.iterrows()]
    for col, key in (("channel", "by_channel"), ("operator", "by_operator"), ("tx_type", "by_tx_type"),
                     ("access_channel", "by_access"), ("device_type", "by_device"), ("location_province", "by_province"),
                     ("segment", "by_segment"), ("kyc_level", "by_kyc")):
        R[key] = rate_table(tx, col)
    ep = tx[tx.is_fraud == 1].groupby("fraud_episode_id").agg(n=("transaction_id", "size"), usd=("amount_usd", "sum"),
                                                              ftype=("fraud_type", "first"))
    R["episodes"] = {"n_episodes": int(len(ep)), "ops_per_episode_mean": float(ep.n.mean()), "ops_per_episode_max": int(ep.n.max()),
                     "usd_per_episode_median": float(ep.usd.median()),
                     "by_type": {k: {"episodes": int(len(g)), "ops_mean": float(g.n.mean()), "usd_median": float(g.usd.median())}
                                 for k, g in ep.groupby("ftype")}}
    ty = tx[tx.is_fraud == 1].groupby(["year", "fraud_type"]).size().unstack(fill_value=0)
    R["type_by_year"] = {str(y): {k: int(v) for k, v in row.items()} for y, row in ty.iterrows()}
    R["type_totals"] = {k: int(v) for k, v in tx[tx.is_fraud == 1].fraud_type.value_counts().items()}

    # ---------------------------------------------------------------- 3. montants et horaires
    amt = {}
    for ch, g in tx.groupby("channel"):
        for lab, s in (("legit", g[g.is_fraud == 0].amount_usd), ("fraud", g[g.is_fraud == 1].amount_usd)):
            amt[f"{ch}|{lab}"] = {"median": float(s.median()), "mean": float(s.mean()), "p95": float(s.quantile(.95)),
                                  "p99": float(s.quantile(.99)), "max": float(s.max()),
                                  "skew": float(s.skew()), "skew_log": float(np.log1p(s).skew())}
    R["amounts"] = amt
    hr = tx.groupby(["is_fraud", "hour"]).size().unstack(fill_value=0)
    hshare = hr.div(hr.sum(axis=1), axis=0)
    R["hours"] = {"night_share_legit": float(hshare.loc[0, 0:5].sum()), "night_share_fraud": float(hshare.loc[1, 0:5].sum()),
                  "fraud_rate_by_hour": {int(h): float(tx[tx.hour == h].is_fraud.mean()) for h in range(24)}}
    R["weekday_fraud_rate"] = {int(d): float(tx[tx.dow == d].is_fraud.mean()) for d in range(7)}
    inc = tx[tx.is_fraud == 0].merge(users[["user_id"]], on="user_id")
    R["income_note"] = "revenu mensuel déclaré : médiane %.0f USD (clients)" % float(users.monthly_income_usd.median())

    # ---------------------------------------------------------------- 4. structure par client
    per_user = tx.groupby("user_id").agg(n=("is_fraud", "size"), frauds=("is_fraud", "sum"))
    R["per_user"] = {"tx_min": int(per_user.n.min()), "tx_median": float(per_user.n.median()), "tx_max": int(per_user.n.max()),
                     "users_with_fraud": int((per_user.frauds > 0).sum()), "users": int(len(per_user)),
                     "share_users_with_fraud": float((per_user.frauds > 0).mean()),
                     "fraud_per_victim_median": float(per_user.frauds[per_user.frauds > 0].median())}
    mule_wallets = tx[(tx.tx_type.isin(["P2P_SEND", "P2P_RECEIVE"])) & tx.counterparty_id.notna()]
    cp = mule_wallets.groupby("counterparty_id").agg(users=("user_id", "nunique"), n=("is_fraud", "size"), fr=("is_fraud", "sum"))
    R["counterparties"] = {"n": int(len(cp)), "shared_by_2plus_users": int((cp.users >= 2).sum()),
                           "shared_with_fraud": int(((cp.users >= 2) & (cp.fr > 0)).sum())}

    # ---------------------------------------------------------------- 5. corrélations entre variables
    names = json.loads((ARTIFACTS / "feature_names.json").read_text(encoding="utf-8"))
    X = np.load(PROCESSED / "X_all.npy", mmap_mode="r")
    y = np.load(PROCESSED / "y_all.npy").astype(np.float32)
    sample = np.random.default_rng(42).choice(len(y), 200_000, replace=False)
    Xs, ys = np.asarray(X[sample]), y[sample]
    corr_y = np.array([np.corrcoef(Xs[:, j], ys)[0, 1] if Xs[:, j].std() > 0 else 0.0 for j in range(Xs.shape[1])])
    order = np.argsort(-np.abs(corr_y))
    top = order[:16]
    C = np.corrcoef(Xs[:, top].T)
    pairs = []
    for a in range(len(top)):
        for b in range(a + 1, len(top)):
            pairs.append((abs(C[a, b]), names[top[a]], names[top[b]], float(C[a, b])))
    pairs.sort(reverse=True)
    R["correlations"] = {"top_with_target": [{"feature": names[j], "r": float(corr_y[j])} for j in order[:12]],
                         "redundant_pairs": [{"a": a, "b": b, "r": r} for _, a, b, r in pairs[:6]],
                         "n_features": len(names)}

    # ================================================================ FIGURES
    # III.1 volume mensuel + taux de fraude annuel
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    mv = tx.groupby("month").size()
    ax[0].plot(mv.index.to_timestamp(), mv.values, color=LEG, lw=1.4)
    ax[0].set(title="Transactions par mois", ylabel="transactions")
    ax[0].axvline(pd.Timestamp("2021-01-01"), color="#718096", ls="--", lw=.8)
    ax[0].annotate("lancement de la carte Visa", (pd.Timestamp("2021-01-01"), mv.max() * .5), fontsize=7, color="#4a5568", rotation=90, va="center", ha="right")
    ax[1].bar(yr.index.astype(str), yr.rate * 100, color=FRA)
    for i, (y_, v) in enumerate(yr.rate.items()):
        ax[1].text(i, v * 100 + .02, f"{v * 100:.2f} %", ha="center", fontsize=7)
    ax[1].set(title="Taux de fraude par année", ylabel="% des transactions")
    fig.savefig(FIGS / "fig_III_01_volumes_taux.png"); plt.close(fig)

    # III.2 typologies par année
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bottom = np.zeros(len(ty))
    for i, (k, lab) in enumerate(TYPES.items()):
        if k in ty:
            ax.bar(ty.index.astype(str), ty[k].values, bottom=bottom, label=lab, color=PALETTE[i])
            bottom += ty[k].values
    ax.set(title="Fraudes par typologie et par année", ylabel="opérations frauduleuses")
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.savefig(FIGS / "fig_III_02_typologies_annee.png"); plt.close(fig)

    # III.3 distribution des montants
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4), sharey=False)
    bins = np.logspace(-1, 3.7, 60)
    for a, ch, lab in zip(ax, ("MOBILE_MONEY", "VISA_VIRTUAL"), ("Mobile Money", "Carte Visa virtuelle")):
        g = tx[tx.channel == ch]
        a.hist(g[g.is_fraud == 0].amount_usd.clip(.1, 5000), bins=bins, color=LEG, alpha=.65, density=True, label="légitimes")
        a.hist(g[g.is_fraud == 1].amount_usd.clip(.1, 5000), bins=bins, color=FRA, alpha=.65, density=True, label="fraudes")
        a.set(xscale="log", title=lab, xlabel="montant (USD, échelle logarithmique)", ylabel="densité")
        a.legend(frameon=False)
    fig.savefig(FIGS / "fig_III_03_montants.png"); plt.close(fig)

    # III.4 profil horaire
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.3))
    ax[0].bar(np.arange(24) - .2, hshare.loc[0].values * 100, .4, color=LEG, label="légitimes")
    ax[0].bar(np.arange(24) + .2, hshare.loc[1].values * 100, .4, color=FRA, label="fraudes")
    ax[0].set(title="Répartition des opérations par heure", xlabel="heure", ylabel="% de la classe"); ax[0].legend(frameon=False)
    hr_rate = [tx[tx.hour == h].is_fraud.mean() * 100 for h in range(24)]
    ax[1].plot(range(24), hr_rate, color=FRA, marker="o", ms=3)
    ax[1].set(title="Taux de fraude par heure", xlabel="heure", ylabel="% des transactions")
    fig.savefig(FIGS / "fig_III_04_horaires.png"); plt.close(fig)

    # III.5 taux de fraude par type d'opération et canal d'accès
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.5))
    t = pd.DataFrame(R["by_tx_type"]).set_index("group").sort_values("fraud_rate")
    ax[0].barh(t.index, t.fraud_rate * 100, color=FRA); ax[0].set(title="Taux de fraude par type d'opération", xlabel="%")
    a_ = pd.DataFrame(R["by_access"]).set_index("group").sort_values("fraud_rate")
    ax[1].barh(a_.index, a_.fraud_rate * 100, color=PALETTE[2]); ax[1].set(title="Taux de fraude par canal d'accès", xlabel="%")
    fig.savefig(FIGS / "fig_III_05_type_acces.png"); plt.close(fig)

    # III.6 province et segment
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    p = pd.DataFrame(R["by_province"]).set_index("group").sort_values("n", ascending=True).tail(12)
    ax[0].barh(p.index, p.n / 1000, color=LEG); ax[0].set(title="Volume par province (12 premières)", xlabel="milliers de transactions")
    s = pd.DataFrame(R["by_segment"]).set_index("group").sort_values("fraud_rate")
    ax[1].barh(s.index, s.fraud_rate * 100, color=FRA); ax[1].set(title="Taux de fraude par segment de clientèle", xlabel="%")
    fig.savefig(FIGS / "fig_III_06_province_segment.png"); plt.close(fig)

    # III.7 corrélations
    fig, ax = plt.subplots(figsize=(7.2, 6))
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1)
    labs = [names[j] for j in top]
    ax.set_xticks(range(len(top)), labs, rotation=75, ha="right", fontsize=7); ax.set_yticks(range(len(top)), labs, fontsize=7)
    ax.grid(False)
    for i in range(len(top)):
        for j in range(len(top)):
            if abs(C[i, j]) >= .5 and i != j:
                ax.text(j, i, f"{C[i, j]:.1f}", ha="center", va="center", fontsize=5.5, color="white" if abs(C[i, j]) > .7 else "black")
    fig.colorbar(im, shrink=.7, label="corrélation de Pearson")
    ax.set_title("Corrélations entre les 16 variables les plus liées à la fraude")
    fig.savefig(FIGS / "fig_III_07_correlations.png"); plt.close(fig)

    (REPORTS / "eda.json").write_text(json.dumps(R, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: R[k] for k in ("quality", "balance", "by_year", "episodes", "per_user", "counterparties", "hours")},
                     indent=1, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main()
