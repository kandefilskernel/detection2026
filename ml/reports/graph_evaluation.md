# Évaluation de l'analyse de réseau

Rejeu chronologique ; validation dès 2023-03-02, test dès 2024-12-13 (183,240 transactions, 2,437 fraudes). Verdicts révélés après 7 jours. Vérité du générateur : {'W': 400, 'D': 150, 'A': 24, 'U': 7}.

## A. Transactions (période de test)

### Étiquettes différées seulement

Seuil réseau choisi sur la validation pour 0.5 % de fausses alertes : 0.593.

| Règle | Rappel | Fausses alertes | Précision | AP |
|---|---|---|---|---|
| Modèle hybride seul | 97.8 % | 0.1 % | 95.1 % | 0.996 |
| Réseau seul | 97.4 % | 0.5 % | 74.1 % | 0.976 |
| Modèle OU réseau | 100.0 % | 0.5 % | 71.9 % | — |

Fraudes rattrapées par le réseau (manquées par le modèle) : **54**, pour 831 fausses alertes supplémentaires.

| Typologie | Fraudes | Modèle | Modèle OU réseau | Rattrapées |
|---|---|---|---|---|
| ACCOUNT_TAKEOVER | 406 | 100.0 % | 100.0 % | 0 |
| AGENT_FRAUD | 181 | 100.0 % | 100.0 % | 0 |
| CARD_TESTING | 81 | 100.0 % | 100.0 % | 0 |
| CNP_FRAUD | 131 | 100.0 % | 100.0 % | 0 |
| SIM_SWAP | 623 | 100.0 % | 100.0 % | 0 |
| SMURFING | 303 | 98.7 % | 100.0 % | 4 |
| SOCIAL_ENGINEERING | 630 | 92.1 % | 100.0 % | 50 |
| TOPUP_DRAIN | 82 | 100.0 % | 100.0 % | 0 |

### Étiquettes différées + probabilités du modèle

Seuil réseau choisi sur la validation pour 0.5 % de fausses alertes : 0.593.

| Règle | Rappel | Fausses alertes | Précision | AP |
|---|---|---|---|---|
| Modèle hybride seul | 97.8 % | 0.1 % | 95.1 % | 0.996 |
| Réseau seul | 97.4 % | 0.5 % | 74.1 % | 0.976 |
| Modèle OU réseau | 100.0 % | 0.5 % | 72.0 % | — |

Fraudes rattrapées par le réseau (manquées par le modèle) : **54**, pour 828 fausses alertes supplémentaires.

| Typologie | Fraudes | Modèle | Modèle OU réseau | Rattrapées |
|---|---|---|---|---|
| ACCOUNT_TAKEOVER | 406 | 100.0 % | 100.0 % | 0 |
| AGENT_FRAUD | 181 | 100.0 % | 100.0 % | 0 |
| CARD_TESTING | 81 | 100.0 % | 100.0 % | 0 |
| CNP_FRAUD | 131 | 100.0 % | 100.0 % | 0 |
| SIM_SWAP | 623 | 100.0 % | 100.0 % | 0 |
| SMURFING | 303 | 98.7 % | 100.0 % | 4 |
| SOCIAL_ENGINEERING | 630 | 92.1 % | 100.0 % | 50 |
| TOPUP_DRAIN | 82 | 100.0 % | 100.0 % | 0 |

## B. Entités partagées (fin du test, avec étiquettes)

14,970 entités partagées, dont 574 réellement frauduleuses.

| Classement | p@25 | p@50 | p@100 | p@200 |
|---|---|---|---|---|
| nb_comptes_distincts (variable déjà dans le modèle) | 0.0 % | 2.0 % | 2.0 % | 7.0 % |
| risque_direct | 68.0 % | 70.0 % | 78.0 % | 88.0 % |
| score_reseau (direct + propagé) | 68.0 % | 72.0 % | 79.0 % | 88.0 % |

Comptes mules parmi les 10 comptes les plus exposés : 1.

## B'. Entités partagées sans aucune étiquette

5,362 entités partagées, dont 489 réellement frauduleuses.

| Classement | p@25 | p@50 | p@100 | p@200 |
|---|---|---|---|---|
| nb_comptes_distincts (variable déjà dans le modèle) | 0.0 % | 0.0 % | 0.0 % | 0.0 % |
| risque_direct | 96.0 % | 94.0 % | 90.0 % | 92.5 % |
| score_reseau (direct + propagé) | 96.0 % | 94.0 % | 93.0 % | 93.0 % |

Comptes mules parmi les 10 comptes les plus exposés : 5.

## C. Réseaux détectés

**Historique complet (avec étiquettes)** : 1 réseaux (582 entités) ; le plus grand relie 467 comptes. Pureté (entités réellement frauduleuses) : 95.7 % ; couverture des entités frauduleuses partagées : 97.0 %.

**30 derniers jours, probabilités du modèle seulement (écran Réseaux)** : 3 réseaux (16 entités) ; le plus grand relie 12 comptes. Pureté (entités réellement frauduleuses) : 100.0 % ; couverture des entités frauduleuses partagées : 44.4 %.

_Le générateur réutilise un nombre fini de mules et d'appareils de fraudeurs : l'ampleur du gain dépend de cette hypothèse de simulation._
