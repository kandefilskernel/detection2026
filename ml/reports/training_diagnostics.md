# Courbes d'apprentissage

Réentraînement de diagnostic (configuration complète, 377 s). Perte d'entraînement comparée à la perte sur la tranche early_stop (données jamais vues pendant l'apprentissage).

| Branche | Verdict | Époque retenue | Perte entraînement | Perte validation | Écart de généralisation |
|---|---|---|---|---|---|
| xgboost (logloss / itération) | **SURAPPRENTISSAGE_LEGER** | 538/588 | 0.00086 | 0.00462 | 436.8% |
| lstm_attention (BCE / époque) | **SURAPPRENTISSAGE_LEGER** | 7/8 | 0.00924 | 0.01193 | 29.1% |
| autoencoder (MSE / époque) | **SAIN** | 30/30 | 0.1994 | 0.21626 | 8.5% |

- xgboost : perte de validation 437% au-dessus de celle d'entraînement mais PR-AUC quasi identique (écart 0.006) : modèle très confiant sur ses données d'entraînement, sans perte de performance
- lstm_attention : la perte de validation remonte de 12% alors que celle d'entraînement baisse
- autoencoder : pertes d'entraînement et de validation proches et stables

Pire verdict : **SURAPPRENTISSAGE_LEGER**. Blocage du réentraînement automatique : PR-AUC plus basse de plus de 0,05 en validation (`OVERFIT_MAX_METRIC_GAP`), ou, sans PR-AUC, perte de validation plus du double (`OVERFIT_MAX_GAP`).
