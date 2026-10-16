# H5 — Évolution des fraudes et mise à jour du modèle

Modèle figé entraîné sur 2019-2021, comparé chaque année à un modèle réentraîné sur tout l'historique (cumulatif) et sur les 3 dernières années (glissant). XGBoost, 58 variables de profilage, IC95 par bootstrap apparié par usager. **Données simulées : les tendances des fraudes sont des hypothèses du générateur.**

| Année | Fraudes | Figé : PR-AUC | Cumulatif : PR-AUC | Δ cumulatif − figé | Glissant : PR-AUC | Δ glissant − figé |
|---|---|---|---|---|---|---|
| 2022 | 1164 | 0.9858 [0.9794 ; 0.9908] | 0.9858 [0.9794 ; 0.9908] | +0.0000 [+0.0000 ; +0.0000] (non significatif) | 0.9858 [0.9794 ; 0.9908] | +0.0000 [+0.0000 ; +0.0000] (non significatif) |
| 2023 | 1449 | 0.9835 [0.9780 ; 0.9880] | 0.9911 [0.9870 ; 0.9937] | +0.0076 [+0.0049 ; +0.0108] (significatif) | 0.9913 [0.9875 ; 0.9938] | +0.0078 [+0.0050 ; +0.0113] (significatif) |
| 2024 | 1916 | 0.9729 [0.9616 ; 0.9822] | 0.9958 [0.9934 ; 0.9975] | +0.0229 [+0.0143 ; +0.0333] (significatif) | 0.9957 [0.9934 ; 0.9974] | +0.0228 [+0.0142 ; +0.0329] (significatif) |
| 2025 | 2355 | 0.9681 [0.9586 ; 0.9763] | 0.9980 [0.9970 ; 0.9987] | +0.0299 [+0.0220 ; +0.0385] (significatif) | 0.9980 [0.9971 ; 0.9987] | +0.0299 [+0.0219 ; +0.0386] (significatif) |

**Ensemble 2022-2025** : figé 0.9760 [0.9700 ; 0.9817], cumulatif 0.9930 [0.9912 ; 0.9945] (+0.0170 [+0.0124 ; +0.0218] (significatif)), glissant 0.9930 [0.9912 ; 0.9945] (+0.0170 [+0.0124 ; +0.0218] (significatif)).

Rappel au seuil et faux positifs (seuil choisi sur les 3 derniers mois de chaque entraînement) :

| Année | Figé : rappel / faux positifs | Cumulatif | Glissant |
|---|---|---|---|
| 2022 | 0.887 / 0.0330% | 0.887 / 0.0330% | 0.887 / 0.0330% |
| 2023 | 0.879 / 0.0320% | 0.964 / 0.1030% | 0.963 / 0.1020% |
| 2024 | 0.836 / 0.0430% | 0.972 / 0.0360% | 0.979 / 0.0600% |
| 2025 | 0.834 / 0.0500% | 0.991 / 0.0630% | 0.992 / 0.0670% |

Rappel par typologie (figé → cumulatif), dernière année évaluée :

| Typologie | n | Figé | Cumulatif | Glissant |
|---|---|---|---|---|
| ACCOUNT_TAKEOVER | 398 | 1.0 | 1.0 | 1.0 |
| AGENT_FRAUD | 168 | 1.0 | 1.0 | 1.0 |
| CARD_TESTING | 81 | 1.0 | 1.0 | 1.0 |
| CNP_FRAUD | 128 | 0.9844 | 0.9922 | 1.0 |
| SIM_SWAP | 585 | 1.0 | 1.0 | 1.0 |
| SMURFING | 303 | 0.8746 | 1.0 | 1.0 |
| SOCIAL_ENGINEERING | 610 | 0.4246 | 0.9672 | 0.9721 |
| TOPUP_DRAIN | 82 | 1.0 | 1.0 | 0.9878 |

Écart cumulatif − figé par année : {'2022': 0.0, '2023': 0.0076, '2024': 0.0229, '2025': 0.0299} (pente +0.0105 par an : il se creuse).
Récence ou volume : la fenêtre glissante fait aussi bien que le cumulatif : la récence compte plus que le volume.

**Conclusion H5 : CONFIRMÉE**. Confirmée si le modèle mis à jour est significativement meilleur sur 2022-2025 ET encore meilleur la dernière année, avec un écart qui se creuse ; partiellement si l'écart est significatif sans se creuser.

Limites : données simulées ; un seul modèle (XGBoost) et une seule graine ; les tendances des typologies (FRAUD_TRENDS) sont fixées par hypothèse dans le générateur.
