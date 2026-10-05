# Courbes d'apprentissage

Réentraînement de diagnostic (rapide, 74 s). Perte d'entraînement comparée à la perte sur la tranche early_stop (données jamais vues pendant l'apprentissage).

| Branche | Verdict | Époque retenue | Perte entraînement | Perte validation | Écart de généralisation |
|---|---|---|---|---|---|
| xgboost (logloss / itération) | **SAIN** | 149/150 | 0.01785 | 0.01748 | -2.1% |
| lstm_attention (BCE / époque) | **SURAPPRENTISSAGE_LEGER** | 2/2 | 0.01617 | 0.02244 | 38.8% |
| autoencoder (MSE / époque) | **SOUS_APPRENTISSAGE** | 4/4 | 0.32881 | 0.32347 | -1.6% |

- xgboost : pertes d'entraînement et de validation proches et stables
- lstm_attention : écart de généralisation 39%
- autoencoder : la perte baisse encore à la dernière époque (arrêt par le nombre d'époques)

Pire verdict : **SURAPPRENTISSAGE_LEGER**. Seuil de blocage du réentraînement automatique : écart > 100 % (`OVERFIT_MAX_GAP`).
