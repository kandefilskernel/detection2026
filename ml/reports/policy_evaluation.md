# Politique de décision : seuil unique contre coût

Seconde moitié chronologique du test : 91,620 transactions, 1,207 fraudes ; réglage sur la première moitié (91,620). Toutes les politiques sont jugées avec les mêmes coûts métier (coûts par défaut). Seuil F1 du modèle : 0.538.

| Politique | Perte totale (USD) | Fraude non stoppée | Friction | Faux blocages | Fraudes stoppées | Clients honnêtes gênés | Blocages | Vérifications |
|---|---|---|---|---|---|---|---|---|
| Seuil F1 → blocage | 2,354 | 1,807 | 0 | 547 | 98.4 % | 0.08 % | 1,263 | 0 |
| Seuil F1 → vérification | 38,292 | 37,933 | 359 | 0 | 98.4 % | 0.08 % | 0 | 1,263 |
| Coût, paramètres par défaut | 1,017 | 133 | 153 | 730 | 99.9 % | 0.63 % | 1,261 | 511 |
| Coût, paramètres réglés | 976 | 236 | 164 | 576 | 99.9 % | 0.63 % | 1,225 | 547 |

Paramètres réglés : réglée (plancher 0.9, faux blocage x2.0, friction x1.0).

_Coûts métier : hypothèses de simulation à remplacer par les coûts réels de chaque opérateur._
