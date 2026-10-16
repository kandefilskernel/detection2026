# Étude comparative des méthodes d'apprentissage et choix du modèle

Période de test jamais vue à l'entraînement : 183 240 transactions, 2 437 fraudes. Seuils choisis sur la validation. **Données simulées.**

## 1. Performances

| Méthode | Famille | PR-AUC | ROC-AUC | Précision | Rappel | F1 | Taux de FP |
|---|---|---|---|---|---|---|---|
| Hybride | Empilement (XGBoost + LSTM + autoencodeur) | 0,9955 | 0,9999 | 0,951 | 0,978 | 0,964 | 0,067 % |
| XGBoost | Ensemble d'arbres (boosting) | 0,9895 | 0,9998 | 0,918 | 0,959 | 0,938 | 0,116 % |
| LSTM-attention | Réseau récurrent | 0,9894 | 0,9998 | 0,930 | 0,967 | 0,948 | 0,098 % |
| Random Forest | Ensemble d'arbres (bagging) | 0,9842 | 0,9998 | 0,934 | 0,929 | 0,931 | 0,088 % |
| Régression logistique | Linéaire | 0,9513 | 0,9989 | 0,882 | 0,868 | 0,875 | 0,157 % |
| Autoencodeur | Anomalie (non supervisé) | 0,7094 | 0,9708 | 0,959 | 0,616 | 0,750 | 0,035 % |
| Isolation Forest | Anomalie (non supervisé) | 0,3913 | 0,9487 | 0,428 | 0,395 | 0,411 | 0,710 % |
| Règles métier | Système expert | 0,2755 | 0,7841 | 0,371 | 0,357 | 0,364 | 0,815 % |

Figures : `figures/comparaison_modeles.png`, `figures/courbes_precision_rappel.png`.

## 2. Significativité (bootstrap apparié par usager, 1 000 tirages ; McNemar exact)

| Comparaison | Écart de PR-AUC [IC 95 %] | McNemar (seul juste) | p | Significatif |
|---|---|---|---|---|
| Hybride − XGBoost | +0,0060 [+0,0044 ; +0,0079] | 156 contre 23 | 1,8 × 10^-25 | oui |
| Hybride − LSTM-attention | +0,0061 [+0,0045 ; +0,0078] | 157 contre 75 | 7,8 × 10^-8 | oui |
| Hybride − Autoencodeur | +0,2861 [+0,2306 ; +0,3417] | 943 contre 118 | 2,5 × 10^-160 | oui |
| XGBoost − Random Forest | +0,0104 [+0,0079 ; +0,0135] | — | — | oui |
| XGBoost − Régression logistique | +0,0450 [+0,0340 ; +0,0591] | — | — | oui |
| XGBoost − Isolation Forest | +0,6098 [+0,5423 ; +0,6778] | — | — | oui |
| XGBoost − Règles métier | +0,7167 [+0,6845 ; +0,7477] | — | — | oui |

## 3. Erreurs au seuil retenu

| Méthode | Fausses alertes | Fraudes manquées |
|---|---|---|
| Hybride | 122 | 54 |
| XGBoost | 210 | 99 |
| LSTM-attention | 178 | 80 |
| Autoencodeur | 64 | 937 |

## 4. Rappel par typologie

| Typologie | n | Hybride | XGBoost | LSTM-attention | Autoencodeur |
|---|---|---|---|---|---|
| SOCIAL_ENGINEERING | 630 | 0,921 | 0,859 | 0,882 | 0,003 |
| SIM_SWAP | 623 | 1,000 | 1,000 | 1,000 | 0,998 |
| ACCOUNT_TAKEOVER | 406 | 1,000 | 1,000 | 1,000 | 0,988 |
| SMURFING | 303 | 0,987 | 0,974 | 0,987 | 0,000 |
| AGENT_FRAUD | 181 | 1,000 | 1,000 | 1,000 | 1,000 |
| CNP_FRAUD | 131 | 1,000 | 0,985 | 0,985 | 1,000 |
| TOPUP_DRAIN | 82 | 1,000 | 1,000 | 1,000 | 1,000 |
| CARD_TESTING | 81 | 1,000 | 1,000 | 1,000 | 1,000 |

## 5. Matrice de décision multicritère (notes de 1 à 5)

| Méthode | PR-AUC (30 %) | F1 / fausses alertes (20 %) | Explicabilité (15 %) | Temps réel et simplicité (15 %) | Dynamique (séquence) (10 %) | Fraudes inédites (10 %) | Score pondéré | Poids égaux | 1er sur tirages |
|---|---|---|---|---|---|---|---|---|---|
| Hybride | 5 | 5 | 4 | 3 | 5 | 4 | **4,45** | 4,33 | 91 % |
| XGBoost | 4 | 4 | 4 | 5 | 2 | 1 | **3,65** | 3,33 | 5 % |
| LSTM-attention | 4 | 4 | 2 | 3 | 5 | 2 | **3,45** | 3,33 | 0 % |
| Random Forest | 4 | 4 | 3 | 4 | 1 | 1 | **3,25** | 2,83 | 0 % |
| Régression logistique | 3 | 3 | 5 | 5 | 1 | 1 | **3,20** | 3,00 | 3 % |
| Autoencodeur | 2 | 2 | 2 | 4 | 1 | 5 | **2,50** | 2,67 | 1 % |
| Règles métier | 1 | 1 | 5 | 5 | 1 | 2 | **2,30** | 2,50 | 0 % |
| Isolation Forest | 1 | 1 | 2 | 4 | 1 | 4 | **1,90** | 2,17 | 0 % |

Notes de PR-AUC et de F1 calculées à partir des mesures (seuils [(0.995, 5), (0.98, 4), (0.94, 3), (0.6, 2)] et [(0.96, 5), (0.93, 4), (0.85, 3), (0.6, 2)]). Justification des autres notes :

- **Explicabilité** : règles et régression logistique transparentes (5) ; TreeSHAP exact pour XGBoost, conservé par l'hybride avec la contribution des composantes et l'attention (4) ; Random Forest (3) ; attention seule ou score d'anomalie global (2).
- **Temps réel et simplicité** : modèles linéaires et arbres très rapides (4-5) ; LSTM et hybride plus coûteux en calcul et en maintenance (3).
- **Dynamique (séquence)** : seuls le LSTM et l'hybride lisent la séquence des opérations (5) ; XGBoost n'en voit qu'un résumé par les variables de fréquence (2).
- **Fraudes inédites** : autoencodeur et Isolation Forest apprennent sans étiquette (5, 4) ; l'hybride hérite de l'autoencodeur et des lois physiques (4) ; méthodes supervisées limitées aux fraudes connues (1).

Robustesse : 2 000 pondérations tirées au hasard (Dirichlet) ; colonne « 1er sur tirages ».

## 6. Décision

**Modèle retenu : Hybride** (score 4,45 / 5, contre 3,65 pour XGBoost).

1. meilleure PR-AUC (0,9955) et meilleur F1 (0,964) sur la période de test
2. supériorité significative sur chacune des composantes seules (IC 95 % excluant 0, McNemar p < 0,05)
3. 42 % de fausses alertes et 45 % de fraudes manquées en moins que XGBoost seul
4. couvre le profil instantané (XGBoost), la dynamique (LSTM) et l'anomalie (autoencodeur)
5. reste explicable (TreeSHAP, contribution des composantes, attention) et compatible avec le temps réel

Latence de bout en bout (rejeu) : médiane 59,5 ms, 95ᵉ centile 104,4 ms.
Attaque par relais inédite : rappel 0,3 % pour le modèle de données seul, 100 % avec les lois physiques.
