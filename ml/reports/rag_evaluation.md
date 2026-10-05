# Évaluation du RAG (mémoire de cas)

Index : 64,003 cas de la période d'entraînement. Paramètres choisis sur la validation : k = 7, similarité minimale = 0.2. Évaluation sur le test, modèle = XGBoost (seuil F1 de la validation).

## Les cas proches reconnaissent-ils la fraude seuls ?

PR-AUC de la part de fraude parmi les voisins : **0.9604** [IC95 0.9495 ; 0.9702] (modèle : 0.9895). Opérations comparables aux cas connus : 99.8%.

## Les alertes du modèle selon l'avis des cas proches

| Avis des cas proches | Alertes | Vraies fraudes | Précision [IC95] |
|---|---|---|---|
| Confirment (COHERENT) | 1978 | 1939 | 0.9803 [0.9718, 0.9868] |
| Contredisent (DIVERGENT) | 437 | 266 | 0.6087 [0.55, 0.6611] |
| Peu comparables (INSUFFISANT) | 133 | 133 | 1.0 |

Précision globale des alertes du modèle : 0.9176.

## Fraudes manquées par le modèle

99 fraudes du test ne sont pas alertées ; les cas proches en retrouvent 22, au prix de 53 fausses alertes supplémentaires si on les ajoutait aux alertes.

## Type de fraude

Type majoritaire des cas proches : exactitude 0.8802 (classifieur de type : 0.9622).
