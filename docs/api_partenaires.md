# API partenaires — guide d'intégration

API REST qui permet à toute institution (opérateur Mobile Money, banque, émetteur de cartes, régulateur) d'utiliser le système de détection de fraude.

- **Adresse** : `https://<serveur>/v1/…` (en local : `http://localhost/v1/…`)
- **Documentation interactive** (OpenAPI / Swagger) : `/v1/docs` ; ReDoc : `/v1/redoc` ; schéma : `/v1/openapi.json`
- **Authentification** : en-tête `X-API-Key: nuru_…`, délivré par l'administrateur du système (page *Institutions & API* du back-office).
- **Format** : JSON, UTF-8. Horodatages ISO 8601. Sans fuseau horaire, l'heure est lue comme l'heure de Kinshasa.

## 1. Institutions et droits

| Type | Droits par défaut | Usage |
|---|---|---|
| `OPERATEUR_MM` | `transactions`, `feedback` | Vodacom, Airtel, Orange… |
| `BANQUE` | `transactions`, `feedback` | banques commerciales |
| `EMETTEUR_CARTE` | `transactions`, `feedback` | émetteurs de cartes Visa virtuelles |
| `REGULATEUR` | `supervision` | Banque Centrale du Congo (BCC) : lecture seule, agrégats sans donnée personnelle |

| Droit | Ce qu'il permet |
|---|---|
| `transactions` | soumettre des transactions, consulter **ses** décisions et **ses** statistiques |
| `feedback` | signaler qu'une de **ses** transactions était, ou non, une fraude |
| `supervision` | statistiques agrégées de **toutes** les institutions |

**Isolement des données.** Chaque transaction est rattachée à l'institution qui l'a soumise. Ce rattachement est fixé par le serveur d'après la clé, jamais par le client. Une institution ne peut ni lire ni étiqueter la transaction d'une autre : elle reçoit la même réponse 404 que pour une transaction inexistante.

**Gestion des clés.** La clé n'est affichée qu'une fois, à la création ou au renouvellement. Le système ne conserve que son empreinte SHA-256. Une clé renouvelée ou révoquée cesse de fonctionner en moins de 30 secondes.

## 2. Points d'entrée

