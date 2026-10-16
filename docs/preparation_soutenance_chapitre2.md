# Préparation à la soutenance — Chapitre II

**Comprendre, expliquer et défendre chaque concept, formule et modèle**

Ce document reprend le chapitre II (analyse du métier, méthodologie, conception) dans l'ordre du mémoire. Pour chaque notion, il donne :

- **Ce que c'est**, en une ou deux phrases simples ;
- **La formule**, avec chaque symbole expliqué ;
- **Un exemple chiffré**, recalculé à partir des résultats du projet ;
- **Pourquoi ce choix** dans ce travail ;
- **La question probable du jury**, avec une réponse prête à dire.

Conseil : apprenez d'abord la partie 0 (le discours de deux minutes et les chiffres clés), puis la partie D (questions pièges). Le reste sert à répondre en profondeur quand le jury creuse un point.

---

## 0. L'essentiel à savoir par cœur

### 0.1 Le chapitre en deux minutes (à dire à l'oral)

> « Le chapitre II répond à trois questions. **Que faut-il résoudre ?** En RDC, la lutte contre la fraude Mobile Money repose sur des règles fixes : elles ignorent l'individu, se laissent contourner, interviennent après l'exécution et n'expliquent pas leurs décisions. **Comment le résoudre avec rigueur ?** Par une démarche de science de la conception : je construis un artefact, un système de détection, et je l'évalue sur cinq hypothèses. Faute de données publiques, j'ai construit un générateur qui simule le marché congolais de 2019 à 2025, et je décris chaque transaction par 58 variables qui mesurent l'écart au comportement habituel du client, calculées sans fuite d'information. J'ai comparé huit méthodes sur le même jeu de test, avec des tests statistiques. **Quel système construire ?** Le modèle hybride XGBoost + LSTM avec attention + autoencodeur est significativement le meilleur : PR-AUC 0,9955, 42 % de fausses alertes et 45 % de fraudes manquées en moins qu'XGBoost seul. Il est intégré dans une architecture temps réel en microservices, avec une décision graduée selon le coût, des explications, une API ouverte aux institutions et un réentraînement contrôlé. »

### 0.2 Les chiffres clés

| Élément | Valeur |
|---|---|
| Période simulée | 1ᵉʳ janvier 2019 → 31 décembre 2025 |
| Transactions | 631 968, dont 8 426 fraudes (1,33 %) |
| Clients, agents | 500 clients, 800 agents |
| Variables par transaction | 58 |
| Typologies de fraude | 8 (5 Mobile Money, 3 Visa virtuelle) |
| Jeu de test | 13/12/2024 → 31/12/2025 : 183 240 transactions, 2 437 fraudes |
| Modèle retenu | Hybride : XGBoost + LSTM-attention + autoencodeur, combinés par empilement |
| PR-AUC de l'hybride | 0,9955 (XGBoost seul : 0,9895) |
| Précision / rappel / F1 | 95,1 % / 97,8 % / 0,964 |
| Erreurs sur le test | 122 fausses alertes, 54 fraudes manquées (XGBoost : 210 et 99) |
| Gain sur XGBoost seul | −42 % de fausses alertes, −45 % de fraudes manquées |
| Ingénierie sociale (rappel) | 92,1 % (XGBoost : 85,9 %) |
| Seuil de décision $\tau^*$ | 0,538 (choisi sur la validation) |
| Latence de bout en bout | 59 ms en médiane, 104 ms au 95ᵉ centile |
| Matrice multicritère | Hybride 4,45 / 5 ; premier dans 91 % de 2 000 pondérations aléatoires |

---

## PARTIE A — ANALYSE DU MÉTIER (Section 1)

### A.1 Le domaine

**Mobile Money.** Portefeuille électronique sur le téléphone, géré par un opérateur de télécommunications (Vodacom M-Pesa, Airtel Money, Orange Money). Il permet d'envoyer, recevoir, déposer et retirer de l'argent, de payer un commerçant ou une facture, sans compte bancaire.

**USSD** (*Unstructured Supplementary Service Data*). Menu par codes (`*1222#`) utilisable sur un téléphone simple, sans Internet. Conséquence pour le système : on ne peut pas compter sur des signaux propres aux smartphones (géolocalisation GPS, empreinte de l'application). D'où des variables fondées sur le montant, la fréquence, l'agent et le destinataire, disponibles quel que soit le téléphone.

**Agent.** Commerçant de proximité qui convertit espèces et monnaie électronique (dépôt, retrait). Indispensable à l'inclusion financière, mais point de vulnérabilité : d'où la typologie « fraude d'agent ».

**Double monnaie CDF / USD.** Les opérations se font en francs congolais et en dollars. Le franc s'est déprécié (≈ 1 650 CDF/USD en 2019, plus de 2 700 en 2024). **Règle RG-02** : tout montant est converti en USD **au taux de l'année** de l'opération. Sinon, 100 000 CDF n'auraient pas la même valeur en 2019 et en 2025, et le modèle confondrait inflation et anomalie.

**KYC** (*Know Your Customer*). Niveaux d'identification du client imposés par la BCC, chacun avec un plafond par opération. Utilisé dans la variable « montant / plafond KYC » et la règle RG-08.

**BCC et ARPTC.** La Banque Centrale du Congo régule la monnaie électronique (Instruction n° 24 de 2011) et attend une traçabilité des décisions. L'ARPTC régule les télécommunications et publie l'observatoire du marché (sources utilisées pour confronter le générateur).

**Carte Visa virtuelle.** Carte prépayée sans support physique, rechargée depuis le portefeuille, pour les achats en ligne. Second canal, avec d'autres usages et d'autres fraudes : objet de l'hypothèse H4 (transposition).

> **Question probable :** « Pourquoi parler d'USSD dans un mémoire d'IA ? »
> **Réponse :** « Parce que c'est une contrainte de conception. Une grande partie des clients n'ont pas de smartphone : les signaux techniques du téléphone n'existent pas pour eux. J'ai donc choisi des variables comportementales disponibles pour tous : montant, fréquence, agent, destinataire, horaires. »

### A.2 Les huit typologies de fraude

| Typologie | Comment l'expliquer en une phrase | Signal attendu |
|---|---|---|
| Échange de SIM | Le fraudeur obtient un duplicata de la SIM et vide le compte depuis un autre téléphone | nouvel appareil + vidage du solde |
| Ingénierie sociale | La victime est manipulée et envoie elle-même l'argent | nouveau destinataire, montant inhabituel, message suspect |
| Prise de contrôle de compte | Quelqu'un accède à l'application avec le code volé | nouvel appareil, heure inhabituelle, rafale |
| Fraude d'agent | Un agent compromis fait des retraits non autorisés | nouvel agent, retraits répétés |
| Fractionnement (*smurfing*) | Petits montants répétés vers des comptes mules pour rester sous les seuils | forte fréquence, destinataire lié à beaucoup de clients |
| Test de carte | Salves de petits achats pour vérifier qu'une carte volée fonctionne | rafale de petits montants |
| Carte non présente (CNP) | Achat en ligne avec les données de la carte | pays ou commerçant inhabituel, IP étrangère |
| Vidage par rechargement | Recharge de la carte puis vidage rapide | recharge suivie d'achats rapprochés |

**Compte mule.** Compte (souvent loué ou volé) qui reçoit l'argent frauduleux avant qu'il soit retiré. Il se repère parce qu'il reçoit de nombreux clients sans lien entre eux.

> **Question probable :** « Quelle est la fraude la plus difficile ? »
> **Réponse :** « L'ingénierie sociale : c'est la vraie cliente qui paie, depuis son propre téléphone, à son heure habituelle. Seuls le destinataire nouveau, le montant inhabituel et le message trahissent la fraude. C'est là que le modèle hybride apporte le plus : 92,1 % de rappel contre 85,9 % pour XGBoost seul. »

### A.3 Étude et critique de l'existant

**Diagramme de contexte.** Il fixe la **frontière** du système : il ne gère pas les portefeuilles et n'exécute pas les opérations ; il **décide** (accepter, vérifier, refuser) et **outille** l'équipe anti-fraude.

**Processus actuel** : vérification du PIN et du solde, règles fixes (plafond, liste noire), exécution immédiate, plainte du client souvent plusieurs heures après, enquête manuelle.

**Les sept insuffisances**, à savoir citer dans l'ordre :

1. les règles ignorent l'individu (300 USD : banal pour un commerçant, anormal pour un étudiant) ;
2. les règles sont figées : les fraudeurs apprennent les seuils ;
3. la détection est tardive (après exécution, fonds perdus) ;
4. la réponse n'est pas graduée (2 USD et 900 USD traités pareil) ;
5. les décisions ne sont pas expliquées ;
6. les plaintes ne nourrissent pas le dispositif ;
7. le marché est cloisonné entre opérateurs.

**Solution qui en découle** : le **profilage comportemental**. On apprend l'habitude de chaque client et on juge chaque opération par rapport à elle, **avant** l'exécution.

### A.4 Problématique, hypothèses, objectifs

**Problématique** : comment concevoir un modèle d'IA qui apprend le comportement habituel de chaque utilisateur pour détecter en temps réel, de façon explicable, les fraudes Mobile Money en RDC, et dans quelle mesure cette approche se transpose-t-elle aux cartes virtuelles ?

| Hypothèse | Ce qu'elle affirme | Comment on la teste |
|---|---|---|
| **H1** | Le profilage comportemental bat les règles et un modèle sans historique | Même algorithme avec et sans variables d'historique ; règles métier |
| **H2** | Les variables temporelles, fréquentielles et contextuelles contribuent significativement | Ablation (on retire une famille), ajout (socle + une famille) |
| **H3** | La performance dépend de la famille de modèles | Comparaison de 8 méthodes sur le même test |
| **H4** | Un modèle appris sur le Mobile Money reste bon sur la carte Visa | Entraînement Mobile Money seul, évaluation Visa ; variantes 5 % et 20 % de Visa |
| **H5** | Un modèle mis à jour reste meilleur qu'un modèle figé | Modèle figé 2019-2021 contre modèle réentraîné, évalués chaque année 2022-2025 |

**Hypothèse de recherche** : affirmation testable, formulée avant l'expérience, qu'on confirme ou infirme avec un critère fixé à l'avance (Tableau II.20).

### A.5 Acteurs, règles de gestion, besoins

**Acteur** : entité **externe** au système qui interagit avec lui (humain ou système). Huit acteurs : client, opérateur, émetteur de cartes, banque partenaire, analyste, superviseur, administrateur, régulateur.

**Généralisation** (relation UML « hérite de ») : le superviseur hérite des droits de l'analyste ; l'émetteur Visa et la banque se comportent comme un opérateur.

**Règle de gestion** : contrainte du métier que le système doit respecter, indépendamment de la technique. Les plus importantes à savoir expliquer :

- **RG-01** : trois décisions, APPROVE (laisser passer), VERIFY (faire confirmer par le client), BLOCK (refuser) ;
- **RG-03, idempotence** : une opération envoyée deux fois avec le même identifiant reçoit la même décision. Si le réseau coupe et que l'opérateur renvoie, le client n'est pas débité ou bloqué deux fois ;
- **RG-04 et RG-05** : au-dessus de 0,97 on bloque, en dessous de 0,01 on accepte, entre les deux on choisit l'action de coût minimal ;
- **RG-06** : les règles métier et les lois physiques ne peuvent que **renforcer** la décision, jamais l'assouplir (défense en profondeur) ;
- **RG-16** : journal d'audit non modifiable ;
- **RG-17** : une institution ne voit que ses opérations ; le régulateur ne voit que des agrégats.

**Besoin fonctionnel (BM)** : ce que le système doit **faire** (détecter avant exécution, expliquer, prioriser…).
**Besoin non fonctionnel (BT)** : la **qualité** attendue (moins de 100 ms, disponibilité, sécurité, absence de fuite d'information…).

**MoSCoW** : méthode de priorisation. *Must* (indispensable), *Should* (important), *Could* (souhaitable), *Won't* (hors périmètre pour l'instant).

**Cas d'utilisation** : service rendu à un acteur. La **description textuelle** précise acteur, préconditions, scénario nominal, scénarios alternatifs, postconditions.

**Matrice de traçabilité** : relie chaque hypothèse aux besoins qui permettent de l'éprouver. Elle prouve que le système construit sert la question de recherche, et non l'inverse.

> **Question probable :** « Quelle différence entre un besoin fonctionnel et non fonctionnel ? »
> **Réponse :** « Le fonctionnel dit ce que fait le système : par exemple BM-06, expliquer chaque décision. Le non fonctionnel dit comment il doit le faire : par exemple BT-01, décider en moins de 100 ms. »

---

## PARTIE B — MÉTHODOLOGIE (Section 2)

### B.1 Démarche de recherche

**Science de la conception** (*Design Science Research*, Hevner et al., 2004). Démarche où le résultat de la recherche est un **artefact** (ici le système) construit pour résoudre un problème réel, puis évalué rigoureusement. Elle convient parce que mon travail ne se contente pas d'observer : il construit et il mesure.

**CRISP-DM** (*Cross Industry Standard Process for Data Mining*). Cycle standard des projets de données en six étapes : compréhension du métier → compréhension des données → préparation → modélisation → évaluation → déploiement. Il est itératif : on revient en arrière quand l'évaluation révèle un problème (par exemple une fuite d'information).

