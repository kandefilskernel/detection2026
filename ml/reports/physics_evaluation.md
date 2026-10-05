# Modèle hybride : données + lois physiques

Lois : cinématique (déplacement entre provinces) et conservation (solde). Voir `ml/physics/laws.py`.

## A. Violations sur les données simulées

Cinématique nettement violée : 75 opérations légitimes (0.01% des légitimes) et 88 fraudes (1.04% des fraudes) ; précision des violations : 0.5399 pour un taux de fraude global de 0.01333.

**Lecture** : les déplacements légitimes de ce jeu respectent la physique (voyages réalistes) ; une violation nette de la cinématique est donc un signal fort : 54% des opérations qui la violent sont des fraudes, contre 1.33% en moyenne.

Conservation (débit supérieur au solde) : 5710 légitimes, 500 fraudes.

## B. Les valeurs physiques comme variables du modèle de données

| Modèle | PR-AUC test [IC95] | Δ vs données seules |
|---|---|---|
| données | 0.9886 [0.9848 ; 0.9911] | réf. |
| données + physique | 0.9887 [0.9850 ; 0.9914] | +0.0001 [-0.0003 ; +0.0007] (non significatif) |

Sur 5 graines d'entraînement : données 0.9888 ± 0.0004, données + physique 0.9889 ± 0.0002 (PR-AUC du test). Un écart du même ordre que l'écart-type est du bruit d'entraînement.

## C. Coût du mode « enforce »

0.01% des opérations légitimes du test seraient soumises à vérification ; 1.07% des fraudes seraient signalées par la physique.

## D. Robustesse : attaque « session relayée » injectée (jamais vue à l'entraînement)

300 attaques : appareil, type d'opération et montant habituels de la victime, mais depuis une province à 1568 km en moyenne, 3.0 min après une opération légitime.

| Détecteur | Attaques détectées | Fausses alertes (vraies opérations légitimes) |
|---|---|---|
| Modèle de données (seuil F1) | 0.3% | 0.12% |
| Modèle de données (seuil à 1 % de faux positifs) | 7.0% | 1,00 % |
| Physique seule | 100.0% | 0.01% |
| **Hybride (données OU physique)** | **100.0%** | 0.13% |

IC95 du rappel : données [0.0, 0.01] ; hybride [1.0, 1.0].

**Limites** : D est un scénario construit par l'équipe, pas une mesure sur des fraudes réelles. Les coordonnées sont celles des chefs-lieux.
