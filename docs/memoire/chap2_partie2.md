## II. Méthodologie

### Cadre méthodologique

Ce travail relève de la **science de la conception** (*Design Science Research*, Hevner et al., 2004). Cette démarche convient aux recherches dont le résultat est un **artefact** : on le construit pour répondre à un problème réel, puis on l'évalue de façon rigoureuse. Ici, l'artefact est le système de détection, et son évaluation passe par le test des cinq hypothèses.

Le volet données suit le cycle **CRISP-DM** (*Cross Industry Standard Process for Data Mining*, Chapman et al., 2000), standard de fait des projets d'exploration de données. Ce cycle est itératif : l'évaluation peut renvoyer à une étape antérieure, par exemple lorsqu'elle révèle une fuite d'information (tableau II.24).

*Tableau II.24 — Application du cycle CRISP-DM.*

| Étape CRISP-DM | Contenu dans ce travail | Livrable |
|---|---|---|
| 1. Compréhension du métier | Contexte RDC, typologies de fraude, acteurs, besoins | Partie I, section 1 |
| 2. Compréhension des données | Générateur synthétique 2019-2025, analyse exploratoire | Partie I, sections 2 et 3 ; chapitre III |
| 3. Préparation des données | 58 variables comportementales, normalisation, découpage temporel | Partie I, section 4 |
| 4. Modélisation | Modèles de référence, modèle hybride, classifieur de typologie | Partie II, sections 1 à 3 |
| 5. Évaluation | Protocole statistique H1 à H5 et évaluations complémentaires | Partie II, sections 4 à 6 ; chapitre III |
| 6. Déploiement | Architecture temps réel, API, supervision, apprentissage continu | Chapitre III |

Le développement logiciel suit une démarche **itérative et incrémentale**, inspirée du processus unifié et de sa variante en Y, **2TUP** (*Two Track Unified Process*, Roques et Vallée, 2011). Cette variante sépare une branche fonctionnelle (les besoins du métier), une branche technique (les contraintes et les choix d'architecture) et une branche de réalisation qui les fusionne. Le projet a été conduit en incréments successifs, chacun produisant une version utilisable et s'achevant par une évaluation : données et variables, modèles, service de notation, intégration des opérateurs, tableau de bord, workers asynchrones, supervision, conteneurisation, apprentissage continu, puis réseaux de fraude, boucle de retour, politique de coût, sécurité et équité. Les diagnostics ont conduit à des corrections successives, notamment sur les fuites d'information, la cohérence entre l'entraînement et la production, le surapprentissage et le choix des seuils. La modélisation utilise le langage **UML** (*Unified Modeling Language*), dont les diagrammes sont présentés au chapitre III.

### 1. Choix des algorithmes et modèles

#### 1.1 Les méthodes candidates

Pour éprouver les hypothèses H1 et H3, huit méthodes, représentatives des grandes familles de l'apprentissage automatique appliqué à la fraude, sont mises en concurrence, des plus simples aux plus élaborées (tableau II.25).

*Tableau II.25 — Méthodes comparées.*

| Méthode | Famille | Principe | Forces attendues | Faiblesses attendues |
|---|---|---|---|---|
| Règles métier | Système expert | Seuils fixes (montant, plafond, liste noire) | Simple, transparent, auditable | Ignore l'individu, facile à contourner |
| Régression logistique | Linéaire supervisée | Combinaison linéaire des variables passée dans une sigmoïde | Interprétable, rapide | Ne capte pas les interactions non linéaires |
| Random Forest | Ensemble d'arbres (*bagging*) | Moyenne de nombreux arbres appris sur des échantillons différents | Robuste, peu de réglages | Moins précis que le *boosting*, explication plus lourde |
| XGBoost | Ensemble d'arbres (*boosting*) | Arbres ajoutés successivement pour corriger les erreurs des précédents | État de l'art sur données tabulaires ; TreeSHAP exact | Ne voit que l'opération courante, pas la séquence |
| Isolation Forest | Détection d'anomalies non supervisée | Isole les points rares par partitions aléatoires | Sans étiquette, détecte l'inédit | Une anomalie n'est pas toujours une fraude |
| Autoencodeur | Réseau de neurones non supervisé | Apprend à reconstruire les opérations légitimes ; l'erreur de reconstruction mesure l'anomalie | Sans étiquette de fraude, détecte l'inédit | Aveugle aux fraudes qui imitent le comportement normal |
| LSTM avec attention | Réseau récurrent supervisé | Lit la séquence des 10 dernières opérations | Capte la dynamique (escalade, salves) | Plus coûteux, explication moins directe |
| **Hybride (proposé)** | Empilement (*stacking*) | Combine XGBoost, LSTM et autoencodeur par une régression logistique | Cumule les forces des trois | Plus complexe à entraîner et à maintenir |

Toutes les méthodes reçoivent les mêmes données, les mêmes 58 variables et sont évaluées sur le même jeu de test. Un second étage, un classifieur de typologie, identifie le type de fraude des opérations signalées.

#### 1.2 Fonctionnement formel des modèles

**Règles métier.** Un score additif compte les conditions remplies parmi six : montant supérieur à cinq fois l'habitude, nouvel appareil, opération de nuit, vidage du solde, adresse IP étrangère, rafale de quatre opérations ou plus en une heure. Elles reproduisent la pratique actuelle du secteur et servent de référence.

**Régression logistique.** Une somme pondérée des variables est transformée en probabilité par la **fonction sigmoïde** $\sigma$ :

$$p=\sigma\big(w_0+w_1\tilde x_1+\dots+w_{58}\tilde x_{58}\big),\qquad \sigma(z)=\frac{1}{1+e^{-z}}$$

Chaque poids $w_j$ mesure l'effet de la variable $j$, ce qui la rend très interprétable ; mais le modèle est linéaire et ne capte pas les interactions (« nouvel appareil **et** vidage »).

**Arbre, Random Forest et XGBoost.** Un arbre de décision est une suite de questions oui / non sur les variables, qui aboutit à une feuille portant une prédiction. La **Random Forest** (Breiman, 2001) moyenne des centaines d'arbres appris indépendamment sur des échantillons tirés au hasard (*bagging*). **XGBoost** (Chen et Guestrin, 2016) ajoute les arbres un par un, chacun corrigeant les erreurs des précédents (*gradient boosting*). Il construit un modèle additif de $K$ arbres, $F(\tilde x)=\sum_{k=1}^{K}f_k(\tilde x)$, en minimisant une perte logistique pondérée et régularisée :

$$\mathcal{L}=\sum_i w_i\Big[-y_i\ln\sigma(F_i)-(1-y_i)\ln\big(1-\sigma(F_i)\big)\Big]+\sum_k\Omega(f_k),\qquad \Omega(f)=\gamma T+\tfrac12\lambda\lVert w\rVert^2$$

Le crochet est l'**entropie croisée**, qui punit fortement une probabilité confiante mais fausse ; $w_i$ est le poids de l'exemple (environ 74 pour une fraude) ; $\Omega$ est la **régularisation**, qui pénalise le nombre de feuilles $T$ (par $\gamma$) et la taille de leurs valeurs (par $\lambda$) pour empêcher des arbres trop complexes.

**Isolation Forest.** Cette méthode non supervisée découpe les données au hasard, récursivement. Un point **rare** est isolé en très peu de coupes (Liu et al., 2008). Elle n'a pas besoin d'étiquettes, mais une anomalie n'est pas forcément une fraude.

**Autoencodeur.** Ce réseau de neurones compresse puis reconstruit chaque opération : $58\to32\to16\to8\to16\to32\to58$. Le goulot de 8 neurones l'oblige à apprendre l'essentiel des opérations normales (Hinton et Salakhutdinov, 2006). Il est entraîné **sur les seules opérations légitimes** :

$$\min_\phi\ \frac{1}{N}\sum_i\big\lVert \tilde x_i-g_\phi(\tilde x_i)\big\rVert_2^2,\qquad s_{\text{AE}}=\ln\!\Big(\tfrac{1}{58}\lVert \tilde x-g_\phi(\tilde x)\rVert_2^2+10^{-6}\Big)$$

où $g_\phi$ est le réseau, de paramètres $\phi$. Une opération qu'il reconstruit mal est inhabituelle : l'**erreur de reconstruction** $s_{\text{AE}}$ sert de score d'anomalie.

**LSTM avec attention.** Un réseau récurrent lit les 10 dernières opérations du client dans l'ordre, en gardant une mémoire. Le LSTM (*Long Short-Term Memory*, Hochreiter et Schmidhuber, 1997) contrôle cette mémoire par trois portes, d'oubli ($f_\tau$), d'entrée ($i_\tau$) et de sortie ($o_\tau$), ce qui évite que le début de la séquence soit oublié :

$$c_\tau=f_\tau\odot c_{\tau-1}+i_\tau\odot g_\tau,\qquad h_\tau=o_\tau\odot\tanh(c_\tau)$$

où $c_\tau$ est la mémoire, $h_\tau$ la sortie à l'étape $\tau$ et $\odot$ le produit terme à terme. Au lieu de ne garder que la dernière sortie, un mécanisme d'**attention** (Bahdanau et al., 2015) pondère toutes les étapes :

$$e_\tau=v^\top\tanh(W_a h_\tau+b_a),\qquad \alpha_\tau=\frac{e^{e_\tau}}{\sum_{\tau'}e^{e_{\tau'}}},\qquad c=\sum_\tau\alpha_\tau h_\tau$$

