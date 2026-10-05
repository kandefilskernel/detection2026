---
type: GENERAL
titre: Politique de décision et lecture des preuves
---
## Actions du système
APPROVE laisse passer l'opération. VERIFY demande une confirmation (PIN USSD, OTP ou appel) avant de libérer l'opération. BLOCK refuse l'opération. L'action est choisie pour minimiser la perte attendue selon la probabilité de fraude et le montant.

## Lecture des preuves
Les cas similaires sont des opérations passées dont le verdict est connu (jeu d'historique ou verdict d'un analyste). Si les cas les plus proches sont majoritairement frauduleux, la décision du modèle est confortée ; s'ils sont majoritairement légitimes, examiner l'opération manuellement avant de confirmer la fraude. Un faible nombre de cas proches ou une grande distance indiquent une opération inhabituelle : ne pas se fier à la comparaison.

## Principes de traitement d'un dossier
- Ne jamais demander le PIN du client et ne communiquer aucun code.
- Documenter le verdict : la note est conservée et sert à ré-entraîner le modèle.
- Un faux positif confirmé améliore le modèle : le clore avec une note précise.
