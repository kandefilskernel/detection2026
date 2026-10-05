---
type: SIM_SWAP
titre: Échange de SIM (SIM swap)
---
## Définition
Le fraudeur obtient une nouvelle carte SIM pour le numéro de la victime (ou détourne la ligne), reçoit les SMS et codes de confirmation, puis vide le portefeuille depuis un autre téléphone. Dans les données simulées, l'épisode commence par l'apparition d'un nouvel appareil sur un compte ancien et se poursuit par des opérations rapides vers de nouveaux destinataires ou des retraits.

## Signaux observables
- Nouvel appareil jamais utilisé par ce client [is_new_device] [log_device_prior_uses] [n_devices_user].
- Montant élevé par rapport à l'habitude du client [amount_zscore_user] [amount_ratio_user_mean] et vidage d'une grande part du solde [amount_to_balance] [is_near_full_drain].
- Rafale d'opérations en peu de temps [tx_count_1h] [debit_count_1h] [log_secs_since_last_tx].
- Nouveau destinataire ou nouvel agent [is_new_counterparty] [is_new_agent].
- Heure inhabituelle pour ce client, souvent la nuit [night_unusual] [hour_deviation_user].

## Vérifications recommandées
- Contacter le client sur un canal déjà connu (pas sur le numéro qui vient d'agir) pour confirmer l'opération.
- Demander à l'opérateur télécom si un remplacement de SIM a eu lieu récemment sur cette ligne.
- Geler les retraits et les envois vers de nouveaux destinataires tant que l'identité n'est pas confirmée.
- Rechercher d'autres comptes ayant utilisé le même appareil [device_n_users].
