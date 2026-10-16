# Évaluation de la boucle de retour des analystes

Rejeu mensuel de la période de test (13 mois, 183,240 transactions, 2,437 fraudes), branche XGBoost. Budget : 200 revues supplémentaires par mois ; 30% des fraudes manquées signalées par plainte. Métriques mesurées avant les étiquettes du mois, à partir du 2ᵉ mois.

| Stratégie | Poids des verdicts | AP moyenne | Rappel | Fraudes manquées | Fraudes trouvées par les revues |
|---|---|---|---|---|---|
| alertes_seules | 1 | 0.9932 | 96.90 % | 73 | 0 |
| temoin_aleatoire | 3 | 0.9948 | 97.41 % | 61 | 2 |
| incertitude_poids1 | 1 | 0.9955 | 97.83 % | 51 | 52 |
| incertitude_poids3 | 3 | 0.9961 | 98.39 % | 38 | 39 |
| incertitude_plus_temoin_poids3 | 3 | 0.9960 | 98.17 % | 43 | 42 |

## Estimation du taux de fraudes manquées par l'échantillon témoin

- **temoin_aleatoire** : l'intervalle de confiance à 95 % couvre le vrai taux 85 % des mois (13 mois).
- **incertitude_plus_temoin_poids3** : l'intervalle de confiance à 95 % couvre le vrai taux 100 % des mois (13 mois).

_Hypothèses : verdicts exacts, taux de plainte fixe ; la nouveauté et le réseau ne sont pas simulés._
