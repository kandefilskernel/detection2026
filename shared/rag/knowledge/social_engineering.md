---
type: SOCIAL_ENGINEERING
titre: Ingénierie sociale
---
## Définition
Le client est manipulé (faux agent de l'opérateur, faux gain, urgence) pour effectuer lui-même les opérations depuis son propre téléphone. Aucun appareil nouveau n'apparaît : la fraude se voit surtout à l'écart de comportement. C'est la typologie la plus difficile à détecter parce que l'opération est authentique du point de vue technique.

## Signaux observables
- Montant ou fréquence inhabituels pour ce client [amount_zscore_user] [amount_ratio_user_mean] [tx_count_24h].
- Envoi vers un destinataire nouveau, parfois lié à plusieurs autres clients [is_new_counterparty] [counterparty_n_users].
- Opérations enchaînées à intervalles courts [log_secs_since_last_tx] [tx_count_1h].
- Opérations qui échouent puis sont retentées [failed_count_24h].
- Pas de nouvel appareil : l'absence de signal technique ne rassure pas.

## Vérifications recommandées
- Appeler le client et lui demander si une personne l'a contacté pour lui demander d'envoyer de l'argent ; ne jamais lui demander son PIN.
- Proposer une confirmation par PIN USSD avant de libérer l'opération (VERIFY) lorsque le montant est inhabituel.
- Examiner le destinataire : plusieurs clients lui ont-ils envoyé de l'argent récemment ?
- Si la fraude est confirmée, bloquer le destinataire et signaler les comptes liés.
