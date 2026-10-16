# Matrices de confusion

Période de test (jamais vue à l'entraînement), 183 240 transactions, seuil opérationnel choisi sur la validation. **Données simulées.**

## 1. Détecteur principal (fraude / légitime)

| Périmètre | VP | FN | FP | VN | Précision | Rappel | F1 | Taux de FP |
|---|---|---|---|---|---|---|---|---|
| Global | 2 383 | 54 | 122 | 180 681 | 95.13% | 97.78% | 0.9644 | 0.067% |
| Mobile Money | 2 089 | 54 | 122 | 170 383 | 94.48% | 97.48% | 0.9596 | 0.072% |
| Visa virtuelle | 294 | 0 | 0 | 10 298 | 100.00% | 100.00% | 1.0000 | 0.000% |

Lecture (global) :

|  | Prédit légitime | Prédit fraude |
|---|---|---|
| **Réel légitime** | 180 681 (VN) | 122 (FP : fausses alertes) |
| **Réel fraude** | 54 (FN : fraudes manquées) | 2 383 (VP) |

Figures : `figures/confusion_global.png`, `figures/confusion_mobile_money.png`, `figures/confusion_visa_virtual.png`.

## 2. Classifieur de type de fraude (fraudes du test)

Exactitude 96.22%, F1 macro 0.9713. Lignes = type réel, colonnes = type prédit.

| Réel \ Prédit | ACCOUNT_TAKEOVER | AGENT_FRAUD | CARD_TESTING | CNP_FRAUD | SIM_SWAP | SMURFING | SOCIAL_ENGINEERING | TOPUP_DRAIN | Rappel |
|---|---|---|---|---|---|---|---|---|---|
| **ACCOUNT_TAKEOVER** | 380 | 0 | 0 | 0 | 26 | 0 | 0 | 0 | 93.6% |
| **AGENT_FRAUD** | 0 | 181 | 0 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| **CARD_TESTING** | 0 | 0 | 79 | 2 | 0 | 0 | 0 | 0 | 97.5% |
| **CNP_FRAUD** | 0 | 0 | 2 | 129 | 0 | 0 | 0 | 0 | 98.5% |
| **SIM_SWAP** | 54 | 8 | 0 | 0 | 561 | 0 | 0 | 0 | 90.0% |
| **SMURFING** | 0 | 0 | 0 | 0 | 0 | 303 | 0 | 0 | 100.0% |
| **SOCIAL_ENGINEERING** | 0 | 0 | 0 | 0 | 0 | 0 | 630 | 0 | 100.0% |
| **TOPUP_DRAIN** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 82 | 100.0% |

Figure : `figures/confusion_fraud_type.png`.
- ACCOUNT_TAKEOVER confondu avec SIM_SWAP (6%)
- SIM_SWAP confondu avec ACCOUNT_TAKEOVER (9%)