$e_\tau$ est un score d'importance de l'opération $\tau$ ; la fonction **softmax** le transforme en poids $\alpha_\tau$ positifs de somme 1 ; $c$ est un résumé pondéré de la séquence. Ces poids indiquent à l'analyste **quelles opérations passées** ont pesé dans la décision.

**Hybride : empilement.** Les scores des trois composantes, $s_k$ avec $k\in\{\text{XGB},\text{LSTM},\text{AE}\}$, sont standardisés ($z_k$), puis combinés par une régression logistique, le **méta-apprenant** (Wolpert, 1992), apprise sur la validation :

$$z_k=\frac{s_k-\mu_k}{\sigma_k},\qquad p=\sigma\Big(\beta_0+\sum_{k}\beta_k z_k\Big)$$

Le terme $\beta_k z_k$ mesure la **contribution de chaque composante**, affichée à l'analyste. Le méta-apprenant est appris sur la validation, que les composantes n'ont pas vue : appris sur l'entraînement, il ferait confiance aux composantes qui ont appris ces données par cœur.

**Seuil de décision.** Le modèle fournit une probabilité ; le seuil $\tau^*$ la transforme en décision. Il est choisi sur la validation pour maximiser le F1, jamais sur le test :

$$\tau^*=\mathrm{argmax}_\tau\ \frac{2\,P(\tau)\,R(\tau)}{P(\tau)+R(\tau)}$$

où $P(\tau)$ et $R(\tau)$ sont la précision et le rappel au seuil $\tau$.

#### 1.3 Second étage : la typologie

