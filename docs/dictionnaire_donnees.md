# Dictionnaire de données

Trois niveaux de données :
1. **Données brutes** (`ml/data/raw/`) : transactions, clients, agents et marchands produits par le générateur
   (jeu pluriannuel 2019-2025 : 631 968 transactions, 500 clients, 800 agents, 900 marchands).
2. **Variables dérivées** (`ml/features/feature_engineering.py`) : 58 variables de profilage comportemental, entrées du
   modèle, et 6 variables physiques.
3. **Base opérationnelle** (PostgreSQL / TimescaleDB, `shared/database/models.py`) : décisions, dossiers, audit, modèles.

Légende du rôle : **ID** identifiant · **E** information disponible à l'entrée (utilisable par le modèle après
transformation) · **C** cible · **H** caché (vérité terrain, interdit en entrée : fuite garantie) · **D** dérivé.

---

## 1. Données brutes

### 1.1 `transactions.csv` — une ligne par opération

| Colonne | Type | Domaine / format | Description | Exemple | Rôle |
|---|---|---|---|---|---|
| `transaction_id` | texte | `TX` + 16 hexadécimaux, unique | Identifiant de l'opération | `TX5349cf0a4e187da3` | ID |
| `timestamp` | date-heure | `AAAA-MM-JJ hh:mm:ss`, heure locale RDC | Date et heure de l'opération | `2019-01-01 00:25:59` | E |
| `user_id` | texte | `U` + 6 chiffres | Titulaire du compte (portefeuille et carte) | `U000375` | ID |
| `wallet_id` | texte | MSISDN fictif `243…` | Numéro du portefeuille Mobile Money | `243826851728` | ID |
| `card_id` | texte | `CARD` + 10 chiffres, vide hors carte | Carte Visa virtuelle | `CARD0012345678` | ID |
| `channel` | catégorie | `MOBILE_MONEY`, `VISA_VIRTUAL` | Canal de paiement | `MOBILE_MONEY` | E |
| `operator` | catégorie | `VODACOM`, `AIRTEL`, `ORANGE` | Opérateur du portefeuille | `VODACOM` | E |
| `tx_type` | catégorie | voir §4 | Type d'opération | `MERCHANT_PAYMENT` | E |
| `access_channel` | catégorie | `USSD`, `APP`, `AGENT` | Moyen d'accès | `USSD` | E |
| `amount` | décimal | > 0 | Montant dans la devise de l'opération | `16005.0` | E |
| `currency` | catégorie | `CDF`, `USD` | Devise | `CDF` | E |
| `amount_usd` | décimal | > 0 | Montant converti en USD (taux de l'année) | `9.70` | E |
| `balance_before_usd` | décimal | ≥ 0 | Solde du compte débité ou crédité avant l'opération | `24.05` | E |
| `balance_after_usd` | décimal | ≥ 0 | Solde après l'opération (inchangé si échec) | `14.35` | H (connu après exécution) |
| `status` | catégorie | `SUCCESS`, `FAILED_INSUFFICIENT_FUNDS` | Résultat de l'opération | `SUCCESS` | H (inconnu au moment du score) |
| `counterparty_id` | texte | MSISDN ou opérateur | Contrepartie (transfert) ou opérateur (crédit téléphonique) | `243917538864` | E |
| `merchant_id` | texte | `M` + 7 chiffres | Marchand (paiement, facture, achat carte) | `M3135526` | E |
| `merchant_category` | catégorie | voir §4 | Catégorie du marchand | `BOUTIQUE` | E |
| `merchant_country` | texte | code pays ISO-2 | Pays du marchand | `CD` | E |
| `agent_id` | texte | `A` + 6 chiffres | Agent (dépôt, retrait) | `A535964` | E |
| `device_id` | texte | `DEV` + 12 hexadécimaux | Empreinte de l'appareil | `DEV57b52acf7306` | E |
| `device_type` | catégorie | `smartphone`, `feature_phone` | Type d'appareil | `feature_phone` | E |
| `ip_country` | texte | ISO-2, vide hors application | Pays de l'adresse IP | `CD` | E |
| `location_province` | catégorie | une des provinces (§4) | Province d'où l'opération est initiée | `Kasai-Oriental` | E |
| `is_fraud` | entier | 0 / 1 | **Cible** : l'opération fait partie d'un épisode de fraude | `0` | C |
| `fraud_type` | catégorie | voir §4, vide si légitime | Typologie (analyse et second étage uniquement) | `SIM_SWAP` | H |
| `fraud_episode_id` | texte | `EP` + 5 chiffres | Regroupe les opérations d'un même épisode | `EP00042` | H |

### 1.2 `users.csv` — un client par ligne

| Colonne | Type | Domaine | Description | Rôle |
|---|---|---|---|---|
| `user_id` | texte | `U` + 6 chiffres | Identifiant du client | ID |
| `wallet_id` | texte | MSISDN fictif | Portefeuille principal | ID |
| `operator` | catégorie | `VODACOM`, `AIRTEL`, `ORANGE` | Opérateur | E |
| `province` | catégorie | provinces (§4) | Province de résidence | E |
| `city` | texte | chef-lieu | Ville principale | E |
| `segment` | catégorie | `etudiant`, `commercant`, `salarie`, `informel`, `agriculteur`, `diaspora_beneficiaire` | Profil socio-économique | E |
| `kyc_level` | entier | 1, 2, 3 | Niveau de vérification d'identité | E |
| `kyc_tx_limit_usd` | décimal | 150, 1 500, 5 000 | Plafond par opération (paramètre de simulation, pas le plafond officiel BCC) | E |
| `device_type` | catégorie | `smartphone`, `feature_phone` | Appareil principal | E |
| `primary_device_id` | texte | `DEV…` | Appareil principal | E |
| `account_age_days` | entier | négatif possible | Ancienneté du compte au début de la période ; **négatif** = compte ouvert pendant la période, ‖valeur‖ jours après le début | E |
| `monthly_income_usd` | décimal | ≥ 0 | Revenu mensuel déclaré | E |
| `preferred_currency` | catégorie | `CDF`, `USD` | Devise habituelle | E |
| `has_visa_virtual` | booléen | — | Détient une carte Visa virtuelle | E |
| `card_id` | texte | `CARD…` | Carte, si elle existe | ID |
| `typical_amount_usd` | décimal | > 0 | Montant typique (paramètre de simulation) | H |
| `is_mule_account` | booléen | — | Compte « mule » (vérité terrain) | H |

### 1.3 `agents.csv`

| Colonne | Type | Domaine | Description | Rôle |
|---|---|---|---|---|
| `agent_id` | texte | `A` + 6 chiffres | Identifiant de l'agent | ID |
| `province` | catégorie | provinces | Province de l'agent | E |
| `operator` | catégorie | opérateurs | Opérateur de rattachement | E |
| `device_id` | texte | `DEV…` | Terminal de l'agent | E |
| `is_compromised` | entier | 0 / 1 | Agent compromis (vérité terrain) | H |

### 1.4 `merchants.csv`

| Colonne | Type | Domaine | Description | Rôle |
|---|---|---|---|---|
| `merchant_id` | texte | `M` + 7 chiffres | Identifiant du marchand | ID |
| `channel` | catégorie | `MOBILE_MONEY`, `VISA_VIRTUAL` | Canal du marchand | E |
| `category` | catégorie | voir §4 | Catégorie | E |
| `country` | texte | ISO-2 | Pays | E |
| `province` | catégorie | provinces, vide si étranger | Province | E |
| `risk_level` | catégorie | `low`, `medium`, `high` | Niveau de risque de la catégorie | E |
| `typical_amount_usd` | décimal | > 0, vide en Mobile Money | Prix typique (achats carte) | H |

---

## 2. Variables dérivées (entrées du modèle)

Calculées pour chaque opération **à partir du seul passé** du client, puis standardisées (`(x − moyenne) / écart-type`,
écrêtées à ±10). Notation : *a* montant USD, *B* solde avant, *n* nombre d'opérations passées du client.

### 2.1 Montant (7)

| Variable | Type | Description |
|---|---|---|
| `log_amount_usd` | réel | ln(1 + *a*) |
| `amount_zscore_user` | réel [−10 ; 10] | Écart du montant à l'habitude du client (z-score sur les logarithmes, si *n* ≥ 3) |
| `amount_ratio_user_mean` | réel | ln(1 + *a* / montant moyen du client) |
| `amount_to_balance` | réel [0 ; 5] | Part du solde débitée : min(*a* / (*B* + 1), 5) ; 0 pour un crédit |
| `is_near_full_drain` | 0 / 1 | Débit d'au moins 85 % du solde |
| `amount_to_kyc_limit` | réel | Montant / plafond KYC |
| `log_balance_before` | réel | ln(1 + *B*) |

### 2.2 Fréquence / vélocité (7)

| Variable | Type | Description |
|---|---|---|
| `tx_count_1h` | entier | Opérations du client dans l'heure précédente |
| `tx_count_24h` | entier | Opérations dans les 24 h |
| `tx_count_7d` | entier | Opérations dans les 7 jours |
| `debit_count_1h` | entier | Débits dans l'heure |
| `log_debit_sum_24h` | réel | ln(1 + total débité sur 24 h) |
| `log_secs_since_last_tx` | réel | ln(1 + secondes depuis la dernière opération) |
| `failed_count_24h` | entier | Échecs sur 24 h |

### 2.3 Appareil (8)

| Variable | Type | Description |
|---|---|---|
| `is_new_device` | 0 / 1 | Appareil jamais utilisé par ce client |
| `log_device_prior_uses` | réel | ln(1 + utilisations passées de cet appareil par le client) |
| `n_devices_user` | entier | Nombre d'appareils distincts du client |
| `device_n_users` | entier [0 ; 20] | Autres clients ayant utilisé cet appareil |
| `is_smartphone` | 0 / 1 | Appareil smartphone |
| `access_app` / `access_ussd` / `access_agent` | 0 / 1 | Moyen d'accès (codage disjonctif) |

### 2.4 Localisation (3)

| Variable | Type | Description |
|---|---|---|
| `is_foreign_ip` | 0 / 1 | Adresse IP hors RDC |
| `is_new_province` | 0 / 1 | Province jamais vue pour ce client |
| `is_away_from_home` | 0 / 1 | Opération hors de la province de résidence |

### 2.5 Contrepartie, agent, marchand (7)

| Variable | Type | Description |
|---|---|---|
| `is_new_counterparty` | 0 / 1 | Destinataire jamais vu |
| `counterparty_n_users` | réel | ln(1 + autres clients liés à ce destinataire) — indice de compte mule |
| `is_new_agent` | 0 / 1 | Agent jamais utilisé par ce client |
| `agent_n_users_24h` | réel | ln(1 + clients servis par l'agent en 24 h) |
| `is_new_merchant` | 0 / 1 | Marchand jamais vu |
| `is_high_risk_merchant` | 0 / 1 | Catégorie à risque (électronique, cartes cadeaux, cryptomonnaies, jeux) |
| `is_foreign_merchant` | 0 / 1 | Marchand étranger |

### 2.6 Temporelles (10)

| Variable | Type | Description |
|---|---|---|
| `hour_sin`, `hour_cos` | réel [−1 ; 1] | Heure cyclique sin(2π*h*/24), cos(2π*h*/24) |
| `is_night` | 0 / 1 | Entre 0 h et 5 h |
| `user_night_ratio` | réel [0 ; 1] | Part lissée des opérations nocturnes du client |
| `night_unusual` | réel [0 ; 1] | Nuit × (1 − habitude nocturne) |
| `hour_deviation_user` | réel [0 ; 1] | Écart à l'heure habituelle (statistique circulaire) |
| `is_weekend` | 0 / 1 | Samedi ou dimanche |
| `is_month_end` | 0 / 1 | Du 25 au 3 (période de paie) |
| `log_history_days` | réel | ln(1 + jours d'historique du client) |
| `log_user_tx_count` | réel | ln(1 + *n*) |

### 2.7 Trans-canal (3)

| Variable | Type | Description |
|---|---|---|
| `is_card` | 0 / 1 | Opération sur carte Visa virtuelle |
| `log_mins_since_topup` | réel | ln(1 + minutes depuis la dernière recharge de carte), pour un achat carte |
| `purchase_to_topup_ratio` | réel [0 ; 5] | Achat / dernière recharge |

### 2.8 Profil KYC (4)

| Variable | Type | Description |
|---|---|---|
| `kyc_level` | entier | Niveau KYC |
| `log_account_age_days` | réel | ln(1 + ancienneté du compte en jours à la date de l'opération) |
| `log_monthly_income` | réel | ln(1 + revenu mensuel déclaré) |
| `has_visa_virtual` | 0 / 1 | Détient une carte virtuelle |

### 2.9 Type d'opération (9)

`type_P2P_SEND`, `type_P2P_RECEIVE`, `type_CASH_IN`, `type_CASH_OUT`, `type_MERCHANT_PAYMENT`, `type_AIRTIME`,
`type_BILL_PAYMENT`, `type_CARD_TOPUP`, `type_CARD_PURCHASE` : codage disjonctif (0 / 1) du type d'opération.

**Familles utilisées pour H2** : temporelles = 2.6 ; fréquentielles = 2.2 ; contextuelles = 2.3 + 2.4 + 2.5.

### 2.10 Variables physiques (hors entrée du modèle de données)

| Variable | Type | Description |
|---|---|---|
| `phys_travel_km` | réel | Distance (km) entre la province actuelle et la précédente |
| `phys_travel_required_kmh` | réel | Vitesse qu'il aurait fallu pour ce déplacement |
| `phys_travel_infeasibility` | réel ≥ 0 | max(0, durée minimale / temps écoulé − 1) ; 0 = déplacement possible |
| `phys_overdraft` | réel [0 ; 1] | Part du montant dépassant le solde |
| `phys_time_to_empty_h` | réel | Heures avant vidage du compte au débit de la dernière heure |
| `phys_score` | réel [0 ; 1] | Score de violation des lois physiques |

---

## 3. Base opérationnelle

### 3.1 `scored_transactions` — chaque décision (hypertable TimescaleDB sur `tx_time`)

| Colonne | Type | Description |
|---|---|---|
| `transaction_id`, `tx_time` | texte, date-heure | Clé primaire composée |
| `scored_at` | date-heure (UTC) | Heure de la décision |
| `user_id`, `channel`, `operator`, `tx_type`, `access_channel` | texte | Reprise de l'opération |
| `amount`, `currency`, `amount_usd` | décimal, texte, décimal | Montant |
| `province`, `device_id`, `counterparty_id`, `agent_id`, `merchant_id` | texte | Contexte |
| `fraud_probability` | réel [0 ; 1] | Probabilité de fraude |
| `risk_level` | texte | `FAIBLE`, `MOYEN`, `ELEVE`, `CRITIQUE` |
| `action` | texte | `APPROVE`, `VERIFY`, `BLOCK` |
| `reason` | texte | Motif de la décision |
| `rules_triggered` | JSON | Règles métier ou physiques déclenchées |
| `fraud_type`, `fraud_type_probability` | texte, réel | Typologie probable (si signalée) |
| `model_version` | texte | Version du modèle |
| `latency_ms`, `degraded` | réel, booléen | Latence ; mode dégradé (branche indisponible) |
| `explanation` | JSON | SHAP, contributions des branches, attention, typologies candidates, analyse de texte, lois physiques |
| `features` | JSON | Les 58 variables calculées |
| `label`, `labeled_at` | entier, date-heure | Étiquette posée par un analyste ou une plainte (1 fraude, 0 légitime) |

### 3.2 `cases` — dossiers d'alerte

| Colonne | Type | Description |
|---|---|---|
| `id` | entier | Identifiant |
| `transaction_id`, `tx_time`, `user_id`, `channel`, `tx_type`, `amount_usd` | — | Opération concernée |
| `fraud_probability`, `risk_level`, `action`, `fraud_type` | — | Décision et typologie |
| `status` | texte | `OUVERT`, `EN_COURS`, `FRAUDE_CONFIRMEE`, `FAUX_POSITIF` |
| `assigned_to`, `resolved_by` | entier | Analyste affecté, analyste qui a clos |
| `resolution_note`, `resolved_at` | texte, date-heure | Justification et date de clôture |
| `created_at`, `updated_at` | date-heure | Horodatage |

### 3.3 Autres tables

| Table | Contenu |
|---|---|
| `notifications` | SMS, e-mails et webhooks envoyés : `case_id`, `channel`, `recipient`, `status`, `detail`, `created_at` |
| `audit_log` | Journal inaltérable : `ts`, `actor`, `action`, `entity`, `entity_id`, `details` (JSON), `prev_hash`, `hash` (SHA-256 chaîné) |
| `bo_users` | Utilisateurs : `email`, `full_name`, `role` (`ANALYSTE`, `SUPERVISEUR`, `ADMIN`), `password_hash`, `is_active` |
| `model_registry` | Versions de modèle : `version`, `status` (`CHAMPION`, `CHALLENGER`, `ARCHIVE`, `REJETE`), `metrics`, `trained_on` |
| `retrain_events` | Journal du réentraînement : `trigger` (`AUTO`, `MANUEL`), `reasons`, `status`, `detail`, `requested_by`, `handled_at` |
| `retrain_state` | Dernier relevé des signaux (dérive, nouveauté, étiquettes) |

---

## 4. Valeurs possibles (énumérations)

| Champ | Valeurs |
|---|---|
| `tx_type` | `P2P_SEND` (envoi), `P2P_RECEIVE` (réception), `CASH_IN` (dépôt chez un agent), `CASH_OUT` (retrait chez un agent), `MERCHANT_PAYMENT` (paiement marchand), `AIRTIME` (crédit téléphonique), `BILL_PAYMENT` (facture), `CARD_TOPUP` (recharge de la carte depuis le portefeuille), `CARD_PURCHASE` (achat par carte) |
| `fraud_type` — Mobile Money | `SIM_SWAP` (échange de SIM), `SOCIAL_ENGINEERING` (ingénierie sociale), `ACCOUNT_TAKEOVER` (prise de contrôle de compte), `AGENT_FRAUD` (fraude d'agent), `SMURFING` (fractionnement, comptes mules) |
| `fraud_type` — Visa virtuelle | `CARD_TESTING` (test de carte), `CNP_FRAUD` (carte non présente), `TOPUP_DRAIN` (vidage par rechargement, trans-canal) |
| `location_province` (jeu simulé) | Kinshasa, Haut-Katanga, Nord-Kivu, Sud-Kivu, Kongo-Central, Kasai-Oriental, Lualaba, Tshopo, Ituri |
| Catégories marchand Mobile Money | `SUPERMARCHE`, `PHARMACIE`, `RESTAURANT`, `CARBURANT`, `BOUTIQUE`, `TELECOM`, `ECOLE`, `UTILITES` |
| Catégories marchand carte | `ECOMMERCE_INTL`, `LOCAL_ONLINE`, `STREAMING`, `SOFTWARE`, `GAMING`, `EDUCATION`, `ELECTRONICS`, `TRAVEL`, `GIFT_CARDS`, `CRYPTO_EXCHANGE` |
| `action` | `APPROVE` (laisser passer), `VERIFY` (faire confirmer par le client), `BLOCK` (refuser) |
| `risk_level` | `FAIBLE`, `MOYEN`, `ELEVE`, `CRITIQUE` |

---

## 5. Règles de qualité et d'intégrité

| Règle | Contrôle |
|---|---|
| Unicité | `transaction_id` unique ; une opération reçue deux fois n'est traitée qu'une fois (idempotence) |
| Chronologie | Transactions triées par date ; aucune opération avant l'ouverture du compte ; aucune opération carte avant le lancement de la carte |
| Cohérence des soldes | `balance_after = balance_before − montant` (débit réussi) ; échec si le montant dépasse le solde |
| Cohérence monétaire | `amount_usd = amount / taux(année)` pour le CDF |
| Cohérence physique | Aucun déplacement légitime plus rapide que la durée minimale de trajet |
| Absence de fuite | Variables calculées sur le passé seulement ; colonnes « H » jamais utilisées en entrée |
| Valeurs manquantes | Champs facultatifs vides selon le type d'opération (ex. `merchant_id` vide pour un transfert) ; aucune valeur manquante dans les 58 variables |
