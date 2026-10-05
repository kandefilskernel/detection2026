"""
Lexiques de l'analyse de messages. Les motifs s'appliquent au texte NORMALISÉ :
minuscules, sans accents, apostrophes droites (ex. « vous avez gagné » -> « vous avez gagne »).

SE_CUES : catégorie -> (libellé affiché, poids, motifs). Le poids est la confiance qu'un message
contenant ce motif relève de l'ingénierie sociale ; il est volontairement faible pour les indices
banals (urgence) et élevé pour les indices spécifiques (demande de code PIN).
"""

SE_CUES = {
    "DEMANDE_CODE": ("Demande de PIN / code secret", 0.80, [
        r"\b(envoy\w*|donn\w*|communiqu\w*|dit\w*|dites|partag\w*|confirm\w*|fourni\w*|transmet\w*)\b.{0,30}\b(pin|otp|code secret|mot de passe|code de (verification|confirmation|securite)|code recu)\b",
        r"\b(votre|ton|ta) (code pin|pin|code secret|mot de passe)\b.{0,30}\b(svp|s'il vous plait|pour|afin|maintenant|urgent)\b",
        r"\bcode (pin|otp)\b.{0,15}\b(svp|s'il vous plait|maintenant)\b",
    ]),
    "AUTORITE": ("Se fait passer pour l'opérateur / la banque", 0.55, [
        r"\b(je suis|ici|c'est)\b.{0,25}\b(du |de la |de l')?(service client|conseiller|agent (vodacom|airtel|orange|m-?pesa)|support|administrateur|direction|responsable|police|banque|vodacom|airtel|orange money|m-?pesa)\b",
        r"\b(message|appel|notification) (officiel )?(de|du|d')\s?(vodacom|airtel|orange|m-?pesa|la banque|la direction)\b",
        r"\b(equipe|service) (securite|fraude|verification)\b",
    ]),
    "GAIN": ("Faux gain / loterie / héritage", 0.70, [
        r"\bvous avez gagne\b",
        r"\bfelicitations\b.{0,40}\b(gagn\w*|lot|prix|selectionne\w*|tirage)\b",
        r"\b(loterie|tirage au sort|heritage|legs)\b",
        r"\bvous etes (le|la|l')?\s?(gagnant\w*|selectionne\w*|elu\w*)\b",
    ]),
    "MENACE": ("Menace de blocage / de poursuites", 0.60, [
        r"\b(votre|ton|ta) (compte|carte|solde|numero)\b.{0,25}\b(sera|va etre|a ete|est|allons)\b.{0,15}\b(bloque|suspendu|ferme|desactive|supprime|gele)\w*",
        r"\b(poursuites?|arrestation|plainte contre vous|amende)\b",
        r"\bsans (action|reponse) de votre part\b",
    ]),
    "SECRET": ("Demande de garder le secret", 0.60, [
        r"\bne (le )?dites?\b.{0,15}\b(rien|a personne)\b",
        r"\bn'en parlez (a personne|pas)\b",
        r"\b(gardez|garde) (ca|cela|le) (secret|confidentiel)\b",
        r"\bstrictement confidentiel\b",
    ]),
    "FRAIS_AVANCE": ("Frais à payer pour débloquer un gain", 0.70, [
        r"\bfrais (de )?(dossier|deblocage|livraison|reception|transfert|douane|traitement)\b.{0,40}\b(payer|envoy\w*|verser|regler|deposer)\b",
        r"\b(payer|envoyer|verser|regler|deposer)\b.{0,30}\bfrais (de )?(dossier|deblocage|livraison|reception|douane|traitement)\b",
        r"\b(payez|payer|envoyez|versez|reglez)\b.{0,25}\bfrais\b.{0,30}\d",
        r"\bpour (debloquer|recevoir|retirer) (votre|le|l')\b.{0,25}\b(gain|lot|colis|argent|prix|heritage)\b",
    ]),
    "ERREUR_ENVOI": ("Faux « envoi par erreur » (arnaque au remboursement)", 0.60, [
        r"\b(envoye|transfere|depose)\b.{0,25}\bpar erreur\b",
        r"\bpar erreur\b.{0,40}\b(renvoy\w*|rembours\w*|retourn\w*|rendez)\b",
        r"\b(renvoyez|remboursez|retournez)[- ]?(moi|le)\b.{0,25}\b(argent|montant|somme|\d)",
    ]),
    "PROCHE_DETRESSE": ("Faux proche en détresse demandant de l'argent", 0.50, [
        r"\b(accident|hopital|arrete|en prison|garde a vue|kidnap\w*|enleve\w*)\b.{0,60}\b(envoy\w*|transf\w*|argent|payer|verser)\b",
        r"\b(envoy\w*|transf\w*)\b.{0,40}\b(urgence|urgent)\b.{0,40}\b(accident|hopital|police|arrete)\b",
        r"\b(c'est|ici) (maman|papa|ton frere|ta soeur|ton fils|ta fille|ton cousin)\b.{0,40}\b(nouveau numero|numero)\b",
    ]),
    "URGENCE": ("Pression d'urgence", 0.35, [
        r"\burgent\w*\b",
        r"\b(immediatement|tout de suite|sans attendre|dans l'heure)\b",
        r"\bdans les \d+ ?(minutes?|min|heures?|h)\b",
        r"\b(vite|rapidement)\b.{0,25}\b(envoy\w*|repondre|confirmer|payer)\b",
        r"\bderniere chance\b|\bdernier avertissement\b",
    ]),
    "LIEN": ("Lien à ouvrir", 0.40, [
        r"https?://\S+",
        r"\b(bit\.ly|tinyurl|wa\.me|t\.me)\S*",
        r"\bcliquez (ici|sur)\b",
    ]),
    "DEMANDE_TRANSFERT": ("Demande d'envoyer de l'argent", 0.30, [
        r"\b(envoyez|transferez|deposez|virez|faites un (depot|transfert|envoi))\b.{0,40}(\d|usd|cdf|dollars|francs)",
    ]),
}