Un second modèle, XGBoost multiclasse (fonction *softmax*), est entraîné sur les seules fraudes. Sa sortie est restreinte aux typologies possibles pour le canal $c$ (un test de carte n'a pas de sens en Mobile Money), puis renormalisée :

$$\hat P(k\mid\tilde x,c)=\frac{P(k\mid\tilde x)\,\mathbb{1}[k\in\mathcal{K}_c]}{\sum_{k'\in\mathcal{K}_c}P(k'\mid\tilde x)},\qquad \hat k=\arg\max_k\hat P(k\mid\tilde x,c)$$

où $\mathcal{K}_c$ est l'ensemble des typologies possibles sur le canal $c$.

#### 1.4 Composants complémentaires du moteur de décision

Au modèle appris s'ajoutent cinq composants, qui renforcent la détection, l'explication et la décision.

**Décision coût-sensible.** Un seuil unique « fraude / pas fraude » ignore le montant en jeu. Le système choisit plutôt l'action dont le **coût attendu** est minimal. Pour une probabilité $p$ et un montant $m$ :

$$\mathbb{E}[\text{APPROVE}]=p\,m,\qquad \mathbb{E}[\text{VERIFY}]=c_f+p\,m(1-\kappa),\qquad \mathbb{E}[\text{BLOCK}]=(1-p)(c_b+\lambda m)$$

où $\mathbb{E}[\cdot]$ désigne l'espérance (le coût moyen attendu), $c_f$ le coût d'une vérification (friction), $\kappa$ la part des fraudes stoppées par la vérification, $c_b$ le coût fixe d'un client honnête bloqué et $\lambda$ la part du montant perdue lors d'un blocage à tort. Approuver coûte le montant si c'est une fraude ; vérifier coûte la friction à coup sûr, plus le montant si la fraude passe malgré la vérification ; bloquer ne coûte que si le client était honnête. Par exemple, à probabilité égale ($p=0{,}30$), le système bloque une opération de 500 USD mais se contente de faire vérifier une opération de 10 USD, ce qu'un seuil unique ne sait pas faire (Elkan, 2001). Au-dessus de $p=0{,}97$ on bloque, en dessous de $0{,}01$ on approuve. Les règles métier ne peuvent ensuite que renforcer l'action.

**Lois physiques.** Un modèle appris ne connaît que les fraudes qu'il a vues. Les lois physiques ajoutent des contraintes que toute fraude, même inédite, doit respecter. La **cinématique** calcule la distance de grand cercle $d$ (formule de haversine, $R_\oplus=6\,371$ km) entre les chefs-lieux de deux provinces consécutives, puis la durée minimale du trajet par la route (80 km/h) ou par avion (800 km/h plus 2 h de formalités) :

$$t_{\min}(d)=\min\Big(\frac{d}{80},\ 2+\frac{d}{800}\Big),\qquad I=\max\Big(0,\ \frac{t_{\min}(d)}{\Delta t}-1\Big)$$

où $\Delta t$ est le temps écoulé depuis l'opération précédente. L'**infaisabilité** $I$ vaut 0 si le trajet est possible ; $I\ge1$ signifie que le client aurait dû aller au moins deux fois plus vite que le moyen le plus rapide, ce qui est une violation nette. Exemple : Kinshasa-Lubumbashi représente 1 568 km, soit 3,96 h au minimum ; deux opérations espacées de 30 minutes donnent $I=6{,}9$. La **conservation** interdit qu'un débit dépasse le solde.

**Explication.** Chaque décision est accompagnée de ses explications. Les **valeurs de Shapley** répartissent le score d'une opération entre les variables, comme on répartirait un gain entre les joueurs d'une équipe (Lundberg et Lee, 2017) : $F(\tilde x)=\phi_0+\sum_{j=1}^{58}\phi_j$, où $\phi_0$ est le score moyen et $\phi_j$ la contribution de la variable $j$. L'algorithme **TreeSHAP** les calcule exactement pour les arbres (Lundberg et al., 2020). S'y ajoutent les contributions des composantes ($\beta_k z_k$) et les poids d'attention.

**Cas similaires et procédures (RAG sans modèle de langage).** Les opérations passées les plus proches dans l'espace des variables (k plus proches voisins) sont retrouvées avec leur proportion de fraudes. Un indicateur de cohérence les compare à la décision du modèle : si les cas proches la contredisent, une revue attentive est conseillée. Les passages pertinents d'une base de procédures par type de fraude sont retrouvés par **TF-IDF** (*Term Frequency – Inverse Document Frequency*), pondération forte pour un mot fréquent dans un document et rare dans les autres. Aucun modèle de langage externe n'est utilisé : les preuves viennent uniquement de sources vérifiables et aucune donnée ne quitte la plateforme.

**Analyse du message.** Le score d'ingénierie sociale d'un message de transfert est un **OU probabiliste** (*noisy-OR*) des catégories d'indices détectées $\mathcal{C}$ (urgence, gain, faux agent), de poids $w_c$ :

$$S_{\text{IS}}=1-\prod_{c\in\mathcal{C}}(1-w_c)$$

C'est la probabilité qu'au moins un indice soit réellement révélateur. Deux indices de poids 0,5 donnent $1-0{,}5\times0{,}5=0{,}75$. Le texte seul impose une vérification, jamais un blocage (RG-10), et n'est jamais stocké en clair.

**Analyse de réseau.** Le score transaction par transaction ne voit pas les réseaux de mules. Un **graphe biparti** relie les comptes clients aux entités qu'ils utilisent : portefeuille destinataire, appareil, agent, marchand (Akoglu et al., 2015). Chaque transaction pèse par le verdict de l'analyste s'il existe, sinon par la probabilité du modèle. Trois scores interprétables en découlent. Le **risque direct** d'une entité $e$ est sa part de fraude lissée vers le taux global $\bar p$ :

$$r_e=\frac{S_e+m\,\bar p}{K_e+m},\qquad m=4$$

où $S_e$ est la suspicion cumulée des transactions de l'entité, $K_e$ leur nombre et $m$ le poids de l'a priori (une seule fraude ne condamne pas une entité très utilisée). L'**exposition** d'un compte $u$ combine l'excès de risque de ses entités $\mathcal{E}(u)$ au-dessus du taux global :

$$E_u=1-\prod_{e\in\mathcal{E}(u)}\left(1-\frac{\max(r_e-\bar p,\,0)}{1-\bar p}\right)$$

Enfin, le **risque propagé** d'une entité partagée par au moins deux comptes est l'exposition moyenne de ces comptes, entité exclue, et le score final est $R_e=1-(1-r_e)(1-\alpha\,q_e)$ avec $\alpha=0{,}5$, où $q_e$ est ce risque propagé. Les **réseaux** sont les composantes connexes des comptes reliés par des entités partagées dont le risque direct dépasse 0,30.

### 2. Justification des choix

#### 2.1 Critères de choix

Les critères ont été fixés **avant** l'expérimentation, à partir des besoins de la section 1. Chacun reçoit un poids qui traduit son importance pour le métier (tableau II.26).

*Tableau II.26 — Critères de choix et pondération.*

| Critère | Poids | Mesure | Besoin lié |
|---|---|---|---|
| Performance de détection | 30 % | PR-AUC sur le test | BM-01, BM-02 |
| Qualité au seuil opérationnel | 20 % | F1, fausses alertes, fraudes manquées | BM-04 |
| Explicabilité | 15 % | Possibilité d'expliquer chaque décision à l'analyste et au régulateur | BM-06, BT-14 |
| Temps réel et simplicité | 15 % | Latence d'inférence, coût d'entraînement et de maintenance | BT-01 |
| Prise en compte de la dynamique | 10 % | Capacité à lire la séquence des opérations | BM-02 |
| Détection de fraudes inédites | 10 % | Capacité à signaler un comportement jamais vu, sans étiquette | BM-15, BM-16, BT-19 |

La performance de détection pèse le plus, car c'est la raison d'être du système. Mais un modèle très performant, impossible à expliquer ou trop lent pour décider avant l'exécution, ne serait pas utilisable en RDC, sous le contrôle de la BCC. Chaque méthode reçoit une note de 1 à 5 par critère ; la matrice complète est présentée au chapitre III, une fois les performances mesurées.

#### 2.2 Justification de chaque choix

Chaque choix de conception répond à une raison métier ou à un résultat établi (tableau II.27).

*Tableau II.27 — Justification des choix.*

| Choix | Raison | Appui |
|---|---|---|
| Arbres boostés (XGBoost) pour les variables tabulaires | Les modèles à base d'arbres restent les plus performants sur données tabulaires de taille moyenne, et TreeSHAP donne une explication exacte | Grinsztajn et al. (2022) ; Chen et Guestrin (2016) ; Lundberg et al. (2020) |
| LSTM avec attention pour la séquence | Capte l'escalade et les salves d'opérations ; l'attention désigne les opérations passées décisives. Les modèles de séquence apportent un gain surtout sur les opérations en présence de la carte, moins sur les paiements à distance | Hochreiter et Schmidhuber (1997) ; Bahdanau et al. (2015) ; Jurgovsky et al. (2018) |
| Autoencodeur pour l'inédit | Apprend sans étiquette de fraude et signale un comportement jamais vu ; combiner supervisé et non supervisé améliore la détection quand les fraudes évoluent | Hinton et Salakhutdinov (2006) ; Carcillo et al. (2019) |
| Empilement par régression logistique | Combine des modèles de nature différente par un méta-apprenant simple, interprétable, appris sur des données que les composantes n'ont pas vues | Wolpert (1992) |
| Variables d'écart au profil et horaires cycliques | Une fraude est une rupture d'habitude ; des variables agrégées par client et des variables périodiques pour l'heure améliorent la détection de fraude par carte | Bahnsen et al. (2016) |
| Découpage chronologique | Le comportement évolue : l'évaluation doit apprendre sur le passé et tester sur l'avenir, comme en production | Dal Pozzolo et al. (2014) |
| Décision selon le coût attendu | Les erreurs n'ont pas le même coût ; l'action doit minimiser la perte attendue, avec un montant en jeu | Elkan (2001) |
| Lois physiques | Contraintes valables même pour une fraude inédite, indépendantes de l'apprentissage | Connaissance du domaine |
| PR-AUC comme métrique principale | Sur classes très déséquilibrées, la courbe précision-rappel est plus informative que la courbe ROC | Davis et Goadrich (2006) ; Saito et Rehmsmeier (2015) |
| Analyse de réseau | Les mules et les appareils réutilisés ne se voient qu'en reliant les comptes | Akoglu et al. (2015) |
| Explication sans modèle de langage externe | Confidentialité, absence de dépendance en ligne, aucune invention de texte | Contraintes BT-23 |

Deux points méritent d'être précisés. Pour compenser le déséquilibre, une partie des opérations légitimes est sous-échantillonnée à l'apprentissage du LSTM. Or le sous-échantillonnage modifie les probabilités a priori et fausse les probabilités prédites, sans changer le classement des opérations (Dal Pozzolo et al., 2015). Le travail en tient compte : la décision repose sur un seuil, et la calibration est mesurée au chapitre III. Par ailleurs, l'avantage des arbres sur les réseaux de neurones est établi surtout sur des jeux de taille moyenne ; il n'est pas garanti sur des jeux plus grands ou plus structurés par une séquence. C'est précisément la raison d'évaluer un modèle séquentiel et un modèle hybride plutôt que de les écarter par principe.

### 3. Paramètres et configuration

Tous les paramètres sont fixés par défaut dans le code et surchargeables sans modification, par variables d'environnement. Les graines aléatoires sont figées à 42 pour la reproductibilité.

*Tableau II.28 — Hyperparamètres des modèles.*

| Modèle | Paramètre | Valeur |
|---|---|---|
| XGBoost | nombre d'arbres (maximum) | 600, avec arrêt précoce après 50 itérations sans gain de PR-AUC |
| | profondeur maximale | 6 |
| | taux d'apprentissage | 0,05 |
| | échantillonnage des lignes et des colonnes | 0,8 et 0,8 |
| | poids minimal d'une feuille | 3 |
| | poids des fraudes | $N^-/N^+$ (≈ 74) |
| LSTM avec attention | entrée, couches cachées | 58 variables, 2 couches de 64 neurones |
| | séquence | 10 dernières opérations du client |
| | *dropout* | 0,2 |
| | optimiseur | AdamW, taux 0,001, régularisation L2 de 0,01 |
| | lot, époques, patience | 512, 8 au maximum, 2 |
| | opérations légitimes conservées par époque | 30 % |
| Autoencodeur | architecture | 58, 32, 16, 8, 16, 32, 58 (activation ReLU) |
| | lot, taux d'apprentissage, patience | 1 024, 0,001, 3 ; 30 époques au maximum |
| | données d'entraînement | opérations légitimes seulement |
| Méta-apprenant | modèle | régression logistique ($C=1$) sur scores standardisés |
| | données d'apprentissage | validation |
| Seuil | $\tau^*$ | 0,538 (F1 maximal sur la validation) |
| Régression logistique | $C$, classes | 0,5 ; pondération équilibrée |
| Random Forest | arbres, feuille minimale | 200 ; 5 (pondération équilibrée par échantillon) |
| Isolation Forest | arbres, échantillon | 200 ; 4 096 |
| Typologie (XGBoost multiclasse) | arbres, profondeur, taux | 400 ; 5 ; 0,05 |

*Tableau II.29 — Paramètres de décision, de détection et d'apprentissage continu.*

| Composant | Paramètre | Valeur |
|---|---|---|
| Décision (Mobile Money) | $c_f$, $\kappa$, $c_b$, $\lambda$ | 0,30 USD ; 0,85 ; 4,00 USD ; 0,05 |
| Décision (Visa virtuelle) | $c_f$, $\kappa$, $c_b$, $\lambda$ | 0,15 USD ; 0,90 ; 6,00 USD ; 0,05 |
| Décision | blocage direct, approbation directe | $p\ge0{,}97$ ; $p<0{,}01$ |
| Niveaux de risque | CRITIQUE, ÉLEVÉ, MOYEN | $p\ge\max(0{,}9;\tau^*)$ ; $p\ge\tau^*$ ; $p\ge\tau^*/5$ |
| Lois physiques | vitesses route, avion, formalités | 80 km/h ; 800 km/h ; 2 h |
| | violation nette | $I\ge1$ (mode « enforce » : vérification imposée) |
| Cas similaires | voisins, similarité minimale | $k=7$ ; 0,2 (choisis sur la validation) |
| Réseau | a priori, poids du risque propagé, seuil de réseau | $m=4$ ; $\alpha=0{,}5$ ; 0,30 |
| Dérive | écart KS, p-valeur, PSI | $D>0{,}1$ et $p<0{,}01$ ; PSI $>0{,}2$ |
| Nouveauté | centile de référence, taux d'alarme | 99ᵉ ; 4 % (1 % attendu) |
| Réentraînement | étiquettes minimales, fraudes minimales | 2 000 ; 30 |
| | nouvelles étiquettes, nouvelles transactions | 500 ; 20 000 |
| | délai de carence, âge maximal, vérification | 6 h ; 168 h ; toutes les 10 min |
| | maturité d'une étiquette supposée | 7 jours |
| | poids d'un verdict vérifié | 3 |
| | écart de PR-AUC bloquant (surapprentissage) | 0,05 |
| Garde-fou de détection | PR-AUC, rappel à 1 % de faux positifs, faux positifs | $\ge0{,}975$ ; $\ge0{,}98$ ; $\le0{,}2$ % |
| Sécurité | échecs avant verrouillage, durée, seuil des quatre yeux | 5 ; 15 min ; 500 USD |

### 4. Évaluation des performances

Évaluer la performance d'un système de détection de fraude ne se réduit pas à un score de classification. Le système doit détecter, mais aussi décider à un coût acceptable, rester rapide, expliquer, évoluer et traiter équitablement les clients. Douze dimensions sont donc évaluées (tableau II.30).

*Tableau II.30 — Dimensions de l'évaluation.*

| Dimension | Question posée | Mesure principale | Hypothèse ou besoin |
|---|---|---|---|
| Détection globale | Le modèle sépare-t-il fraudes et opérations légitimes ? | PR-AUC, ROC-AUC, intervalles de confiance | H1, H3 |
| Qualité opérationnelle | Que donne le modèle au seuil retenu ? | précision, rappel, F1, F2, MCC, fausses alertes, fraudes manquées | BM-04 |
| Budget d'alertes | Combien de fraudes arrête-t-on avec un nombre d'alertes limité ? | rappel à 0,05 %, 0,1 %, 0,5 % et 1 % de faux positifs | BM-04 |
| Typologies | Quelles fraudes sont difficiles ? | rappel par typologie, matrices de confusion | BM-05 |
| Apport des variables et des composantes | Chaque famille de variables et chaque composante est-elle utile ? | ablation, ajout, AUC univariée | H2 |
| Transposabilité | La logique se transpose-t-elle à la carte Visa ? | PR-AUC Visa sans donnée Visa, rapport de transfert | H4 |
| Évolution | Faut-il réentraîner ? | PR-AUC par année, modèle figé contre modèle mis à jour | H5 |
| Robustesse | Le modèle résiste-t-il à une attaque inédite ? | rappel sur une attaque injectée, lois physiques | BT-19 |
| Coût | La décision graduée réduit-elle la perte ? | perte attendue et réalisée, comparaison à un seuil unique | BM-03 |
| Explication et preuves | Les explications aident-elles ? | précision des alertes selon l'avis des cas proches, exactitude de l'analyse de texte | BM-06, BM-10 |
| Boucle de retour et réseaux | Revoir les bons cas et relier les comptes améliore-t-il la détection ? | fraudes manquées, rappel et précision des entités à risque | BM-22, BM-23 |
| Temps réel et équité | Le système tient-il le délai ? Les erreurs sont-elles réparties équitablement ? | latence médiane et au 95ᵉ centile ; taux de fausses alertes par groupe | BT-01, BM-25 |

### 5. Métriques utilisées

#### 5.1 Matrice de confusion et métriques de classification

On note $VP$ les vrais positifs (fraudes détectées), $FP$ les faux positifs (fausses alertes), $FN$ les faux négatifs (fraudes manquées) et $VN$ les vrais négatifs. Le tableau II.31 définit les métriques employées.

*Tableau II.31 — Métriques d'évaluation.*

| Métrique | Définition | Lecture métier |
|---|---|---|
| Précision | $VP/(VP+FP)$ | part des alertes justifiées |
| Rappel (sensibilité) | $VP/(VP+FN)$ | part des fraudes interceptées |
| Spécificité | $VN/(VN+FP)$ | part des opérations légitimes laissées passer |
| Taux de faux positifs | $FP/(FP+VN)$ | clients honnêtes dérangés |
| F1 | $2PR/(P+R)$ | compromis précision / rappel (moyenne harmonique : elle s'effondre si l'une des deux est faible) |
| F2 | $5PR/(4P+R)$ | compromis qui donne deux fois plus de poids au rappel, car manquer une fraude coûte plus cher |
| MCC | voir ci-dessous | corrélation entre prédiction et réalité, de $-1$ à $+1$ |
| Exactitude équilibrée | (rappel + spécificité) / 2 | neutralise le poids écrasant des légitimes |
| Kappa de Cohen | accord corrigé de l'accord dû au hasard | 0 : pas mieux que le hasard ; 1 : accord parfait |
| Score de Brier | $\frac1n\sum_i(\hat p_i-y_i)^2$ | qualité des probabilités prédites (Brier, 1950) |
| Rappel à $x$ % de faux positifs | rappel maximal quand le taux de faux positifs est plafonné à $x$ % | performance à budget d'alertes fixé |

Le **coefficient de corrélation de Matthews** utilise les quatre cases de la matrice de confusion et reste fiable quand les classes sont très déséquilibrées (Chicco et Jurman, 2020) :

$$MCC = \frac{VP \cdot VN - FP \cdot FN}{\sqrt{(VP+FP)(VP+FN)(VN+FP)(VN+FN)}}$$

#### 5.2 Courbes et métrique principale

La **courbe ROC** trace le taux de vrais positifs en fonction du taux de faux positifs pour tous les seuils ; la **ROC-AUC** est l'aire sous cette courbe. La **courbe précision-rappel** trace la précision en fonction du rappel ; la **PR-AUC** (précision moyenne) en est l'aire :

$$\text{PR-AUC}=\sum_n (R_n-R_{n-1})\,P_n$$

c'est-à-dire la précision moyenne, pondérée par chaque gain de rappel quand on abaisse le seuil. Avec 1,33 % de fraudes, la courbe ROC est trompeuse : les fausses alertes se divisent par des centaines de milliers d'opérations légitimes, et son aire reste élevée même quand le modèle produit beaucoup de fausses alertes. La précision compare au contraire les fausses alertes aux vraies fraudes et chute immédiatement. La **PR-AUC est donc la métrique principale** (Davis et Goadrich, 2006 ; Saito et Rehmsmeier, 2015). Sa valeur de base, pour un modèle aléatoire, est la prévalence (environ 0,013), alors que celle de la ROC-AUC est 0,5. Le seuil de décision est choisi sur la validation, jamais sur le test.

#### 5.3 Métriques de coût, d'équité et de surveillance

**Perte attendue et perte réalisée.** Pour un ensemble d'opérations et une politique de décision, la **perte attendue** somme les coûts attendus de l'action choisie (formules du § 1.4) d'après les probabilités du modèle, sur toutes les opérations. La **perte réalisée** somme les coûts effectifs d'après les étiquettes, sur les seules opérations étiquetées : montant perdu pour une fraude approuvée, friction pour une vérification, coût d'un blocage pour un client honnête.

**Intervalle de confiance de Wilson.** Pour une proportion observée $\hat p=k/n$, l'intervalle à 95 % est :

$$\frac{\hat p+\frac{z^2}{2n}\pm z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}}{1+\frac{z^2}{n}},\qquad z=1{,}96$$

