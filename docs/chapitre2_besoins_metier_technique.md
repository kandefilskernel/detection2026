# Chapitre II — Analyse des besoins métiers et techniques

> Proposition de contenu pour le chapitre II. Chaque besoin est relié à sa justification (contexte RDC, problématique)
> et à la réponse apportée par le système, avec un indicateur vérifiable. Les valeurs mesurées proviennent des rapports
> du dépôt (`ml/reports/`) et portent sur des **données simulées**.

---

## II.1 Contexte et acteurs

### II.1.1 Contexte métier

Le Mobile Money est en RDC un moyen de paiement de masse : transferts entre particuliers, dépôts et retraits chez des
agents, paiements marchands, achat de crédit, factures. Il fonctionne sur smartphone (application) mais aussi sur
téléphone simple (USSD), en francs congolais (CDF) et en dollars (USD). Les cartes Visa virtuelles, rechargées depuis le
portefeuille, ouvrent l'accès aux achats en ligne et à l'international. Ces deux canaux attirent des fraudes variées
(échange de SIM, ingénierie sociale, prise de contrôle de compte, fraude d'agent, fractionnement, test de carte, fraude
carte non présente, vidage par rechargement) qui évoluent dans le temps.

### II.1.2 Acteurs

| Acteur | Rôle | Attentes principales |
|---|---|---|
| Client (titulaire) | Effectue les opérations | Être protégé sans être bloqué à tort ; être prévenu en cas d'opération suspecte |
| Opérateur (Vodacom, Airtel, Orange) et émetteur Visa | Transmet les opérations, exécute la décision | Décision rapide, fiable, au format de son système |
| Analyste anti-fraude | Traite les alertes et les dossiers | Alertes priorisées et expliquées, outils d'enquête |
| Superviseur | Encadre l'équipe, suit le modèle | Indicateurs, journal d'audit, déclenchement du réentraînement |
| Administrateur | Gère les comptes et les droits | Gestion des utilisateurs et des rôles |
| Régulateur (BCC) et auditeur | Contrôle la conformité | Traçabilité complète et inaltérable des décisions |
| Équipe données (data scientist) | Entretient le modèle | Données étiquetées, suivi de la dérive, réentraînement maîtrisé |

---

## II.2 Besoins métiers (fonctionnels)

| Réf. | Besoin | Justification | Réponse du système | Indicateur |
|---|---|---|---|---|
| **BM-01** | Détecter la fraude **avant** l'exécution de l'opération | Une fraude stoppée après exécution est souvent irrécupérable | Score de chaque opération en temps réel par le modèle hybride | Rejeu : 278 fraudes interceptées sur 279 ; pertes avant alerte quasi nulles |
| **BM-02** | Reconnaître le **comportement habituel** de chaque client et ses écarts | Cœur de la problématique : la fraude se manifeste par une rupture d'habitude | 58 variables de profilage (montant habituel, fréquence, appareil, lieu, destinataire, horaires) | H1 : PR-AUC 0,989 contre 0,753 sans historique |
| **BM-03** | **Graduer la réponse** : laisser passer, faire vérifier, bloquer | Bloquer 2 USD de crédit ou 900 USD de retrait n'a pas le même coût | Décision coût-sensible (probabilité × montant), règles métier prioritaires | 0,4 % d'opérations légitimes soumises à vérification au rejeu |
| **BM-04** | Limiter les **fausses alertes** | Chaque blocage à tort coûte un client et un appel | Seuil optimisé, vérification plutôt que blocage dans les cas intermédiaires | 0,067 % de faux positifs sur le test |
| **BM-05** | Identifier le **type de fraude** | Chaque type appelle une procédure différente | Classifieur de typologie (8 types), affiché sur chaque alerte | Exactitude 96 % sur les fraudes du test |
| **BM-06** | **Expliquer** chaque décision | L'analyste doit comprendre ; le client et le régulateur peuvent contester | Contributions SHAP, part de chaque branche, attention sur l'historique, cas passés similaires (RAG) | Alerte confirmée par les cas proches : 98 % de vraies fraudes |
| **BM-07** | **Prioriser et traiter** les alertes | Le volume d'alertes dépasse la capacité d'une équipe | Dossiers classés par niveau de risque et montant ; statuts ; affectation ; note obligatoire | Workflow ouvert → en cours → fraude confirmée / faux positif |
| **BM-08** | **Prévenir le client** | Une opération suspecte doit être confirmée par son titulaire | SMS (confirmation par PIN, blocage), e-mail à l'équipe pour les cas critiques, webhook vers l'opérateur | Notification journalisée pour chaque dossier |
| **BM-09** | Enregistrer les **plaintes** des clients | Seule source des fraudes que le modèle a laissé passer | Plainte → dossier « fraude confirmée » → étiquette ; analyse du texte de la plainte | Typologie déduite si la plainte décrit une manipulation |
| **BM-10** | Repérer l'**ingénierie sociale** | Fraude la plus difficile : la victime paie elle-même | Profilage des écarts, analyse des messages (indices de manipulation), règle de vérification | Rappel 92 % (test) ; 97,6 à 100 % des épisodes détectés au rejeu |
| **BM-11** | Couvrir **plusieurs opérateurs et la carte Visa** | Le marché congolais est multi-opérateurs et multi-canal | Un adaptateur par format (Vodacom, Airtel, Orange, Visa) vers un schéma unique | 4 formats acceptés |
| **BM-12** | Comparer et **transposer** la logique au canal Visa | Extension comparative du sujet | Évaluation Mobile Money → Visa, avec et sans adaptation | H4 : PR-AUC 0,985 sur Visa sans donnée Visa |
| **BM-13** | Vision **géographique** nationale | Les fraudes se concentrent par zones (provinces, agents) | Carte des 26 provinces, classement, flux en direct | Carte et classement par province |
| **BM-14** | **Tableau de bord** de supervision | Piloter l'activité en temps réel | Indicateurs (volume, taux d'alerte, montants bloqués), séries, répartitions | Rafraîchissement de quelques secondes |
| **BM-15** | **S'adapter** aux fraudes nouvelles | Les fraudeurs s'adaptent ; un modèle figé se dégrade | Réentraînement déclenché (nouvelles étiquettes, dérive, comportements nouveaux, demande), champion / challenger | H5 : figé 0,968 contre 0,998 mis à jour (2025) |
| **BM-16** | Faire **examiner les cas nouveaux** | Les comportements jamais vus doivent être étiquetés pour être appris | Liste des transactions les plus « étranges », revue d'analyste (légitime / fraude) | Verdict converti en étiquette |
| **BM-17** | **Traçabilité** et conformité | Exigence d'audit du régulateur | Journal d'audit chaîné par hachage, interdiction de modification et de suppression | Toute action et décision journalisée |
| **BM-18** | **Gérer les droits** selon le rôle | Séparation des responsabilités | Rôles analyste, superviseur, administrateur ; pages et actions protégées | Contrôle côté serveur et côté interface |

