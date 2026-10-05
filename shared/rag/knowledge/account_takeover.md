---
type: ACCOUNT_TAKEOVER
titre: Prise de contrôle de compte
---
## Définition
Un tiers accède à l'application du client (identifiants volés ou devinés) depuis son propre appareil et déplace l'argent. Dans les données simulées, ces fraudes passent par l'application sur un smartphone différent de celui du client.

## Signaux observables
- Appareil inconnu qui accède à l'application [is_new_device] [log_device_prior_uses] [is_smartphone] [access_app].
- Connexion depuis une autre province ou un autre pays [is_new_province] [is_away_from_home] [is_foreign_ip].
- Opérations à des heures atypiques pour le client [night_unusual] [hour_deviation_user].
- Vidage rapide du solde [amount_to_balance] [is_near_full_drain].
- Plusieurs appareils associés au même compte en peu de temps [n_devices_user].

## Vérifications recommandées
- Forcer la réinitialisation du PIN et la déconnexion de toutes les sessions.
- Joindre le client par un canal déjà connu et confirmer qu'il utilise bien ce nouvel appareil.
- Vérifier si cet appareil a servi sur d'autres comptes [device_n_users].
- Suspendre les envois sortants jusqu'à confirmation.