Il reste fiable pour de petits effectifs et des proportions proches de 0, ce qui est le cas des fausses alertes et des fraudes manquées (Wilson, 1927).

**Équité.** Pour un groupe $g$ de clients (province, opérateur, canal d'accès, niveau KYC, segment, tranche de revenu), on calcule son taux de fausses alertes $\mathrm{FPR}_g$ et son rappel, chacun avec son intervalle de Wilson. Le **rapport d'écart** est $\rho_g=\mathrm{FPR}_g/\mathrm{FPR}_{\text{global}}$. Un groupe est **signalé** si $\rho_g\ge1{,}25$ et si la borne basse de l'intervalle de $\mathrm{FPR}_g$ dépasse le taux global (écart non dû au hasard), ou si la borne haute de son rappel est sous le rappel global. Les groupes de moins de 200 opérations légitimes sont affichés sans être jugés. Cette mesure s'inspire de l'égalité des chances (Hardt et al., 2016), qui demande des taux d'erreur comparables entre groupes.

**Surveillance de la dérive.** La statistique de **Kolmogorov-Smirnov** $D=\sup_x|F_{\text{réf}}(x)-F_{\text{prod}}(x)|$ mesure le plus grand écart entre les fonctions de répartition d'une variable en référence et en production. L'indice de stabilité de population (**PSI**) découpe la variable en classes, avec $r_k$ la part de la référence et $q_k$ la part de la production dans la classe $k$ :

$$\mathrm{PSI}=\sum_{k}(q_k-r_k)\,\ln\frac{q_k}{r_k}$$

Les seuils usuels sont : PSI inférieur à 0,1, stable ; entre 0,1 et 0,2, à surveiller ; supérieur à 0,2, dérive (Gama et al., 2014, pour la notion de dérive). Exemple : une référence répartie à 25 % dans quatre classes et une production à 10, 20, 30 et 40 % donnent $\mathrm{PSI}=0{,}228$ : dérive. Le **taux de nouveauté** est la part des opérations dont l'erreur de reconstruction de l'autoencodeur dépasse le 99ᵉ centile de référence ; il vaut 1 % si rien ne change, et l'alarme se déclenche à 4 %.

**Temps réel.** La latence est mesurée de bout en bout sur un rejeu de flux. On rapporte la **médiane** et le **95ᵉ centile** (95 % des requêtes sont plus rapides que cette valeur), qui est plus exigeant que la moyenne et ne cache pas les requêtes lentes.

### 6. Protocole d'évaluation

#### 6.1 Principes généraux

Le protocole obéit à six règles, qui s'appliquent à toutes les évaluations.

1. **Découpage chronologique** (tableau II.23). Le test, du 13/12/2024 au 31/12/2025, est postérieur à tout ce qui a servi à apprendre.
2. **Seuil choisi sur la validation**, jamais sur le test.
3. **Mêmes données, mêmes variables, même test** pour toutes les méthodes comparées.
4. **Intervalles de confiance par bootstrap apparié par usager.** On tire avec remise 1 000 fois les **clients**, et non les transactions, car les opérations d'un même client sont corrélées (Efron, 1979). Les deux modèles comparés sont évalués sur le même rééchantillon, ce qui donne directement la distribution de leur écart. L'intervalle de confiance à 95 % est borné par les 2,5ᵉ et 97,5ᵉ centiles. Une différence est **significative** si l'intervalle de confiance de l'écart exclut 0.
5. **Test de McNemar exact** (McNemar, 1947 ; Dietterich, 1998). On ne considère que les opérations où deux modèles ne sont pas d'accord : $b$ opérations où seul le premier a raison, $c$ où seul le second a raison. Si les modèles se valaient, chacun aurait raison une fois sur deux, et :

$$X\sim\mathcal{B}\big(b+c,\ \tfrac12\big),\qquad p=\min\Big(1,\ 2\,P\big(X\le\min(b,c)\big)\Big)$$

où $\mathcal{B}(n,\frac12)$ est la loi binomiale (nombre de « pile » en $n$ lancers d'une pièce équilibrée). La **p-valeur** est la probabilité d'observer un écart au moins aussi grand si les modèles étaient équivalents ; on rejette l'équivalence si $p<0{,}05$.
6. **Variance selon la graine.** Les entraînements sont répétés avec plusieurs graines ; un écart du même ordre que l'écart-type d'une graine à l'autre est du bruit d'entraînement.

#### 6.2 Protocole par hypothèse

*Tableau II.32 — Protocole expérimental par hypothèse.*

| Hyp. | Expérience | Critère de confirmation |
|---|---|---|
| H1 | Modèle de profilage (toutes variables) contre modèle statique appris (sans historique du client) et règles métier | écart de PR-AUC significatif ; McNemar $p<0{,}05$ |
| H2 | Ablation (retrait de chaque famille de variables), ajout (socle + une famille), AUC univariées | retrait dégradant significativement, ou ajout améliorant nettement (plus de 0,005 de PR-AUC) |
| H3 | Comparaison XGBoost, Random Forest, régression logistique, Isolation Forest, règles ; composantes et hybride | écarts significatifs entre familles |
| H4 | Entraînement sur le Mobile Money seul puis évaluation sur Visa ; variantes avec 5 % et 20 % de données Visa ; sens inverse | PR-AUC élevée sur Visa sans données Visa |
| H5 | Modèle figé (entraîné sur 2019-2021) contre modèle mis à jour (cumulatif, ou glissant sur 3 ans), évalués chaque année de 2022 à 2025 | modèle mis à jour significativement meilleur, écart croissant avec le temps |

Pour H4, le **rapport de transfert** est $\text{PR-AUC}_{\text{Visa}}(\text{modèle Mobile Money seul})/\text{PR-AUC}_{\text{Visa}}(\text{modèle mixte})$, interprété comme fort s'il atteint 0,9, partiel entre 0,6 et 0,9, faible en dessous. Le **gain sur le hasard** est la PR-AUC divisée par la prévalence. Pour H5, on calcule pour chaque année l'écart $\Delta_Y=\text{PR-AUC}_Y(\text{réentraîné})-\text{PR-AUC}_Y(\text{figé})$, puis la pente de la droite des moindres carrés $\Delta_Y=\alpha+\beta Y$ : $\beta>0$ signifie que l'écart se creuse.

#### 6.3 Protocoles des évaluations complémentaires

*Tableau II.33 — Protocoles des évaluations complémentaires.*

| Évaluation | Protocole | Précautions |
|---|---|---|
| Choix du modèle (comparaison de 8 méthodes) | Mêmes données et mêmes variables ; métriques complètes ; bootstrap et McNemar ; ablation ; analyse par typologie ; matrice multicritère testée avec des poids égaux et 2 000 pondérations aléatoires | Contrôle de reproductibilité : les métriques recalculées sont identiques à la quatrième décimale |
| Robustesse physique | Injection de 300 attaques « session relayée » : appareil, type et montant habituels de la victime, mais depuis une province éloignée, quelques minutes après une opération légitime | Scénario construit par l'équipe, jamais vu à l'entraînement ; fausses alertes mesurées sur les vraies opérations légitimes |
| Cas similaires (RAG) | Index de 64 003 cas d'entraînement ; $k$ et la similarité minimale choisis sur la validation ; précision des alertes selon l'avis des cas proches | Évaluation sur le test |
| Analyse de texte | Corpus de développement (50 messages) et corpus de test (61 messages), annotés ; précision, rappel et F1 de l'ingénierie sociale, exactitude du sentiment | Intervalle de confiance du F1 par bootstrap |
| Analyse de réseau | Rejeu chronologique : avant la validation, toutes les transactions sont ajoutées avec leur étiquette ; ensuite, chaque transaction reçoit le score réseau calculé sur l'instantané de la veille (recalculé une fois par jour), puis son verdict n'est révélé qu'après 7 jours ; seuil réseau choisi sur la validation pour 0,5 % de fausses alertes supplémentaires ; règle « modèle OU réseau » | Aucune fuite temporelle ; variante sans aucune étiquette (scores du modèle seuls) |
| Boucle de retour | Rejeu mensuel de 13 mois du test, avec XGBoost seul : à chaque mois, le modèle score, puis les étiquettes sont révélées (alertes, revues ciblées, plaintes pour 30 % des fraudes manquées, le reste supposé légitime), puis le modèle est réentraîné ; cinq stratégies à budget égal de 200 revues par mois | Mesures sur le mois suivant, avant ses étiquettes ; modèle initial identique pour toutes les stratégies |
| Politique de décision | Réglage des paramètres de coût sur la première moitié chronologique du test, mesure sur la seconde ; quatre politiques jugées avec les mêmes coûts métier | Coûts métier = hypothèses de simulation |
| Équité | Taux de fausses alertes et rappel par groupe, intervalles de Wilson, règle de signalement | Données simulées : à refaire sur données réelles |
| Temps réel | Rejeu d'un flux d'opérations vers l'API d'intégration à débit contrôlé ; latence de bout en bout | Mesure dans l'environnement de démonstration |
| Robustesse adversariale (prévue) | Réécriture des épisodes de fraude selon quatre stratégies (fractionnement, mimétisme, étalement dans le temps, combinaison) et rescoring avec les variables recalculées | Protocole écrit, résultats à produire |

#### 6.4 Menaces sur la validité

Une étude doit dire ce qui pourrait fausser ses conclusions (tableau II.34). La **validité interne** demande si le résultat vient bien de ce qu'on croit ; la **validité externe**, s'il se généralise au monde réel ; la **validité de construit**, si l'on mesure bien ce qu'on prétend mesurer ; la **validité statistique**, si les conclusions statistiques sont correctes.

*Tableau II.34 — Menaces sur la validité.*

| Menace | Nature | Mesure prise ou réserve |
|---|---|---|
| **Données simulées** | Validité externe | Les fraudes simulées sont plus nettes que les vraies : les performances réelles seront plus faibles. Une validation sur données réelles est prévue. |
| Circularité de H5 | Validité interne | L'évolution des fraudes est un paramètre du générateur : H5 démontre surtout que le mécanisme de mise à jour fonctionne. |
| Canal Visa trop séparable | Validité de construit | Effet plafond possible : la transposabilité (H4) peut être surestimée. |
| Réutilisation d'un nombre fini d'appareils et de mules | Validité de construit | Le générateur réutilise 150 appareils de fraudeurs et 400 portefeuilles mules ; les variables de partage et l'analyse de réseau en profitent. À confirmer sur données réelles. |
| Faible nombre de clients | Validité statistique | 500 clients : les intervalles par usager reposent sur 500 unités. |
| Fuite d'information | Validité interne | Variables calculées sur le passé, découpage temporel, seuil choisi sur la validation. |
| Corrélation intra-client | Validité statistique | Bootstrap par usager plutôt que par transaction. |
| Surapprentissage | Validité interne | Arrêt précoce, régularisation, diagnostic automatique. |
| Verdicts supposés exacts dans les rejeux | Validité externe | Les rejeux de la boucle de retour supposent des analystes sans erreur et un taux de plainte fixe. |
| Corpus de messages construit par l'auteur | Validité externe | Messages en français seulement ; lingala et swahili non couverts. |
| Étiquettes réelles imparfaites | Validité externe | Fraudes non signalées, délai d'étiquetage ; la file de revue et l'échantillon témoin visent à les mesurer. |
| Coûts métier fixés par hypothèse | Validité externe | Paramètres de coût à remplacer par ceux de chaque opérateur. |

Pour passer du prototype à un usage réel, la démarche de validation comporte cinq étapes : accord de données anonymisées avec un opérateur ; validation hors ligne sur son historique, avec le même protocole ; **mode observation** de deux à quatre semaines, le système notant les opérations sans rien bloquer ; recalibrage des seuils et des coûts ; mise en service progressive, d'abord en vérification seule, puis en blocage des cas critiques.

#### 6.5 Reproductibilité

Chaque résultat du mémoire est produit par une commande du projet, qui écrit un rapport et ses figures dans `ml/reports/` (tableau II.35).

*Tableau II.35 — Commandes de reproduction.*

| Étape | Commande |
|---|---|
| Génération des données | `python ml/generator/generate_synthetic_data.py --multi-year` |
| Variables, entraînement, typologie | `scripts/run_pipeline.ps1` (variables, `ml.training.train_model`, `ml.training.train_fraud_type`) |
| Analyse exploratoire | `python -m ml.eda.exploratory_analysis` |
| Choix du modèle et métriques complètes | `python -m ml.training.model_selection`, `python -m ml.training.figures_comparaison` |
| Hypothèses H1 à H4, puis H5 | `python -m ml.training.research_evaluation`, `python -m ml.training.h5_temporal` |
| Lois physiques, cas similaires, texte | `python -m ml.physics.evaluate_physics`, `python -m ml.rag.evaluate_rag`, `python -m ml.nlp.evaluate_nlp` |
| Réseaux, boucle de retour, politique, équité | `python -m ml.graph.evaluate_graph`, `python -m ml.retraining.evaluate_feedback`, `python -m ml.serving.evaluate_policy`, `python -m ml.robustness.evaluate_fairness` |
| Garde-fou de non-régression | `python -m ml.training.detection_gate` |

<!-- CONCLUSION -->
Ce chapitre a d'abord analysé le métier de la lutte contre la fraude Mobile Money en RDC. L'étude de l'existant a montré qu'un contrôle fondé sur des règles statiques ignore l'individu, se laisse contourner, intervient trop tard, ne gradue pas sa réponse et n'explique pas ses décisions. De cette critique sont nés vingt-trois règles de gestion, vingt-six besoins fonctionnels et une vingtaine de besoins non fonctionnels, priorisés et reliés aux cinq hypothèses de recherche.

Il a ensuite décrit les données : un jeu synthétique de 631 968 transactions sur sept ans, reproductible et confronté aux statistiques officielles, complété en exploitation par un flux collecté par une API ouverte aux institutions et par plusieurs sources d'étiquettes, dont un échantillon témoin aléatoire qui permet de mesurer ce que le modèle laisse passer. Ces données sont préparées sans fuite d'information : 58 variables calculées sur le seul passé du client, normalisation estimée sur l'entraînement, découpage chronologique.

La méthodologie enfin justifie le choix d'un modèle hybride (XGBoost, LSTM avec attention, autoencodeur), complété par une décision selon le coût, des lois physiques, une explication de chaque décision et une analyse de réseau. Elle fixe les paramètres, les métriques, avec la PR-AUC comme métrique principale, et un protocole qui impose un test postérieur à l'apprentissage, un seuil choisi sur la validation et des tests statistiques adaptés (bootstrap par client, test de McNemar). Le chapitre suivant présente les résultats obtenus en appliquant ce protocole, puis l'implémentation du système.