---

## II.3 Besoins techniques (non fonctionnels)

### II.3.1 Performance et disponibilité

| Réf. | Besoin | Réponse du système | Indicateur |
|---|---|---|---|
| **BT-01** | Latence compatible avec le paiement (décision avant exécution) | Variables précalculées dans Redis, inférence d'une seule opération, explication détaillée calculée seulement au-delà d'un risque moyen | Médiane ≈ 60 ms, 95ᵉ centile ≈ 110 ms de bout en bout |
| **BT-02** | Supporter le débit des opérateurs | Plusieurs processus de scoring, limitation de débit par opérateur (Nginx) | Rejeu soutenu à 15 opérations/s sur un poste ; montée en charge par réplicas (Kubernetes) |
| **BT-03** | Continuité de service si le scoring est indisponible | Politique de repli configurable (laisser passer ou faire vérifier), relances bornées sur les échecs transitoires | 2 replis sur 19 165 opérations au rejeu |
| **BT-04** | Résilience aux doublons (relances des opérateurs) | Idempotence : une opération reçue deux fois renvoie sa décision d'origine sans modifier le profil | Testé : quatre envois → une seule décision |
| **BT-05** | Déploiement multi-zones | Manifestes Kubernetes, déclinaisons Kinshasa et Katanga | `infra/kubernetes/overlays/` |

### II.3.2 Données et intégration

| Réf. | Besoin | Réponse du système |
|---|---|---|
| **BT-06** | Interopérabilité avec des formats hétérogènes | Patron *Adapter* : un adaptateur par opérateur vers un schéma pivot unique (`UnifiedTransaction`) |
| **BT-07** | Prise en compte du contexte monétaire | Montants en CDF et USD, conversion au taux de l'année de l'opération |
| **BT-08** | Profil client à jour en temps réel | Feature store Redis : état comportemental et séquence des 10 dernières opérations par client, verrou par client |
| **BT-09** | Historisation des décisions | Base TimescaleDB (série temporelle) : opération, décision, explication, variables, étiquette |
| **BT-10** | Découplage des traitements | Bus d'événements Kafka (Redpanda) : enregistrement, alertes, audit traités par des workers indépendants |
| **BT-11** | Cohérence entre entraînement et production | Mêmes fonctions de calcul des variables hors ligne et en ligne ; contrôle de l'empreinte du scaler | Écart médian des scores en ligne / hors ligne : 0 |

### II.3.3 Exigences liées à l'apprentissage automatique