# Émotions (utiles pour les plaintes : un client en détresse ou apeuré est à traiter en priorité).
EMOTIONS = {
    "PEUR": [r"\b(peur|inquiet\w*|angoiss\w*|panique\w*|stress\w*|effray\w*|terrifi\w*)\b"],
    "COLERE": [r"\b(scandale|inadmissible|honte|honteux|voleurs?|arnaqueurs?|escrocs?|furieu\w*|en colere|ras-le-bol)\b"],
    "DETRESSE": [r"\b(au secours|desespere\w*|j'ai tout perdu|plus rien|je suis ruine\w*|aidez[- ]moi|a l'aide)\b"],
    "CONFUSION": [r"\b(je ne comprends pas|je comprends pas|comment (ca|cela) se fait|aucune idee)\b"],
}

NEGATIVE = [
    r"\b(arnaque\w*|escroquerie|fraude\w*|vol|vole\w*|probleme\w*|perdu\w*|perte|erreur|mecontent\w*|decu\w*)\b",
    r"\b(inadmissible|scandale|honte|nul|mauvais|horrible|catastrophe|terrible|inquiet\w*|peur|panique\w*)\b",
    r"\b(bloque\w*|refuse\w*|echec|echoue\w*|impossible|retire sans|sans mon accord|non autorise\w*|pas autorise\w*)\b",
    r"\b(desespere\w*|furieu\w*|en colere|triste|stress\w*|angoiss\w*|au secours)\b",
]
POSITIVE = [
    r"\b(merci|content\w*|satisfait\w*|ravi\w*|parfait\w*|excellent\w*|super|genial|bravo|heureu\w*)\b",
    r"\b(bien recu|bonne (nouvelle|journee|fete)|felicitations a|joyeux|bon anniversaire)\b",
    r"\b(rapide|efficace|resolu\w*|regle\w*)\b",
]
NEGATION = r"\b(ne|n'|pas|jamais|aucun\w*|sans)\b"