**Processus unifié et 2TUP** (*Two Track Unified Process*, « processus en Y »). Méthode itérative et incrémentale qui sépare une **branche fonctionnelle** (les besoins), une **branche technique** (les contraintes et l'architecture), puis les fusionne dans la **réalisation**. Le projet a été conduit en neuf incréments, chacun produisant une version utilisable.

**UML** (*Unified Modeling Language*). Langage graphique standard de modélisation. Diagrammes utilisés :

| Diagramme | À quoi il sert |
|---|---|
| Contexte | situer le système parmi ses interlocuteurs |
| Cas d'utilisation | les services rendus à chaque acteur |
| Activité | l'enchaînement des étapes d'un processus (existant et cible) |
| Packages | l'organisation du code en grands modules |
| Classes | la structure des données (tables, attributs, relations) |
| Séquence | les échanges de messages entre composants, dans l'ordre du temps |
| États-transitions | les états successifs d'un objet (un dossier d'alerte) |
| Composants, déploiement | les briques logicielles et les machines qui les hébergent |

> **Question probable :** « Pourquoi 2TUP et pas Scrum ? »
> **Réponse :** « 2TUP convient à un projet où les contraintes techniques (temps réel, sécurité, apprentissage automatique) pèsent autant que les besoins métier : il les traite dans une branche dédiée. Je l'ai appliqué de façon itérative, en neuf incréments, ce qui en garde l'esprit agile. »

### B.2 Les données simulées

**Pourquoi simuler ?** Les données des opérateurs sont confidentielles (secret bancaire, données personnelles) et aucun jeu public ne couvre la RDC.

**Précédent : PaySim** (Lopez-Rojas et al., 2016), simulateur Mobile Money reconnu. Différence : PaySim part d'un échantillon réel agrégé ; mon générateur repose entièrement sur des hypothèses paramétrées.

**Données primaires synthétiques** : produites par moi, pour ce travail, sans aucune donnée personnelle réelle.

**Graine aléatoire (42)** : nombre qui initialise le générateur de hasard. Même graine, mêmes données : la génération est **reproductible** à l'identique.

**Ce que le générateur reproduit** : rythmes individuels (heures, semaines, fins de mois, rentrée scolaire), cas légitimes difficiles (changement de téléphone, voyage, usage nocturne), trajets réalistes entre provinces, fraudes par épisodes qui débitent réellement le solde, et **évolution des fraudes dans le temps** (`FRAUD_TRENDS`).

