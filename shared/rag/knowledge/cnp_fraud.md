---
type: CNP_FRAUD
titre: Fraude carte non présente (CNP)
---
## Définition
Achat en ligne réalisé avec les données de la carte, sans la carte, par une personne autre que le titulaire. Pour une carte virtuelle, il s'agit généralement de données volées ou interceptées.

## Signaux observables
- Marchand à risque ou étranger [is_high_risk_merchant] [is_foreign_merchant] [is_new_merchant].
- Connexion depuis l'étranger [is_foreign_ip] et appareil inconnu [is_new_device].
- Montant élevé pour ce porteur [amount_zscore_user] [amount_ratio_user_mean] [amount_to_balance].
- Horaires inhabituels [is_night] [night_unusual].

## Vérifications recommandées
- Demander une authentification forte (3-D Secure) avant de libérer l'opération.
- Contacter le titulaire pour confirmer l'achat.
- Bloquer la carte virtuelle si l'achat n'est pas reconnu et en émettre une nouvelle.
- Relever le marchand pour le suivi de cas similaires.