| Méthode | Chemin | Droit | Rôle |
|---|---|---|---|
| GET | `/v1/me` | aucun | institution associée à la clé et droits accordés |
| POST | `/v1/transactions` | `transactions` | scorer une transaction au **format commun** |
| POST | `/v1/transactions/{format}` | `transactions` | scorer au format natif `vodacom`, `airtel`, `orange` ou `visa` (si l'institution y est autorisée) |
| GET | `/v1/transactions/{id}` | `transactions` | décision enregistrée, état du dossier, étiquette |
| POST | `/v1/feedback` | `feedback` | fraude constatée, ou fausse alerte, sur une de vos transactions |
| GET | `/v1/stats?days=30` | `transactions` | statistiques de votre institution |
| GET | `/v1/supervision/summary?days=30` | `supervision` | agrégats par institution, canal, opération, province et type de fraude |
| GET | `/v1/supervision/daily?days=90&institution=` | `supervision` | évolution quotidienne |

## 3. Scorer une transaction (format commun)

À appeler **avant d'exécuter** l'opération, puis appliquer la décision.

```bash
curl -X POST http://localhost/v1/transactions \
  -H "X-API-Key: nuru_…" -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "RB-2026-000123",
    "timestamp": "2026-10-06T09:15:00",
    "user_id": "CLIENT-42",
    "channel": "MOBILE_MONEY",
    "tx_type": "P2P_SEND",
    "access_channel": "APP",
    "amount": 150000,
    "currency": "CDF",
    "balance_before_usd": 400.0,
    "device_id": "DEV-8f2a",
    "location_province": "Kinshasa",
    "counterparty_id": "CLIENT-77",
    "memo": "remboursement"
  }'
```

| Champ | Obligatoire | Valeurs |
|---|---|---|
| `transaction_id` | oui | unique chez l'institution (1 à 64 caractères) |
| `timestamp` | oui | ISO 8601 |
| `user_id` | oui | identifiant stable du client (pseudonyme accepté) |
| `channel` | oui | `MOBILE_MONEY`, `VISA_VIRTUAL` |
| `tx_type` | oui | `P2P_SEND`, `P2P_RECEIVE`, `CASH_IN`, `CASH_OUT`, `MERCHANT_PAYMENT`, `AIRTIME`, `BILL_PAYMENT`, `CARD_TOPUP`, `CARD_PURCHASE` |
| `access_channel` | oui | `USSD`, `APP`, `AGENT` |
| `amount`, `currency` | oui | montant > 0 ; `CDF` ou `USD` |
| `amount_usd` | non | converti par le serveur au taux de l'année de l'opération s'il est absent |
| `balance_before_usd` | oui | solde avant l'opération |
| `device_id` | oui | identifiant de l'appareil |
| `location_province` | oui | province de la RDC |
| `counterparty_id`, `merchant_id`, `merchant_category`, `merchant_country`, `agent_id`, `ip_country`, `device_type`, `wallet_id`, `card_id` | non | améliorent la détection |
| `memo` | non | motif saisi par le client ; analysé (ingénierie sociale) puis jamais stocké en clair |

Réponse :

```json
{
  "transaction_id": "RB-2026-000123",
  "action": "VERIFY",
  "risk_level": "ELEVE",
  "fraud_probability": 0.71,
  "fraud_type": "SOCIAL_ENGINEERING",
  "reason": "…",
  "institution": "rawbank",
  "end_to_end_ms": 38.2
}
```

| `action` | Ce que fait l'institution |
|---|---|
| `APPROVE` | exécuter l'opération |
| `VERIFY` | confirmer avec le client (OTP, appel) avant d'exécuter |
| `BLOCK` | suspendre l'opération et ouvrir une vérification |

**Rejeu sans risque.** En cas de délai dépassé, renvoyez la même transaction (même `transaction_id`) : la décision d'origine est renvoyée, et le profil du client n'est pas compté deux fois.

**Indisponibilité.** Si le moteur de scoring ne répond pas, l'API applique la politique de repli configurée et l'indique dans `reason` : `VERIFY` par défaut, `APPROVE` si `FAIL_OPEN=true`.

## 4. Signaler une fraude constatée

Une plainte, une enquête ou une rétrofacturation a confirmé, ou infirmé, une fraude. Le verdict clôt le dossier et devient une **étiquette** pour le prochain réentraînement du modèle. C'est ainsi que le système apprend les fraudes qu'il a manquées.

```bash
curl -X POST http://localhost/v1/feedback \
  -H "X-API-Key: nuru_…" -H "Content-Type: application/json" \
  -d '{"transaction_id": "RB-2026-000123", "verdict": "FRAUDE", "fraud_type": "SIM_SWAP",
       "note": "plainte du client : carte SIM remplacée la veille"}'
```

- `verdict` : `FRAUDE` ou `LEGITIME`.
- `note` : 5 à 2000 caractères.
- `fraud_type` (facultatif) : `SIM_SWAP`, `SOCIAL_ENGINEERING`, `ACCOUNT_TAKEOVER`, `AGENT_FRAUD`, `SMURFING`, `CARD_TESTING`, `CNP_FRAUD`, `TOPUP_DRAIN`.
- La réponse indique `missed_by_model: true` quand la fraude avait été laissée passer.

## 5. Supervision (régulateur)

```bash
curl http://localhost/v1/supervision/summary?days=30 -H "X-API-Key: nuru_…(clé BCC)"
```

La réponse contient, par institution, canal, opération, province et type de fraude :
- le volume et le nombre d'alertes ;
- les montants traités et bloqués ;
- les fraudes confirmées, les fraudes manquées et les fausses alertes.

Elle ne contient **aucune donnée personnelle** : ni client, ni appareil, ni numéro. Chaque consultation est inscrite au journal d'audit.

## 6. Codes de réponse

| Code | Signification |
|---|---|
| 200, 201 | succès |
| 401 | clé absente, invalide ou révoquée |
| 403 | droit non accordé à l'institution, ou format natif non autorisé |
| 404 | transaction inconnue ou appartenant à une autre institution. Juste après le scoring, l'enregistrement peut prendre quelques secondes : réessayer. |
| 409 | transaction déjà étiquetée, ou dossier déjà clos |
| 422 | message invalide (le détail indique le champ) |
| 429 | trop de requêtes : limite de 200 par seconde et par adresse, avec une rafale de 400 |
| 503 | vérification de la clé momentanément impossible : réessayer |

## 7. Avant une mise en production

Pour une ouverture à de vraies institutions, il faut aussi :
- **HTTPS obligatoire**, et mTLS pour les banques ;
- un environnement de test (bac à sable) ;
- un contrat de niveau de service ;
- un accord de traitement des données (loi congolaise, exigences de la BCC) ;
- le renouvellement périodique des clés.

Voir aussi `docs/uml/diagramme_composants.puml`.