**Confrontation aux sources officielles** : parts de marché des opérateurs (45/32/23 % contre 45/33/23 % à l'ARPTC), classement des provinces, taux de change (écart < 0,2 % de 2019 à 2022). Le **taux de fraude** (1,24 % en Mobile Money) reste une hypothèse invérifiable : aucune statistique publique n'existe.

> **Question probable :** « Vos résultats ne valent rien puisque les données sont fausses ? »
> **Réponse :** « Les données sont simulées, pas fausses : leur structure est confrontée aux statistiques officielles. Je n'affirme pas qu'on obtiendra 99,5 % en réalité : les vraies fraudes sont moins nettes. Ce que la simulation démontre, c'est la **méthode** et la **hiérarchie** entre approches, dans des conditions contrôlées et reproductibles. Je propose une démarche de validation sur données réelles en cinq étapes (§ II.2.11), avec un mode observation avant tout blocage. »

### B.3 Ingénierie des variables (58 variables)

**Principe du profilage comportemental** : une fraude se manifeste par une **rupture des habitudes**. Chaque variable mesure l'écart entre l'opération actuelle et le passé du client.

**Calcul sans fuite d'information** : chaque variable est calculée par un **rejeu chronologique**, à partir du seul passé du client. **Fuite d'information** (*data leakage*) : utiliser, pendant l'apprentissage, une information qui ne serait pas disponible au moment de la décision réelle. Le modèle paraît alors excellent en test et s'effondre en production.

**Mêmes fonctions en entraînement et en production** (BT-11) : sinon, le modèle reçoit en production des variables calculées différemment de celles qu'il a apprises (écart entraînement/production, *training-serving skew*).

#### a) Écart au montant habituel (z-score logarithmique)

$$\mu_u=\frac{1}{n_u}\sum_{i=1}^{n_u}\ln(1+a_i),\qquad z_{\text{montant}}=\operatorname{clip}\!\left(\frac{\ln(1+a_t)-\mu_u}{s_u},\,-10,\,10\right)$$

- $u$ : le client ; $a_t$ : montant (USD) de l'opération actuelle ; $a_i$ : ses montants passés ; $n_u$ : nombre d'opérations passées ;
- $\mu_u$ : moyenne des **logarithmes** des montants passés ; $s_u$ : leur écart-type, **plus 0,25** ;
- $\operatorname{clip}(x,-10,10)$ : on borne la valeur entre −10 et 10.

**Pourquoi le logarithme ?** Les montants sont très asymétriques (beaucoup de petits, quelques très gros). Le logarithme ramène une échelle multiplicative à une échelle additive : passer de 10 à 100 USD compte autant que de 100 à 1 000. **Pourquoi « 1 + a » ?** Pour que $\ln(1+0)=0$ reste défini. **Pourquoi + 0,25 ?** Un client très régulier a un écart-type proche de 0 : on diviserait par presque zéro. **Pourquoi borner ?** Une valeur extrême isolée ne doit pas écraser les autres.

**Exemple** : un client a payé 10, 12, 8, 15, 10 et 11 USD. On obtient $\mu_u = 2{,}469$ et $s_u = 0{,}426$. Une opération de 12 USD donne $z = 0{,}22$ (normal). Une opération de 300 USD donne $z = 7{,}6$ (rupture nette).

#### b) Solde, vidage, plafond KYC

$$\text{part du solde}=\min\!\Big(\frac{a_t}{B_t+1},\,5\Big),\qquad \text{vidage}=\mathbb{1}\big[B_t>1 \wedge a_t\ge 0{,}85\,B_t\big],\qquad \text{plafond KYC}=\frac{a_t}{L_{\text{KYC}}}$$

$B_t$ : solde avant l'opération ; $\mathbb{1}[\cdot]$ : **fonction indicatrice**, qui vaut 1 si la condition est vraie, 0 sinon ; $L_{\text{KYC}}$ : plafond du niveau KYC. Le « vidage » signale qu'on retire au moins 85 % du solde, typique de l'échange de SIM.

#### c) Vélocité (fréquence)

$$N_\Delta(t)=\big|\mathcal{H}_u(t,\Delta)\big|,\qquad \Delta\in\{1\,\text{h},\,24\,\text{h},\,7\,\text{j}\}$$

$\mathcal{H}_u(t,\Delta)$ : les opérations du client dans la fenêtre $]t-\Delta,\,t]$ ; les barres verticales désignent leur nombre. Une rafale de 6 opérations en une heure chez un client qui en fait une par jour trahit un vidage ou un test de carte.

#### d) Nouveauté du contexte

$$\text{nouvel appareil}=\mathbb{1}[n_u>0 \wedge d_t\notin D_u]$$

$d_t$ : appareil de l'opération ; $D_u$ : ensemble des appareils déjà connus du client ; $n_u>0$ : le client a un historique (sinon tout serait « nouveau »). Même principe pour la province, l'agent, le destinataire et le marchand.

