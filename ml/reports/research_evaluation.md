# Évaluation de recherche : profilage comportemental (Mobile Money RDC et Visa virtuelle)

Données : 631,968 transactions synthétiques, période 2019-01-01 → 2025-12-31, test = 2024-12-13 → fin (183,240 transactions, 2437 fraudes).
Les intervalles [IC95] sont des bootstraps appariés par usager ; les seuils sont choisis sur la validation. **Les données sont simulées : les résultats mesurent la capacité à retrouver des fraudes injectées, pas la fraude réelle.**

## H1 — Le profilage comportemental améliore la détection par rapport aux approches statiques

« Statique » = règles métier à seuils fixes, et XGBoost limité aux variables calculables sans historique de l'usager. « Profilage » = XGBoost avec toutes les variables comportementales.

| Modèle | PR-AUC [IC95] | Δ PR-AUC vs profilage | Rappel à 1 % FP [IC95] |
|---|---|---|---|
| profilage | 0.9893 [0.9857 ; 0.9917] | réf. | 0.9996 [0.9985 ; 1.0000] |
| statique | 0.7533 [0.7027 ; 0.7897] | -0.2360 [-0.2831 ; -0.2014] (significatif) | 0.7505 [0.7068 ; 0.7803] |
| regles_metier | 0.2726 [0.2405 ; 0.3041] | -0.7167 [-0.7477 ; -0.6845] (significatif) | 0.2860 [0.2516 ; 0.3194] |

McNemar au seuil opérationnel : profilage vs statique p = 0.0 ; profilage vs règles p = 0.0.

Variance selon la graine : profilage 0.9895 ± 0.0004, statique 0.7544 ± 0.0011 (PR-AUC test).

**Conclusion H1 : CONFIRMÉE sur ces données** (le profilage est significativement supérieur aux deux approches statiques).

Rappel par typologie de fraude (test) :

| Typologie | n | Profilage | Statique | Règles |
|---|---|---|---|---|
| ACCOUNT_TAKEOVER | 406 | 1.0 | 0.5271 | 0.2069 |
| AGENT_FRAUD | 181 | 1.0 | 0.6077 | 0.3646 |
| CARD_TESTING | 81 | 1.0 | 1.0 | 0.8765 |
| CNP_FRAUD | 131 | 0.9847 | 0.9389 | 0.8092 |
| SIM_SWAP | 623 | 1.0 | 0.7897 | 0.435 |
| SMURFING | 303 | 0.9802 | 0.967 | 0.1221 |
| SOCIAL_ENGINEERING | 630 | 0.8556 | 0.1365 | 0.0032 |
| TOPUP_DRAIN | 82 | 1.0 | 0.8049 | 0.7317 |

## H2 — Les variables temporelles, fréquentielles et contextuelles discriminent

Ablation : PR-AUC du modèle complet moins celui d'un modèle SANS la famille ; ajout : socle (profil client + type d'opération) auquel on AJOUTE une famille.

| Famille | PR-AUC sans la famille | Δ vs complet | PR-AUC socle + famille |
|---|---|---|---|
| temporelles | 0.9902 [0.9869 ; 0.9927] | +0.0009 [-0.0003 ; +0.0023] (non significatif) | 0.1623 [0.1314 ; 0.2006] |
| fréquentielles | 0.9539 [0.9417 ; 0.9621] | -0.0354 [-0.0439 ; -0.0299] (significatif) | 0.4646 [0.4318 ; 0.4961] |
| contextuelles | 0.8426 [0.8135 ; 0.8647] | -0.1467 [-0.1733 ; -0.1266] (significatif) | 0.8174 [0.7852 ; 0.8502] |
| montants | 0.9066 [0.8874 ; 0.9238] | -0.0827 [-0.0994 ; -0.0679] (significatif) | 0.6898 [0.6352 ; 0.7270] |
| socle seul | - | - | 0.0561 [0.0411 ; 0.0838] |

