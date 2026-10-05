---
type: CARD_TESTING
titre: Test de carte (card testing)
---
## Définition
Le fraudeur teste les données d'une carte Visa virtuelle volée avec une série de très petits achats, souvent chez des marchands différents, avant un achat plus important.

## Signaux observables
- Salve d'achats de petits montants en peu de temps [tx_count_1h] [log_secs_since_last_tx] [log_amount_usd].
- Nouveaux marchands successifs [is_new_merchant] [is_foreign_merchant].
- Échecs répétés [failed_count_24h].
- Connexion depuis un pays étranger [is_foreign_ip].
- Appareil inconnu [is_new_device] [log_device_prior_uses].

## Vérifications recommandées
- Bloquer la carte virtuelle et en émettre une nouvelle (opération peu coûteuse pour une carte virtuelle).
- Vérifier les achats ultérieurs d'un montant plus élevé chez des marchands à risque [is_high_risk_merchant].
- Informer le client et vérifier l'origine d'une possible fuite des données de carte.