| Réf. | Besoin | Réponse du système |
|---|---|---|
| **BT-12** | Gérer le fort **déséquilibre** des classes (≈ 1,3 % de fraudes) | Pondération des classes, sous-échantillonnage des légitimes (LSTM), métrique PR-AUC plutôt que ROC-AUC |
| **BT-13** | Éviter toute **fuite d'information** | Variables calculées sur le passé seulement ; découpage **temporel** (entraînement / validation / test) ; seuil choisi sur la validation |
| **BT-14** | **Explicabilité** | SHAP exact (TreeSHAP), contributions des branches, poids d'attention, cas proches (RAG) |
| **BT-15** | Évaluation **statistiquement fondée** | Intervalles de confiance par bootstrap apparié par usager, test de McNemar, plusieurs graines |
| **BT-16** | Surveillance de la **dérive** | Kolmogorov-Smirnov et PSI par variable, PSI du score, taux de comportements nouveaux (autoencodeur) |
| **BT-17** | **Réentraînement** maîtrisé | Champion / challenger : promotion seulement si meilleur ; contrôle de sanité avant activation ; garde-fou contre le surapprentissage |
| **BT-18** | **Reproductibilité** | Générateur à graine fixe, registre des modèles (MLflow), artefacts versionnés, garde-fou de non-régression |
| **BT-19** | Robustesse face aux attaques **jamais vues** | Lois physiques (déplacement impossible, solde) en complément du modèle de données |

### II.3.4 Sécurité et confidentialité

| Réf. | Besoin | Réponse du système |
|---|---|---|
| **BT-20** | Authentification des systèmes | Clé d'API par opérateur et pour le scoring |
| **BT-21** | Authentification et droits des utilisateurs | Jetons JWT, rôles (analyste, superviseur, administrateur), pages protégées côté serveur |
| **BT-22** | Intégrité du journal | Journal d'audit chaîné par hachage SHA-256, modification et suppression interdites au niveau de la base |
| **BT-23** | Confidentialité des données clients | Aucun service externe pour l'analyse (pas de modèle de langage en ligne, carte sans fournisseur de tuiles par défaut) ; texte des messages ni stocké ni publié |
| **BT-24** | Protection de l'interface | En-têtes de sécurité (Nginx), échappement des données affichées |

### II.3.5 Exploitation et maintenance

| Réf. | Besoin | Réponse du système |
|---|---|---|
| **BT-25** | Observabilité | Métriques Prometheus, tableaux Grafana, journaux centralisés (Loki), alertes (latence, erreurs, dérive, cohérence du feature store) |
| **BT-26** | Qualité logicielle | Tests automatisés par service (ML, scoring, back-office, workers, intégration) |
| **BT-27** | Conteneurisation | Images Docker par service, orchestration Docker Compose (poste) et Kubernetes (production) |

---

## II.4 Contraintes propres au contexte de la RDC

| Contrainte | Conséquence sur la conception |
|---|---|
| Téléphones simples et USSD très répandus | Variables indépendantes de l'application (montant, fréquence, agent) ; pas de dépendance à l'empreinte du smartphone seule |
| Réseau d'agents de proximité | Variables liées à l'agent (nouvel agent, nombre de clients servis en 24 h) ; typologie « fraude d'agent » |
| Double monnaie CDF / USD et dépréciation du franc | Montants convertis en USD au taux de l'année |
| Connectivité inégale | Traitements locaux, aucune dépendance à un service en ligne pour décider |
| Vaste territoire (26 provinces) | Localisation par province, loi physique de déplacement entre chefs-lieux |
| Niveaux KYC et plafonds | Variable « montant / plafond KYC » ; règle de vérification en cas de dépassement |
| Absence de jeu de données public | Générateur de données synthétiques réaliste (2019-2025) ; validation sur données réelles à mener |

---

## II.5 Traçabilité besoins → hypothèses de recherche

| Hypothèse | Besoins concernés |
|---|---|
| H1 — Le profilage améliore la détection par rapport aux approches statiques | BM-01, BM-02, BM-04 |
| H2 — Les variables temporelles, fréquentielles et contextuelles discriminent | BM-02, BT-13 |
| H3 — Les performances varient selon la famille de modèles | BM-01, BT-12, BT-15 |
| H4 — Transposition Mobile Money → Visa | BM-11, BM-12 |
| H5 — Mise à jour du modèle face aux fraudes émergentes | BM-15, BM-16, BT-16, BT-17 |

---

## II.6 Priorisation (méthode MoSCoW)

| Priorité | Besoins |
|---|---|
| **Indispensable** (*Must*) | BM-01, BM-02, BM-03, BM-04, BM-06, BM-17, BT-01, BT-11, BT-13, BT-21, BT-22 |
| **Important** (*Should*) | BM-05, BM-07, BM-08, BM-09, BM-11, BM-15, BT-03, BT-04, BT-16, BT-17 |
| **Souhaitable** (*Could*) | BM-10, BM-12, BM-13, BM-14, BM-16, BT-19, BT-25 |
| **Hors périmètre actuel** (*Won't, pour l'instant*) | Raccordement aux systèmes réels des opérateurs, validation sur données réelles, analyse de messages en lingala et swahili |
