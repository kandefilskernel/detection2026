---
type: TOPUP_DRAIN
titre: Vidage par rechargement de carte
---
## Définition
Fraude trans-canal : le fraudeur recharge la carte Visa virtuelle depuis le portefeuille Mobile Money de la victime, puis dépense le solde de la carte en achats. La recharge est le premier maillon : l'arrêter empêche la suite.

## Signaux observables
- Recharge de carte importante par rapport au solde du portefeuille [amount_to_balance] [is_near_full_drain] [type_CARD_TOPUP].
- Achats rapides après la recharge [log_mins_since_topup] [purchase_to_topup_ratio].
- Appareil ou connexion inhabituels [is_new_device] [is_foreign_ip].
- Montant inhabituel pour ce client [amount_zscore_user].

## Vérifications recommandées
- Bloquer la recharge dès qu'elle est signalée : les achats suivants deviennent impossibles.
- Contacter le client sur un canal connu pour confirmer la recharge.
- Vérifier si le portefeuille Mobile Money a été compromis (SIM swap, prise de contrôle).
