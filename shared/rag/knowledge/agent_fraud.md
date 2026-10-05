---
type: AGENT_FRAUD
titre: Fraude d'agent
---
## Définition
Un agent de proximité compromis effectue des retraits non autorisés sur le compte de clients. Dans les données simulées, les retraits passent par un agent marqué comme compromis, avec peu d'indices côté client.

## Signaux observables
- Retraits chez un agent que le client n'a jamais utilisé [is_new_agent] [access_agent].
- Agent qui sert un nombre inhabituel de clients en peu de temps [agent_n_users_24h].
- Retrait d'une part importante du solde [amount_to_balance] [is_near_full_drain].
- Localisation de l'agent différente de celle du client [is_new_province] [is_away_from_home].
- Pas de nouvel appareil client : l'appareil est celui de l'agent.

## Vérifications recommandées
- Contrôler l'historique de l'agent : nombre de clients et volume de retraits sur 24 h.
- Contacter le client pour confirmer qu'il s'est bien rendu chez cet agent.
- Suspendre l'agent pour de nouveaux retraits le temps de l'enquête si plusieurs clients contestent.
- Rapprocher les retraits des plaintes clients de la période.