**Destinataire lié à de nombreux clients** : $\ln(1+\text{nombre d'autres clients ayant échangé avec ce destinataire})$. Un compte mule reçoit de beaucoup de victimes sans lien entre elles.

#### e) Heure circulaire

$$\theta_t=\frac{2\pi h_t}{24},\qquad (\sin\theta_t,\ \cos\theta_t)$$

**Pourquoi un cercle ?** Si on codait l'heure par un nombre de 0 à 23, le modèle croirait que 23 h et 0 h sont très éloignées (écart 23), alors qu'elles sont voisines. Sur le cercle : 23 h → (−0,26 ; 0,97) et 0 h → (0 ; 1), deux points très proches ; midi → (0 ; −1), à l'opposé.

**Écart à l'heure habituelle** : moyenne circulaire des heures passées ($\bar\theta$), pondérée par la **régularité** $R$ (entre 0 et 1). Un client qui opère toujours vers 9 h a un $R$ proche de 1 : une opération à 3 h est très anormale. Un client aux horaires dispersés a un $R$ faible : l'écart compte peu.

#### f) Normalisation (centrage-réduction)

$$\tilde x_j=\operatorname{clip}\!\left(\frac{x_j-m_j}{\sigma_j},\,-10,\,10\right)$$

$m_j$, $\sigma_j$ : moyenne et écart-type de la variable $j$ **estimés sur la seule période d'entraînement**. Toutes les variables sont ramenées à la même échelle (indispensable pour le LSTM et l'autoencodeur). Estimer $m_j$ et $\sigma_j$ sur tout le jeu serait une fuite d'information.

> **Question probable :** « Comment garantissez-vous l'absence de fuite d'information ? »
> **Réponse :** « Par trois mesures. Les variables sont calculées par rejeu chronologique, à partir du seul passé du client. La normalisation est estimée sur l'entraînement seulement. Et le découpage est temporel : le test est postérieur à tout ce qui a servi à apprendre, y compris le choix du seuil, fait sur la validation. »

### B.4 Découpage temporel

| Tranche | Période | Usage |
|---|---|---|
| Entraînement | 01/2019 → 02/03/2023 | apprendre les modèles |
| Arrêt précoce | 02/03/2023 → 25/11/2023 | arrêter l'apprentissage au bon moment |
| Validation | 25/11/2023 → 13/12/2024 | choisir le seuil et calibrer la combinaison |
| Test | 13/12/2024 → 31/12/2025 | évaluation finale, jamais vue |

**Pourquoi pas un découpage aléatoire ?** Il mélangerait passé et futur : le modèle apprendrait sur des fraudes de 2025 pour juger 2023. En réalité, on apprend toujours sur le passé pour décider sur l'avenir.

**Pourquoi une tranche « arrêt précoce » distincte de la validation ?** Si on utilisait la même tranche pour arrêter l'apprentissage **et** choisir le seuil, on l'optimiserait deux fois : le seuil serait trop optimiste.

### B.5 Déséquilibre des classes

**Le piège** : avec 1,33 % de fraudes, un « modèle » qui déclare tout légitime a 98,67 % d'**exactitude** (*accuracy*), et ne détecte rien. L'exactitude est donc inutile ici.

**Pondération** : dans la perte d'XGBoost, chaque fraude pèse $w=N^-/N^+$ (nombre de légitimes divisé par nombre de fraudes), soit environ **74**. Une fraude manquée coûte autant que 74 fausses alertes à l'apprentissage.

**Sous-échantillonnage** : pour le LSTM, on ne garde à chaque époque qu'une partie (30 %) des opérations légitimes, tirée au hasard. Le réseau voit plus souvent des fraudes.

### B.6 Surapprentissage

**Surapprentissage** (*overfitting*) : le modèle apprend par cœur les données d'entraînement, y compris leur bruit, et généralise mal. Symptôme : excellent en entraînement, moins bon en validation.

| Mesure | Principe |
|---|---|
| Arrêt précoce | on arrête l'apprentissage quand la performance sur une tranche séparée cesse de progresser |
| *Dropout* (0,2) | on désactive au hasard 20 % des neurones à chaque pas : le réseau ne peut pas dépendre d'un seul chemin |
| Régularisation L2 | on pénalise les poids trop grands (AdamW pour le LSTM ; $\lambda$ et $\gamma$ pour XGBoost) |
| Diagnostic automatique | si la PR-AUC d'entraînement dépasse celle de validation de plus de 0,05, le modèle n'est jamais promu |

### B.7 Les métriques

**Matrice de confusion** (hybride, test) :

| | Prédit fraude | Prédit légitime |
|---|---|---|
| **Fraude réelle** | VP = 2 383 (vrais positifs) | FN = 54 (fraudes manquées) |
| **Légitime réelle** | FP = 122 (fausses alertes) | VN = 180 681 (vrais négatifs) |

| Métrique | Formule | Valeur (hybride) | Lecture métier |
|---|---|---|---|
| Précision | $VP/(VP+FP)$ | 2 383 / 2 505 = **0,951** | sur 100 alertes, 95 sont de vraies fraudes |
| Rappel | $VP/(VP+FN)$ | 2 383 / 2 437 = **0,978** | 97,8 % des fraudes sont interceptées |
| F1 | $2PR/(P+R)$ | **0,964** | compromis précision / rappel |
| Taux de faux positifs | $FP/(FP+VN)$ | 122 / 180 803 = **0,067 %** | clients honnêtes dérangés |
| Spécificité | $VN/(VN+FP)$ | **0,9993** | légitimes laissés passer sans alerte |
| F2 | $5PR/(4P+R)$ | **0,972** | donne deux fois plus de poids au rappel |

**Pourquoi F1 et pas la moyenne simple ?** F1 est la **moyenne harmonique** : elle s'effondre si l'une des deux est faible. Un modèle à 100 % de précision et 1 % de rappel a une moyenne simple de 50 %, mais un F1 de 2 %.

**Pourquoi F2 ?** Manquer une fraude coûte plus cher qu'une fausse alerte : on donne plus de poids au rappel.

#### PR-AUC contre ROC-AUC

**Courbe ROC** : taux de vrais positifs en fonction du taux de faux positifs, pour tous les seuils. **ROC-AUC** : aire sous cette courbe.

**Courbe précision-rappel** : précision en fonction du rappel, pour tous les seuils. **PR-AUC** (*Average Precision*) :

$$\text{AP}=\sum_n (R_n-R_{n-1})\,P_n$$

c'est-à-dire la précision moyenne, pondérée par chaque gain de rappel quand on abaisse le seuil.

**Pourquoi la PR-AUC ?** Le taux de faux positifs se divise par 180 803 légitimes : 1 000 fausses alertes ne font que 0,55 %, et la courbe ROC reste presque parfaite. La précision, elle, compare les fausses alertes aux vraies fraudes, et chute immédiatement. **Preuve dans mes résultats** : l'Isolation Forest a une ROC-AUC de 0,949 mais ne détecte que 39 % des fraudes ; sa PR-AUC (0,39) dit la vérité. Référence : Saito et Rehmsmeier (2015).

**Valeur de base** : la PR-AUC d'un modèle aléatoire vaut la prévalence (≈ 0,013), alors que la ROC-AUC d'un modèle aléatoire vaut 0,5.

#### Autres métriques (§ II.2.9 h)

$$MCC = \frac{VP \cdot VN - FP \cdot FN}{\sqrt{(VP+FP)(VP+FN)(VN+FP)(VN+FN)}}$$

**MCC** (coefficient de corrélation de Matthews) : corrélation entre prédiction et réalité, de −1 à +1, qui utilise les **quatre** cases de la matrice. Il reste fiable quand les classes sont déséquilibrées. Hybride : 0,964 ; autoencodeur : 0,766 malgré une meilleure précision.

**Exactitude équilibrée** : $(\text{rappel}+\text{spécificité})/2$, qui neutralise le poids écrasant des légitimes.

**Kappa de Cohen** : accord entre prédictions et réalité, **corrigé de l'accord dû au hasard** (0 = pas mieux que le hasard, 1 = accord parfait).

**Score de Brier** : $\frac{1}{n}\sum_i (\hat{p}_i - y_i)^2$, erreur quadratique moyenne des **probabilités** (pas des décisions). Plus il est bas, mieux c'est : hybride 0,00077.

**Rappel à budget de fausses alertes** : rappel obtenu quand on s'interdit plus de x % de faux positifs. C'est la question réelle d'un opérateur : « avec l'équipe que j'ai, combien de fraudes j'arrête ? » À 0,05 % de faux positifs : hybride 96,9 %, LSTM 94,0 %, XGBoost 92,3 %.

#### Le seuil de décision

$$\tau^*=\mathrm{argmax}_\tau \frac{2\,P(\tau)\,R(\tau)}{P(\tau)+R(\tau)}\quad\text{(sur la validation)}$$

Le modèle donne une probabilité ; le **seuil** la transforme en décision. $\mathrm{argmax}$ : la valeur de $\tau$ qui rend le F1 maximal. Choisi **sur la validation**, jamais sur le test : $\tau^*$ = 0,538. Sur le test, il tombe dans le **plateau** du F1 (entre 0,45 et 0,75, le F1 varie de moins d'un point) : le choix est robuste.

> **Question probable :** « Votre ROC-AUC est de 0,9999 : n'est-ce pas suspect ? »
> **Réponse :** « Sur des classes très déséquilibrées, la ROC-AUC est presque toujours élevée : même l'Isolation Forest atteint 0,95 en ne détectant que 39 % des fraudes. C'est pourquoi ma métrique principale est la PR-AUC. Et je rappelle que ces chiffres viennent de données simulées, où les fraudes sont plus nettes qu'en réalité. »

### B.8 Les tests statistiques

**Pourquoi ?** Un écart de 0,006 de PR-AUC peut venir du hasard de l'échantillon de test. Les tests disent si l'écart est **réel**.

**Bootstrap** : on fabrique 1 000 nouveaux jeux de test par tirage **avec remise** dans le jeu de test, on recalcule la métrique sur chacun, et on garde les valeurs entre le 2,5ᵉ et le 97,5ᵉ centile : c'est l'**intervalle de confiance à 95 %**.

**Apparié** : les deux modèles sont évalués sur **le même** jeu rééchantillonné, ce qui donne directement la distribution de leur **écart**.

**Par usager** : on tire des **clients**, pas des transactions. Les opérations d'un même client se ressemblent (elles sont corrélées) : les tirer séparément ferait croire à plus d'information qu'il n'y en a, et donnerait des intervalles trop étroits.

**Règle** : l'écart est **significatif** si son intervalle de confiance à 95 % **exclut 0**. Hybride − XGBoost : +0,0060 [+0,0044 ; +0,0079] → significatif.

**Test de McNemar exact.** On ne regarde que les opérations où les deux modèles **ne sont pas d'accord** : $b$ = seul A a raison, $c$ = seul B a raison. Si les deux modèles se valaient, chacun aurait raison une fois sur deux :

$$X\sim\mathcal{B}\big(b+c,\ \tfrac12\big),\qquad p=2\,P\big(X\le\min(b,c)\big)$$

$\mathcal{B}(n,\frac12)$ : loi binomiale (nombre de « pile » en $n$ lancers d'une pièce équilibrée). **Exemple** : hybride contre XGBoost, 156 contre 23. Obtenir 23 ou moins sur 179 avec une pièce équilibrée a une probabilité de **1,8 × 10⁻²⁵** : l'écart n'est pas dû au hasard.

**p-valeur** : probabilité d'observer un écart au moins aussi grand **si les modèles étaient équivalents**. Si p < 0,05, on rejette l'équivalence.

**Variance selon la graine** : on répète l'entraînement avec plusieurs graines. Si le classement change d'une graine à l'autre, l'écart n'est pas robuste.

> **Question probable :** « Pourquoi bootstrap par usager et pas par transaction ? »
> **Réponse :** « Parce que les transactions d'un même client ne sont pas indépendantes : un client qui a un comportement facile à modéliser apparaît des centaines de fois. Rééchantillonner les transactions sous-estimerait l'incertitude. En rééchantillonnant les clients, je respecte la vraie unité d'indépendance. »

### B.9 Les modèles comparés

#### Règles métier (système expert)

Seuils fixés à la main (montant, plafond KYC, liste noire). Transparentes et auditables, mais elles ignorent l'individu. Elles servent de **référence** : c'est la pratique actuelle. Résultat : PR-AUC 0,276, 1 474 fausses alertes et 1 567 fraudes manquées.

#### Régression logistique

$$p=\sigma\big(w_0+w_1x_1+\dots+w_{58}x_{58}\big),\qquad \sigma(z)=\frac{1}{1+e^{-z}}$$

On fait une somme pondérée des variables, puis la **fonction sigmoïde** $\sigma$ la transforme en probabilité entre 0 et 1. Très interprétable (chaque poids dit l'effet d'une variable) mais **linéaire** : elle ne capte pas les interactions (« nouvel appareil **et** vidage »). PR-AUC 0,951.

#### Arbre de décision, Random Forest, XGBoost

**Arbre de décision** : suite de questions oui/non sur les variables (« nouvel appareil ? », « part du solde > 0,85 ? ») qui aboutit à une feuille avec une prédiction.

**Random Forest** (*bagging*) : des centaines d'arbres appris **indépendamment**, chacun sur un échantillon tiré au hasard ; on fait la **moyenne** de leurs votes. Robuste, mais moins précis que le *boosting*. PR-AUC 0,984.

**XGBoost** (*gradient boosting*) : les arbres sont ajoutés **un par un**, chacun corrigeant les erreurs des précédents.

$$F(\tilde x)=\sum_{k=1}^{K}f_k(\tilde x)$$

$$\mathcal{L}=\sum_i w_i\Big[-y_i\ln\sigma(F_i)-(1-y_i)\ln\big(1-\sigma(F_i)\big)\Big]+\sum_k\Omega(f_k),\qquad \Omega(f)=\gamma T+\tfrac12\lambda\lVert w\rVert^2$$

- $f_k$ : le $k$-ième arbre ; $F$ : somme des arbres (score brut, ou *logit*) ;
- le crochet est l'**entropie croisée** (*log-loss*) : elle punit fortement une probabilité confiante mais fausse ;
- $w_i$ : poids de l'exemple (≈ 74 pour une fraude) ;
- $\Omega$ : **régularisation** ; $T$ : nombre de feuilles de l'arbre (pénalisé par $\gamma$) ; $\lVert w\rVert^2$ : taille des valeurs des feuilles (pénalisée par $\lambda$). Elle empêche des arbres trop complexes.

État de l'art sur données tabulaires, rapide, explicable exactement par TreeSHAP. Limite : il ne voit que l'opération actuelle, pas la séquence. PR-AUC 0,9895.

#### Isolation Forest (non supervisé)

On coupe les données au hasard, récursivement. Un point **rare** est isolé en très peu de coupes. Pas besoin d'étiquettes, mais une anomalie n'est pas forcément une fraude, et une fraude « normale » n'est pas une anomalie. PR-AUC 0,391.

#### Autoencodeur (non supervisé)

Réseau de neurones qui compresse puis reconstruit l'opération : $58\to32\to16\to8\to16\to32\to58$. Le goulot de 8 neurones l'oblige à apprendre l'**essentiel** des opérations normales.

$$\min_\phi\ \frac{1}{N}\sum_i\big\lVert \tilde x_i-g_\phi(\tilde x_i)\big\rVert_2^2$$

$g_\phi$ : le réseau (paramètres $\phi$) ; $\lVert\cdot\rVert_2^2$ : somme des carrés des écarts. Il est entraîné **sur les seules opérations légitimes**. Une opération qu'il reconstruit mal est inhabituelle : l'**erreur de reconstruction** sert de score d'anomalie. Il détecte l'inédit sans étiquette, mais il est aveugle aux fraudes qui imitent le normal : ingénierie sociale 0,3 %, fractionnement 0 %.

#### LSTM avec attention (séquentiel)

**Réseau récurrent** : il lit les 10 dernières opérations du client dans l'ordre, en gardant une **mémoire**. Le **LSTM** (*Long Short-Term Memory*, Hochreiter et Schmidhuber, 1997) contrôle cette mémoire par trois **portes** :

$$c_\tau=f_\tau\odot c_{\tau-1}+i_\tau\odot g_\tau,\qquad h_\tau=o_\tau\odot\tanh(c_\tau)$$

- $f_\tau$ : **porte d'oubli** (que garder de la mémoire passée) ; $i_\tau$ : **porte d'entrée** (quoi y ajouter) ; $o_\tau$ : **porte de sortie** (quoi en montrer) ;
- $c_\tau$ : mémoire (état de la cellule) ; $h_\tau$ : sortie à l'étape $\tau$ ; $\odot$ : produit terme à terme.

Les portes résolvent le problème du **gradient évanescent** des réseaux récurrents simples, qui oublient vite le début de la séquence.

**Attention** : au lieu de ne garder que la dernière sortie, on pondère toutes les étapes :

$$e_\tau=v^\top\tanh(W_a h_\tau+b_a),\qquad \alpha_\tau=\frac{e^{e_\tau}}{\sum_{\tau'}e^{e_{\tau'}}},\qquad c=\sum_\tau\alpha_\tau h_\tau$$

$e_\tau$ : score d'importance de l'opération $\tau$ ; la **fonction softmax** transforme ces scores en poids $\alpha_\tau$ positifs dont la somme vaut 1 ; $c$ : résumé pondéré de la séquence. **Intérêt pour l'analyste** : les poids $\alpha_\tau$ montrent **quelles opérations passées** ont pesé dans la décision. PR-AUC 0,9894.

#### L'hybride : empilement (*stacking*)

$$z_k=\frac{s_k-\mu_k}{\sigma_k},\qquad p=\sigma\Big(\beta_0+\sum_{k}\beta_k z_k\Big),\qquad k\in\{\text{XGB},\ \text{LSTM},\ \text{AE}\}$$

Les scores des trois composantes ($s_k$) sont standardisés ($z_k$), puis combinés par une **régression logistique** (le **méta-apprenant**) entraînée sur la **validation**, que les composantes n'ont pas vue. $\beta_k z_k$ est la **contribution de chaque composante**, affichée à l'analyste.

**Pourquoi le méta-apprenant est-il appris sur la validation ?** S'il apprenait sur l'entraînement, il ferait confiance aux composantes qui ont appris par cœur ces données, donc les plus surajustées.

> **Question probable :** « Pourquoi combiner trois modèles plutôt qu'un très bon modèle ? »
> **Réponse :** « Parce qu'ils voient trois choses différentes : XGBoost le profil de l'opération, le LSTM la dynamique de la séquence, l'autoencodeur l'anomalie, y compris inédite. L'ablation le prouve : retirer n'importe laquelle dégrade le modèle. Et la combinaison est significativement meilleure que chacune seule, avec 42 % de fausses alertes et 45 % de fraudes manquées en moins qu'XGBoost. »

### B.10 Ablation, matrice multicritère, robustesse du choix

**Ablation** : retirer une composante (ou une famille de variables) et mesurer la perte. Si le retrait dégrade, la composante est utile. Sans LSTM : PR-AUC 0,9905 ; sans XGBoost : 0,9912 ; sans autoencodeur : 0,9950 (peu de perte sur les fraudes connues, mais moins de fausses alertes avec lui, et seul détecteur de l'inédit).

**Matrice de décision multicritère** : note de 1 à 5 par critère, multipliée par son poids. Hybride :

$$5\times0{,}30+5\times0{,}20+4\times0{,}15+3\times0{,}15+5\times0{,}10+4\times0{,}10=4{,}45$$

XGBoost obtient 3,65. **Contrôles de robustesse** : avec des poids égaux, l'hybride reste premier (4,33) ; sur 2 000 pondérations tirées au hasard, il est premier dans 91 % des cas.

> **Question probable :** « Vos poids sont subjectifs. »
> **Réponse :** « Oui, une pondération comporte du jugement, c'est pourquoi les critères et les poids ont été fixés avant l'expérience, à partir des besoins. Et j'ai testé la sensibilité : avec des poids égaux, puis sur 2 000 pondérations aléatoires, l'hybride reste premier dans 91 % des cas. XGBoost ne passe devant que si presque tout le poids va à la simplicité et à l'explicabilité. »

### B.11 Calibration

**Modèle calibré** : quand il annonce 30 %, environ 30 % de ces opérations sont des fraudes. **Courbe de calibration** : probabilité annoncée contre fréquence observée. L'hybride a un excellent score de Brier (0,00077), mais **surestime** dans la zone 0,2 à 0,8 (annoncé 0,45, réel ≈ 20 %). Cette zone ne concerne que 0,2 % des opérations et n'affecte pas la décision, qui repose sur un seuil. Amélioration possible : **régression isotonique** sur la validation.

### B.12 Validité de l'étude

| Type de validité | Question qu'elle pose | Exemple dans ce travail |
|---|---|---|
| Interne | Le résultat vient-il bien de ce qu'on croit, sans biais du protocole ? | fuite d'information, circularité de H5, surapprentissage |
| Externe | Le résultat se généralise-t-il au monde réel ? | données simulées, étiquettes réelles imparfaites |
| De construit | Mesure-t-on bien ce qu'on prétend mesurer ? | canal Visa trop facile (effet plafond) |
| Statistique | Les conclusions statistiques sont-elles correctes ? | corrélation intra-client → bootstrap par usager |

**Circularité de H5** : l'évolution des fraudes est un paramètre du générateur. Montrer que le modèle réentraîné fait mieux prouve surtout que le **mécanisme** de mise à jour fonctionne, pas que les fraudes réelles évolueront ainsi.

**Effet plafond** : sur la carte Visa, toutes les méthodes supervisées atteignent 1,000. Le canal est trop facile pour les départager, et la transposabilité (H4) peut être surestimée.

**Validation sur données réelles (5 étapes)** : accord de données anonymisées → validation hors ligne → **mode observation** (2 à 4 semaines, le système note sans bloquer) → recalibrage des seuils et des coûts → mise en service progressive.

---

## PARTIE C — CONCEPTION (Section 3)

### C.1 Principes d'architecture

**Microservices** : le système est découpé en services indépendants (intégration, notation, back-office, workers, apprentissage), déployables et dimensionnables séparément. Si la notation est surchargée, on n'ajoute des copies que d'elle.

**Architecture orientée événements** : le **chemin critique** (la décision) est **synchrone** et minimal ; tout le reste (enregistrer, alerter, journaliser) est publié dans un **bus d'événements** et traité **en parallèle**, de façon asynchrone. La décision n'attend pas l'écriture en base.

**Kafka** (ici Redpanda, compatible) : journal d'événements distribué. Les producteurs écrivent dans des **sujets** (*topics*), les consommateurs les lisent à leur rythme, et les messages sont conservés (on peut les rejouer). Quatre sujets : `transactions.scored`, `fraud.alerts`, `analyst.feedback`, `audit.logs`.

**Workers** : petits services qui consomment Kafka. *persister* enregistre en base, *alerter* ouvre les dossiers et prévient le client, *auditor* écrit le journal d'audit.

**Schéma pivot** (`UnifiedTransaction`) : un format unique entre l'intégration et la notation. **Patron *Adapter*** : un adaptateur par format d'opérateur le convertit vers ce schéma. Ajouter un opérateur revient à écrire un adaptateur, sans toucher au moteur.

**Défense en profondeur** : plusieurs barrières indépendantes (modèle appris, règles métier, lois physiques). Si l'une est trompée, une autre peut tenir.

**Explicabilité par conception** : chaque décision est produite avec son explication, et non expliquée après coup.

### C.2 Base de données et magasin de profils

**PostgreSQL** : base relationnelle. **TimescaleDB** : extension qui transforme une table en **hypertable**, partitionnée automatiquement par le temps (en *chunks*) ; les requêtes sur une période récente ne lisent que les morceaux concernés.

**Clé primaire composite** (`transaction_id`, `tx_time`) : imposée par le partitionnement temporel ; elle garantit aussi l'idempotence de l'enregistrement.

**Redis** : base **en mémoire**, lue en moins d'une milliseconde. Elle stocke le profil de chaque client (agrégats, appareils connus, 10 dernières opérations) et les décisions pendant 30 minutes (idempotence).

**Verrou** : deux opérations simultanées d'un même client sont traitées l'une après l'autre ; sinon chacune lirait l'ancien profil et l'une des mises à jour serait perdue (**condition de concurrence**).

**bcrypt** : fonction de hachage **lente et salée** pour les mots de passe. On ne stocke jamais le mot de passe, seulement son empreinte ; la lenteur rend les attaques par force brute coûteuses.

#### Journal d'audit chaîné

$$h_n = \mathrm{SHA256}\big(h_{n-1}\ \Vert\ \text{contenu}_n\big)$$

**SHA-256** : **fonction de hachage cryptographique**. Elle donne une empreinte de 256 bits ; changer un seul caractère change toute l'empreinte, et on ne peut pas retrouver le contenu à partir d'elle. $\Vert$ : concaténation. Chaque entrée contient l'empreinte de la précédente : modifier une entrée ancienne change son empreinte et **casse toute la chaîne** qui suit. C'est le principe d'une chaîne de blocs, sans réseau. En plus, un **déclencheur** (*trigger*) en base interdit UPDATE et DELETE.

> **Question probable :** « Un administrateur de la base ne peut-il pas tout recalculer ? »
> **Réponse :** « Il pourrait recalculer la chaîne s'il désactivait le déclencheur, d'où l'importance de séparer les droits. Pour aller plus loin, on publie régulièrement la dernière empreinte à l'extérieur (au régulateur, par exemple) : toute réécriture du passé devient alors détectable. »

### C.3 Comportement dynamique

**Notation en temps réel (séquence)** : l'institution envoie l'opération **avant** de l'exécuter → l'intégration vérifie la clé et convertit le format → la notation vérifie l'idempotence, met à jour le profil sous verrou, calcule les variables et les lois physiques, applique le modèle, la typologie et l'analyse du message → décision renvoyée en synchrone → publication dans Kafka.

**Cycle de vie d'un dossier (états-transitions)** : OUVERT → EN_COURS → FRAUDE_CONFIRMEE ou FAUX_POSITIF. Les deux états finaux produisent une **étiquette** ($y=1$ ou $y=0$) et ne peuvent plus être quittés.

**Champion / challenger** : le modèle en service (*champion*) n'est remplacé par un nouveau (*challenger*) que si celui-ci est **meilleur sur la même période** et passe les contrôles de qualité. On ne remplace jamais un modèle « parce qu'il est plus récent ».

**Rechargement à chaud** : le service charge le nouveau modèle à côté de l'ancien, le contrôle, puis l'échange en une opération, sans interruption de service.

### C.4 Le moteur de détection

#### a) Décision coût-sensible

$$\mathbb{E}[\text{APPROVE}]=p\,m,\qquad \mathbb{E}[\text{VERIFY}]=c_f+p\,m(1-\kappa),\qquad \mathbb{E}[\text{BLOCK}]=(1-p)(c_b+\lambda m)$$

- $p$ : probabilité de fraude ; $m$ : montant (USD) ; $\mathbb{E}[\cdot]$ : **espérance**, le coût moyen attendu ;
- **APPROVE** : on perd le montant si c'est une fraude (probabilité $p$) ;
- **VERIFY** : on paie la friction $c_f$ à coup sûr, et on ne perd le montant que si la fraude passe malgré la vérification ($1-\kappa$) ;
- **BLOCK** : on ne perd que si le client était honnête ($1-p$) : coût fixe $c_b$ plus une part $\lambda$ du montant.

Paramètres Mobile Money : $c_f$ = 0,30 USD, $\kappa$ = 0,85, $c_b$ = 4 USD, $\lambda$ = 0,05 (carte Visa : 0,15 ; 0,90 ; 6 ; 0,05 : la vérification 3-D Secure est moins chère et plus efficace).

**Exemples (Mobile Money)** :

| Cas | APPROVE | VERIFY | BLOCK | Décision |
|---|---|---|---|---|
| p = 0,30 ; m = 500 USD | 150,00 | 22,80 | 20,30 | **BLOCK** |
| p = 0,30 ; m = 10 USD | 3,00 | 0,75 | 3,15 | **VERIFY** |
| p = 0,05 ; m = 40 USD | 2,00 | 0,60 | 5,70 | **VERIFY** |
| p = 0,005 (sous 0,01) | — | — | — | **APPROVE** directe (RG-04) |

**Message clé** : à probabilité égale (0,30), on bloque 500 USD mais on fait seulement vérifier 10 USD. Le seuil unique ne sait pas faire cela.

**Niveau de risque affiché** : CRITIQUE si $p \ge \max(0{,}9;\ \tau^*)$, ÉLEVÉ si $p \ge \tau^*$, MOYEN si $p \ge \tau^*/5$, FAIBLE sinon.

#### b) Lois physiques

$$d=2R\arcsin\sqrt{\sin^2\!\tfrac{\varphi_2-\varphi_1}{2}+\cos\varphi_1\cos\varphi_2\sin^2\!\tfrac{\lambda_2-\lambda_1}{2}}$$

**Formule de haversine** : distance **de grand cercle** (la plus courte à la surface de la Terre) entre deux points de latitudes $\varphi$ et de longitudes $\lambda$ ; $R$ = 6 371 km (rayon terrestre).

$$t_{\min}(d)=\min\Big(\frac{d}{80},\ 2+\frac{d}{800}\Big),\qquad I=\max\Big(0,\ \frac{t_{\min}(d)}{\Delta t}-1\Big)$$

$t_{\min}$ : durée minimale du trajet, par la route (80 km/h) ou en avion (800 km/h + 2 h de formalités). $\Delta t$ : temps écoulé depuis l'opération précédente. **Infaisabilité** $I$ : 0 si le trajet est possible ; $I \ge 1$ si le client aurait dû aller au moins deux fois plus vite que le moyen le plus rapide.

**Exemple** : Kinshasa → Lubumbashi = 1 568 km, soit 3,96 h au minimum (en avion). Deux opérations à 30 minutes d'intervalle : $I = 3{,}96/0{,}5 - 1 = 6{,}9$, violation nette (attaque par relais : quelqu'un utilise la session du client à distance). À 2 heures d'intervalle : $I = 0{,}98$, juste sous le seuil.

**Conservation** : un débit ne peut pas dépasser le solde. On mesure aussi la vitesse de vidage du compte.

**Pourquoi c'est important** : un modèle appris ne connaît que les fraudes qu'il a vues. Les lois physiques valent pour toute fraude, même inédite : lors d'une attaque par relais simulée, le modèle de données seul en détecte 0,3 %, les lois physiques 100 %.

#### c) Explication : SHAP

$$F(\tilde x)=\phi_0+\sum_{j=1}^{58}\phi_j$$

**Valeurs de Shapley** (théorie des jeux, Lundberg et Lee, 2017) : on répartit le score d'une opération entre les variables, comme on répartirait un gain entre les joueurs d'une équipe. $\phi_0$ : score moyen ; $\phi_j$ : contribution de la variable $j$ (positive : elle pousse vers « fraude »). Chaque $\phi_j$ est la contribution marginale moyenne de la variable sur toutes les coalitions possibles de variables.

**TreeSHAP** : algorithme qui calcule ces valeurs **exactement** et rapidement pour les arbres (XGBoost), au lieu de les approcher. **Lecture** : « cette opération est suspecte surtout parce que l'appareil est nouveau (+2,1) et que le montant vide le solde (+1,7) ».

#### d) Recherche de cas similaires (RAG sans modèle de langage)

**k plus proches voisins** : on cherche les opérations passées les plus proches dans l'espace des 58 variables (distance euclidienne), et la part de fraudes parmi elles. Si elle contredit la décision du modèle, un indicateur « divergent » conseille une revue attentive.

**TF-IDF** (*Term Frequency – Inverse Document Frequency*) : pondération d'un mot, forte s'il est fréquent dans un document et rare dans les autres. Sert à retrouver, dans une base de procédures, la fiche du type de fraude concerné.

**RAG** (*Retrieval-Augmented Generation*) : produire une réponse appuyée sur des documents retrouvés. Ici, **sans modèle de langage externe** : les preuves viennent uniquement de sources vérifiables, rien n'est inventé, et aucune donnée ne quitte la plateforme.

#### e) Analyse du message (NLP)

$$S_{\text{IS}}=1-\prod_{c\in\mathcal{C}}(1-w_c)$$

**OU probabiliste** (*noisy-OR*) : chaque catégorie d'indice détectée (urgence, gain, faux agent…) a un poids $w_c$. Le score est la probabilité qu'**au moins un** indice soit réellement révélateur. Deux indices de poids 0,5 donnent $1-0{,}5\times0{,}5=0{,}75$. Règle RG-10 : le texte seul impose une vérification, **jamais** un blocage. Le texte n'est jamais stocké en clair.

#### f) Typologie

$$\hat P(k\mid\tilde x,c)=\frac{P(k\mid\tilde x)\,\mathbb{1}[k\in\mathcal{K}_c]}{\sum_{k'\in\mathcal{K}_c}P(k'\mid\tilde x)}$$

XGBoost **multiclasse** (fonction *softmax*), entraîné sur les seules fraudes. On met à zéro les typologies impossibles sur le canal $c$ ($\mathcal{K}_c$ : un « test de carte » n'existe pas en Mobile Money), puis on **renormalise** pour que la somme fasse 1. Exemple : si le modèle donne 0,6 SIM swap, 0,3 test de carte, 0,1 ingénierie sociale pour une opération Mobile Money, on obtient 0,6/0,7 = 0,86 et 0,1/0,7 = 0,14.

### C.5 API partenaires

**API** (*Application Programming Interface*) : interface par laquelle des logiciels d'autres institutions utilisent le système. **REST** : échanges HTTP sur des ressources (`POST /v1/transactions`). **Versionnée** (`/v1`) : une évolution incompatible devient `/v2` sans casser les intégrations existantes. **OpenAPI** : description standard de l'API, qui produit une documentation interactive.

**Clé d'API de 256 bits par institution** : seule son **empreinte SHA-256** est stockée ; la clé n'est montrée qu'une fois. Une fuite de la base ne révèle pas les clés.

**Droits (*scopes*)** : transactions, feedback, supervision. Le régulateur ne soumet pas d'opérations ; une banque ne supervise pas le secteur (moindre privilège).

**Isolement** : le code de l'institution est fixé par le serveur d'après la clé, jamais d'après la requête. Une opération d'une autre institution renvoie **la même erreur 404** qu'une opération inexistante : on ne révèle même pas qu'elle existe.

**Limitation de débit** (*rate limiting*) : nombre maximal de requêtes par seconde, pour protéger le service contre les abus et les pannes en cascade.

### C.6 Apprentissage continu et dérive

**Dérive des données** (*data drift*) : la distribution des variables change en production (nouveaux usages, inflation…). **Dérive de concept** : la relation entre variables et fraude change (nouvelles techniques de fraude). Dans les deux cas, le modèle vieillit.

**Test de Kolmogorov-Smirnov** : $D=\sup_x|F_{\text{réf}}(x)-F_{\text{prod}}(x)|$, plus grand écart entre les deux **fonctions de répartition** (courbes cumulées) d'une variable, en référence et en production.

**PSI** (*Population Stability Index*) :

$$\mathrm{PSI}=\sum_i (q_i-p_i)\,\ln\frac{q_i}{p_i}$$

On découpe la variable en classes ; $p_i$ : part de la référence dans la classe $i$ ; $q_i$ : part en production. **Seuils usuels** : < 0,1 stable ; 0,1 à 0,2 à surveiller ; > 0,2 dérive. **Exemple** : référence 25/25/25/25 %, production 10/20/30/40 % → PSI = 0,228, dérive.

**Taux de nouveauté** : part des opérations dont l'erreur de reconstruction de l'autoencodeur dépasse le 99ᵉ centile de référence. Attendu : 1 % ; alarme au-dessus de 4 %.

**Délai de carence** (*cooldown*) : durée minimale entre deux réentraînements, pour qu'une dérive persistante ne relance pas l'entraînement en boucle.

**Porte de détection** : contrôle qui exige du challenger un rappel minimal **par type de fraude** et un taux maximal de faux positifs. Un modèle meilleur en moyenne, mais qui oublie une typologie, est rejeté.

**MLflow** : registre des modèles et des expériences (versions, paramètres, métriques).

> **Question probable :** « Qui fournit les étiquettes pour réentraîner ? »
> **Réponse :** « Trois sources : les verdicts des analystes sur les alertes, les plaintes des clients pour les fraudes laissées passer, et les retours des institutions par l'API. Les opérations sans plainte après 7 jours sont considérées comme légitimes, ce qui est une approximation assumée. »

### C.7 Sécurité

**JWT** (*JSON Web Token*) : jeton signé remis à la connexion, qui prouve l'identité et le rôle à chaque requête, sans session côté serveur. Sa signature empêche de le modifier.

**RBAC** (*Role-Based Access Control*) : les droits dépendent du rôle (analyste < superviseur < administrateur), chaque rôle héritant des droits du précédent.

**Moindre privilège** : chaque acteur n'a que les droits strictement nécessaires.

**Injection SQL** : attaque qui glisse du code SQL dans une saisie. Parade : **requêtes paramétrées** (SQLAlchemy), qui séparent le code des données. **XSS** (*Cross-Site Scripting*) : attaque qui injecte du code dans une page affichée à d'autres. Parade : échappement à l'affichage et en-têtes de sécurité.

### C.8 Déploiement et supervision

**Conteneur Docker** : application empaquetée avec toutes ses dépendances, qui fonctionne à l'identique partout. **Docker Compose** : lance la vingtaine de conteneurs du prototype sur une machine. **Kubernetes** : orchestre les conteneurs sur plusieurs machines (redémarrage automatique, montée en charge, plusieurs sites : Kinshasa et Katanga).

**Prometheus** : collecte les **métriques** (latence, décisions, erreurs, dérive). **Grafana** : tableaux de bord. **Loki** : centralise les **journaux**. **Règles d'alerte** : hausse des comportements nouveaux, violations physiques, rejet d'un modèle, incohérence du magasin de profils.

**Latence p95** : 95 % des requêtes sont plus rapides que cette valeur (104 ms). C'est plus exigeant que la moyenne, qui cache les requêtes lentes.

### C.9 Choix technologiques (à savoir justifier)

| Choix | Justification courte |
|---|---|
| Python + FastAPI | même langage que les modèles ; asynchrone ; documentation OpenAPI automatique |
| XGBoost | état de l'art tabulaire ; SHAP exact |
| PyTorch | LSTM avec attention, autoencodeur |
| Redis | profil lu en moins d'1 ms ; verrous ; expiration automatique |
| PostgreSQL + TimescaleDB | relationnel + séries temporelles |
| Kafka | découplage, rejeu, garanties de livraison |
| Next.js | interface rapide, composants réutilisables |
| Logiciels libres | aucun coût de licence ni dépendance à un service en ligne (contexte congolais) |

---

## PARTIE D — QUESTIONS PIÈGES DU JURY ET RÉPONSES

**1. « 99,5 % de PR-AUC, c'est trop beau. »**
« C'est vrai sur données simulées, où les fraudes sont plus nettes qu'en réalité. Je l'écris explicitement dans les limites. Ce qui est robuste, c'est la comparaison : toutes les méthodes sont évaluées dans les mêmes conditions, et l'écart est statistiquement significatif. En production, j'attends des chiffres plus bas, d'où le mode observation prévu avant tout blocage. »

**2. « Votre générateur a été conçu par vous : le modèle apprend vos propres règles. »**
« C'est une limite réelle : un modèle peut retrouver la logique du générateur. Pour la réduire, le générateur produit des cas légitimes difficiles (changement de téléphone, voyages, usages nocturnes) et des fraudes qui imitent le normal (ingénierie sociale). La preuve que la tâche n'est pas triviale : les règles métier ne dépassent pas 36 % de rappel et l'Isolation Forest 39 %. »

**3. « Pourquoi pas le deep learning seul ? »**
« Le LSTM seul égale XGBoost (PR-AUC 0,9894 contre 0,9895), mais il est moins explicable et plus coûteux. C'est leur combinaison qui est significativement meilleure. »

**4. « Le temps réel est-il tenu ? »**
« La médiane est de 59 ms. Le 95ᵉ centile, 104 ms, est à la limite de l'objectif de 100 ms. La notation est sans état local (le profil est dans Redis) : on peut ajouter des copies du service pour réduire la latence. »

**5. « Un client honnête bloqué à tort, que se passe-t-il ? »**
« Dans les cas intermédiaires, le système fait vérifier au lieu de bloquer : le client confirme par PIN ou OTP et l'opération passe. Le blocage est réservé aux probabilités très élevées ou aux gros montants. Et chaque blocage ouvre un dossier qu'un analyste peut déclarer faux positif, ce qui devient une étiquette pour corriger le modèle. »

**6. « Comment expliquez-vous une décision à un client ou à la BCC ? »**
« Par TreeSHAP, qui donne la contribution exacte de chaque variable, par la contribution de chaque composante du modèle, par les poids d'attention sur les opérations passées et par des cas similaires. Les règles métier ajoutées sont nommées et auditables, et tout est inscrit dans un journal inaltérable. »

**7. « Et si les fraudeurs s'adaptent au modèle ? »**
« C'est l'objet de H5 et de l'apprentissage continu : surveillance de la dérive et des comportements nouveaux, réentraînement champion/challenger. Les lois physiques et les règles ne dépendent pas de l'apprentissage : elles tiennent même face à une fraude inédite. »

**8. « Pourquoi le seuil 0,538 ? »**
« C'est celui qui maximise le F1 sur la validation. Je ne l'ai jamais ajusté sur le test, et sur le test il tombe dans un plateau : entre 0,45 et 0,75, le F1 bouge de moins d'un point. En exploitation, la décision coût-sensible prend le relais du seuil unique. »

**9. « H5 est circulaire. »**
« Oui, et je le dis : l'évolution des fraudes est un paramètre du générateur. H5 démontre que le mécanisme de mise à jour fonctionne, pas que les fraudes réelles évolueront de cette façon. Sa validation réelle demande des données de plusieurs années. »

**10. « Le canal Visa est-il vraiment testé (H4) ? »**
« Les résultats sur Visa sont parfaits pour toutes les méthodes supervisées : c'est un effet plafond, que je signale comme menace à la validité de construit. La transposabilité est donc probablement surestimée et doit être confirmée sur des données réelles de cartes. »

**11. « Quelle est votre contribution originale ? »**
« Un système complet adapté au contexte congolais : profilage comportemental sans dépendre du smartphone, double monnaie au taux de l'année, lois physiques entre provinces, décision graduée selon le coût, explication sans modèle de langage externe, API ouverte aux opérateurs et au régulateur, et un protocole statistique rigoureux (bootstrap par usager, McNemar) sur un générateur reproductible confronté aux statistiques officielles. »

**12. « Pourquoi ne pas utiliser ChatGPT pour expliquer les décisions ? »**
« Pour trois raisons : confidentialité (aucune donnée client ne doit quitter la plateforme), connectivité (pas de dépendance à un service en ligne) et fiabilité (un modèle de langage peut inventer). Mes explications viennent uniquement de sources vérifiables. »

**13. « Pourquoi l'autoencodeur s'il apporte si peu ? »**
« Il apporte peu en PR-AUC sur les fraudes connues, mais il réduit les fausses alertes et c'est la seule composante qui signale les comportements jamais vus. Son taux de nouveauté déclenche le réentraînement. »

**14. « Le McNemar et le bootstrap disent-ils la même chose ? »**
« Ils sont complémentaires. Le bootstrap porte sur une métrique globale (la PR-AUC, sur tous les seuils) et donne un intervalle de confiance. McNemar porte sur les décisions au seuil retenu, opération par opération. Les deux concluent à la supériorité de l'hybride. »

---

## PARTIE E — GLOSSAIRE

| Terme | Définition simple |
|---|---|
| Ablation | retirer un composant pour mesurer son apport |
| Arrêt précoce | arrêter l'apprentissage quand la performance sur une tranche séparée cesse de progresser |
| Attention | mécanisme qui pondère les éléments d'une séquence selon leur importance |
| Autoencodeur | réseau qui compresse puis reconstruit ; l'erreur de reconstruction mesure l'anomalie |
| *Bagging* | moyenne de modèles appris indépendamment sur des échantillons différents (Random Forest) |
| *Boosting* | modèles ajoutés successivement, chacun corrigeant les erreurs des précédents (XGBoost) |
| Bootstrap | rééchantillonnage avec remise pour estimer l'incertitude d'une mesure |
| Calibration | accord entre probabilités annoncées et fréquences observées |
| Champion / challenger | le modèle en service n'est remplacé que par un meilleur, sur la même période |
| Dérive | changement de la distribution des données ou de la relation avec la fraude |
| Entropie croisée | perte qui punit les probabilités confiantes mais fausses |
| Étiquette | vérité connue d'une opération : fraude (1) ou légitime (0) |
| Fuite d'information | usage, pendant l'apprentissage, d'une information indisponible au moment de décider |
| Hachage | empreinte de taille fixe, impossible à inverser, qui change au moindre changement |
| Idempotence | refaire la même requête donne le même résultat, sans effet en double |
| Intervalle de confiance | plage de valeurs plausibles pour une mesure, à un niveau de confiance donné |
| KYC | niveau d'identification du client, avec plafonds associés |
| Latence p95 | durée sous laquelle se trouvent 95 % des requêtes |
| LSTM | réseau récurrent à portes qui garde la mémoire d'une séquence |
| Méta-apprenant | modèle qui combine les sorties d'autres modèles (empilement) |
| Microservice | service indépendant, déployable séparément |
| p-valeur | probabilité d'un écart aussi grand si les modèles étaient équivalents |
| PR-AUC | aire sous la courbe précision-rappel ; métrique principale sur classes déséquilibrées |
| PSI | indice de stabilité d'une population entre référence et production |
| Rappel | part des fraudes détectées |
| Précision | part des alertes qui sont de vraies fraudes |
| Régularisation | pénalité qui limite la complexité d'un modèle pour éviter le surapprentissage |
| SHAP | répartition du score d'une décision entre les variables (valeurs de Shapley) |
| Sigmoïde | fonction qui transforme un nombre quelconque en probabilité entre 0 et 1 |
| Softmax | fonction qui transforme des scores en probabilités dont la somme vaut 1 |
| Surapprentissage | apprendre par cœur l'entraînement et mal généraliser |

---

## Annexe — Fonctions ajoutées au système après la rédaction du chapitre II

Le prototype de démonstration contient cinq fonctions qui ne sont pas encore décrites dans le chapitre II. Si le jury les voit pendant la démonstration, voici l'essentiel à dire.

| Fonction | Écran | Ce qu'elle fait | Résultat mesuré (données simulées) |
|---|---|---|---|
| Réseaux de fraude | Réseaux de fraude | relie les comptes par les portefeuilles, appareils, agents et marchands partagés ; détecte les réseaux de mules | 54 fraudes rattrapées que le modèle manquait, dont 50 d'ingénierie sociale |
| Boucle de retour | Revue & qualité | file de revue (cas incertains, nouveaux, liés à un réseau, échantillon témoin aléatoire) ; verdicts vérifiés pondérés au réentraînement | fraudes manquées ramenées de 73 à 38 à budget de revue égal |
| Politique de coût | Politique de décision | paramètres de coût réglables par canal et par opérateur, simulés avant application | perte divisée par plus de deux par rapport à un seuil unique |
| Sécurité | Sécurité du compte, Alertes | double authentification facultative, verrouillage après 5 échecs, validation à quatre yeux des déblocages ≥ 500 USD | — |
| Équité | Équité du modèle | taux de fausses alertes par province, opérateur, niveau KYC, revenu, avec intervalles de confiance | clients les plus modestes : 2,3 fois plus de fausses alertes que les plus aisés |

**Phrase prête** : « Ces fonctions prolongent la conception du chapitre II. La plus importante pour la défense est l'équité : sur données simulées, les clients les plus modestes subissent 2,3 fois plus de fausses alertes que les plus aisés. Le système le mesure et l'affiche, pour que l'opérateur puisse corriger avant que cela ne devienne une discrimination. »