Familles qui améliorent nettement le socle (> +0,005 de PR-AUC) : temporelles, fréquentielles, contextuelles.
Familles dont le retrait dégrade significativement le modèle complet : fréquentielles, contextuelles.
Une ablation peut rester faible quand les familles se compensent (redondance) : lire les deux colonnes.
**Conclusion H2 : CONFIRMÉE** (chacune des trois familles contribue si elle apparaît dans l'une des deux listes ci-dessus ; une contribution temporelle très faible en ablation indique de la redondance avec les autres familles).

AUC univariée — MOBILE_MONEY (15 meilleures variables, période d'entraînement) :

| Variable | AUC | Sens (+ = plus élevé en fraude) |
|---|---|---|
| log_device_prior_uses | 0.1807 | - |
| amount_to_balance | 0.7865 | + |
| amount_ratio_user_mean | 0.7652 | + |
| amount_zscore_user | 0.7651 | + |
| is_new_counterparty | 0.7589 | + |
| device_n_users | 0.7375 | + |
| log_secs_since_last_tx | 0.2705 | - |
| tx_count_1h | 0.703 | + |
| counterparty_n_users | 0.7005 | + |
| log_amount_usd | 0.6888 | + |
| debit_count_1h | 0.6861 | + |
| amount_to_kyc_limit | 0.6773 | + |
| type_P2P_SEND | 0.6521 | + |
| tx_count_24h | 0.6492 | + |
| hour_deviation_user | 0.6442 | + |

AUC univariée — VISA_VIRTUAL (15 meilleures variables, période d'entraînement) :

| Variable | AUC | Sens (+ = plus élevé en fraude) |
|---|---|---|
| log_device_prior_uses | 0.0014 | - |
| is_foreign_ip | 0.9707 | + |
| device_n_users | 0.9063 | + |
| debit_count_1h | 0.7802 | + |
| tx_count_1h | 0.7757 | + |
| log_secs_since_last_tx | 0.2578 | - |
| is_foreign_merchant | 0.7282 | + |
| tx_count_24h | 0.7155 | + |
| is_new_merchant | 0.7044 | + |
| night_unusual | 0.6991 | + |
| is_night | 0.6975 | + |
| type_CARD_TOPUP | 0.3212 | - |
| type_CARD_PURCHASE | 0.6788 | + |
| log_amount_usd | 0.3215 | - |
| is_high_risk_merchant | 0.6744 | + |

Contrôle de fuite d'information (variable seule d'AUC > 0.97) : VISA_VIRTUAL: ['log_device_prior_uses', 'is_foreign_ip']

## H3 — Les performances varient selon la famille de modèles

| Modèle | PR-AUC [IC95] | Δ vs XGBoost | Rappel à 1 % FP [IC95] |
|---|---|---|---|
| xgboost | 0.9893 [0.9857 ; 0.9917] | réf. | 0.9996 [0.9985 ; 1.0000] |
| random_forest | 0.9789 [0.9733 ; 0.9831] | -0.0104 [-0.0135 ; -0.0079] (significatif) | 0.9984 [0.9961 ; 1.0000] |
| regression_logistique | 0.9443 [0.9288 ; 0.9567] | -0.0450 [-0.0591 ; -0.0340] (significatif) | 0.9692 [0.9535 ; 0.9812] |
| isolation_forest | 0.3795 [0.3111 ; 0.4481] | -0.6098 [-0.6778 ; -0.5423] (significatif) | 0.4292 [0.3668 ; 0.5123] |
| regles_metier | 0.2726 [0.2405 ; 0.3041] | -0.7167 [-0.7477 ; -0.6845] (significatif) | 0.2860 [0.2516 ; 0.3194] |

Par canal (PR-AUC) :

| Modèle | Mobile Money | Visa virtuelle |
|---|---|---|
| xgboost | 0.9865 [0.9818 ; 0.9897] | 1.0000 [1.0000 ; 1.0000] |
| random_forest | 0.9732 [0.9651 ; 0.9789] | 1.0000 [1.0000 ; 1.0000] |
| regression_logistique | 0.9309 [0.9130 ; 0.9461] | 1.0000 [0.9999 ; 1.0000] |
| isolation_forest | 0.4733 [0.3726 ; 0.5903] | 0.6296 [0.5405 ; 0.7143] |
| regles_metier | 0.2303 [0.1967 ; 0.2609] | 0.6343 [0.5634 ; 0.7107] |

**Conclusion H3 : CONFIRMÉE** — modèles significativement différents de XGBoost : random_forest, regression_logistique, isolation_forest, regles_metier. Le modèle hybride (XGBoost + LSTM + autoencodeur) est évalué par `train_model.py` (voir phase3_model_comparison.csv).

## H4 — Transposition du Mobile Money vers la Visa virtuelle

Test Visa : 294 fraudes seulement (prévalence 0.02776) : lire les IC, qui sont larges. Seuil « honnête » = appris sur le Mobile Money.

| Entraînement | PR-AUC Visa [IC95] | Δ vs mixte | Rappel à 1 % FP [IC95] | F1 (seuil MM) | F1 (seuil recalibré Visa) |
|---|---|---|---|---|---|
| mm_seul | 0.9849 [0.9734 ; 0.9959] | -0.0151 [-0.0266 ; -0.0041] (significatif) | 0.9762 [0.9474 ; 1.0000] | 0.929 | 0.9496 |
| mm_seul_vars_communes | 0.9748 [0.9596 ; 0.9920] | -0.0252 [-0.0404 ; -0.0080] (significatif) | 0.9524 [0.9167 ; 0.9906] | 0.927 | 0.927 |
| mm+5%visa | 0.9977 [0.9930 ; 1.0000] | -0.0023 [-0.0070 ; +0.0000] (non significatif) | 0.9966 [0.9882 ; 1.0000] | 0.9702 | 0.9932 |
| mm+20%visa | 0.9988 [0.9959 ; 1.0000] | -0.0012 [-0.0041 ; +0.0000] (non significatif) | 0.9966 [0.9882 ; 1.0000] | 0.9932 | 0.9932 |
| visa_seule | 1.0000 [1.0000 ; 1.0000] | +0.0000 [-0.0000 ; +0.0000] (non significatif) | 1.0000 [1.0000 ; 1.0000] | 0.9983 | 0.9983 |
| mixte | 1.0000 [1.0000 ; 1.0000] | réf. | 1.0000 [1.0000 ; 1.0000] | 0.9966 | 0.9949 |
| regles_metier | 0.6343 [0.5634 ; 0.7107] | -0.3657 [-0.4366 ; -0.2893] (significatif) | 0.3878 [0.3230 ; 0.4541] | 0.6704 | 0.6704 |

Sens inverse et oubli (test Mobile Money) :

| Entraînement | PR-AUC Mobile Money [IC95] | Δ vs mixte |
|---|---|---|
| mixte | 0.9865 [0.9818 ; 0.9897] | réf. |
| mm_seul | 0.9868 [0.9821 ; 0.9899] | +0.0003 [-0.0004 ; +0.0010] (non significatif) |
| visa_seule | 0.5547 [0.4787 ; 0.6370] | -0.4318 [-0.5072 ; -0.3491] (significatif) |
| regles_metier | 0.2303 [0.1967 ; 0.2609] | -0.7562 [-0.7879 ; -0.7259] (significatif) |

Rapport de transfert (PR-AUC Mobile Money seul / modèle mixte, sur la Visa) = 0.9849 → transposabilité **forte** (≥ 0,9 forte ; 0,6-0,9 partielle ; < 0,6 faible — convention de ce rapport). Le modèle Mobile Money seul est 35.5× meilleur que le hasard (PR-AUC / prévalence).

**Conclusion H4** : transposabilité forte du CLASSEMENT des transactions (PR-AUC 0.9849 sans aucune donnée Visa). Le SEUIL, lui, se transpose moins bien : F1 0.929 avec le seuil Mobile Money contre 0.9496 une fois recalibré sur la Visa. Avec adaptation (mm+5%visa, mm+20%visa), l'écart au modèle mixte n'est plus significatif. Attention à l'effet plafond : la PR-AUC Visa du modèle mixte est proche de 1 ; la Visa simulée est très séparable (voir la variable d'AUC univariée > 0,95 dans H2), ce qui peut surestimer la transposabilité.

## RQ1 — Comportements transactionnels observables (échantillon complet)

**MOBILE_MONEY** — 598,515 transactions, taux de fraude 1.24%

| Indicateur | Légitime | Fraude |
|---|---|---|
| montant_median_usd | 24.11 | 95.0 |
| part_nuit | 0.0338 | 0.2689 |
| part_nouvel_appareil | 0.0 | 0.2112 |
| part_ip_etrangere | 0.0 | 0.0 |
| part_nouveau_destinataire | 0.0728 | 0.5978 |
| part_vidage_du_solde | 0.0098 | 0.1184 |
| ratio_montant_habitude_median | 0.7062 | 2.6693 |
| tx_24h_median | 1.0 | 2.0 |

**VISA_VIRTUAL** — 33,453 transactions, taux de fraude 3.06%

| Indicateur | Légitime | Fraude |
|---|---|---|
| montant_median_usd | 20.08 | 5.985 |
| part_nuit | 0.0366 | 0.4491 |
| part_nouvel_appareil | 0.0 | 0.3082 |
| part_ip_etrangere | 0.0229 | 0.9638 |
| part_nouveau_destinataire | 0.0 | 0.0 |
| part_vidage_du_solde | 0.0751 | 0.2006 |
| ratio_montant_habitude_median | 0.5299 | 0.2132 |
| tx_24h_median | 1.0 | 2.0 |

## Limites

- Données synthétiques : validité externe non démontrée ; à confirmer sur des données réelles d'opérateur.
- Test Visa petit (peu de fraudes) : conclusions H4 à nuancer par les IC.
- Une seule période et un seul découpage temporel ; la variance liée aux données n'est pas mesurée.
- Le test « statique » est défini ici par l'absence d'historique de l'usager ; une autre définition pourrait changer l'écart.
