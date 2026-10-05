---
type: SMURFING
titre: Fractionnement (smurfing) et comptes mules
---
## Définition
De nombreux petits montants transitent par des comptes mules pour rester sous les seuils de vigilance puis être regroupés et retirés. Le motif est collectif : plusieurs clients et un même destinataire ou appareil.

## Signaux observables
- Destinataire lié à de nombreux autres clients [counterparty_n_users] [is_new_counterparty].
- Série de petites opérations rapprochées [tx_count_1h] [tx_count_24h] [debit_count_1h].
- Appareil partagé entre plusieurs comptes [device_n_users].
- Montants proches mais sous les plafonds KYC [amount_to_kyc_limit].
- Compte récent ou peu ancien qui reçoit puis retire [log_account_age_days] [kyc_level].

## Vérifications recommandées
- Cartographier les comptes reliés au destinataire et à l'appareil.
- Examiner le niveau KYC du compte receveur et l'ancienneté du compte.
- Limiter temporairement les retraits du compte receveur et demander une mise à jour d'identité.
- Rapprocher les opérations de la période pour estimer le montant total fractionné.
