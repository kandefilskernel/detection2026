## II. Outils de développement et de déploiement

### 1. Environnement de développement

Le système est développé et testé sur un poste de travail unique, sans processeur graphique : tous les entraînements se font sur processeur, ce qui contraint la taille des modèles (tableau III.31).

*Tableau III.31 — Environnement de développement.*

| Élément | Choix |
|---|---|
| Poste | Windows 11 Entreprise, mémoire allouée à Docker : 7,7 Gio, sans GPU |
| Éditeur et terminal | Visual Studio Code ; PowerShell et Git Bash |
| Langage | Python 3.12 (environnement virtuel `venv`) ; TypeScript pour l'interface |
| Conteneurisation | Docker Desktop (moteur 29.8), Docker Compose |
| Contrôle de version | Git ; dépôt GitHub ; une branche par fonctionnalité |
| Tests | pytest 8.3 ; 158 tests automatisés (96 pour la partie apprentissage, 25 pour le back-office, 21 pour l'API d'intégration, 12 pour le service de notation, 4 pour les workers) |
| Base de données de développement | PostgreSQL / TimescaleDB, schéma créé par les migrations Alembic |
| Suivi des expériences | MLflow (registre des modèles) |
| Durée d'un entraînement complet | environ 7 minutes (403 s lors du diagnostic) pour l'ensemble des trois modèles |

L'organisation du dépôt suit l'architecture : un dossier par service, un dossier `ml/` pour tout ce qui touche à l'apprentissage, un dossier `shared/` pour le code partagé et un dossier `infra/` pour la supervision et le déploiement. Le même code de calcul des variables sert à l'entraînement et au service de notation (chapitre II, § 4.8). Les tests d'intégration créent une base PostgreSQL dédiée à partir des vraies migrations, de sorte que le schéma testé est celui de la production. Une procédure de reconstruction complète (génération, variables, entraînement, typologie, références de dérive) est automatisée par un script (`scripts/run_pipeline.ps1`).

### 2. Technologies de développement

Toutes les technologies sont libres, sans coût de licence ni dépendance à un service en ligne (tableau III.32). Les versions sont figées pour garantir la reproductibilité.

*Tableau III.32 — Technologies et versions.*

| Domaine | Technologies |
|---|---|
| Données et calcul | NumPy 1.26, pandas 2.2, SciPy, scikit-learn 1.4 |
| Apprentissage | XGBoost 2.0 (arbres boostés, TreeSHAP natif), PyTorch 2.2 (LSTM, autoencodeur), joblib |
| Suivi des modèles | MLflow 2.16 |
| Services web | FastAPI 0.110, Uvicorn 0.28, Pydantic 2.6, httpx 0.27 |
| Base de données | PostgreSQL 16 avec TimescaleDB 2.14, SQLAlchemy 2.0, Alembic 1.13, psycopg2 |
| Profils en mémoire | Redis 7.2 (client redis-py 5.0) |
| Bus d'événements | Kafka, via Redpanda v24.1 (client confluent-kafka 2.3) |
| Sécurité | python-jose (jetons JWT), bcrypt 4.2, hachage SHA-256, codes à usage unique (TOTP, RFC 6238) |
| Interface | Next.js 14, React 18, TypeScript 5, Tailwind CSS 3, Recharts 2, Leaflet 1.9 |
| Passerelle | Nginx 1.27 |
| Supervision | Prometheus 2.54, Grafana 11.2, Loki 3.1, Promtail 3.1 |
| Messagerie de démonstration | Mailpit 1.20 (boîte e-mail locale) |
| Tests | pytest, fakeredis (Redis simulé) |
| Modélisation | PlantUML |
| Déploiement | Docker, Docker Compose, Kubernetes (Kustomize) |

Les choix ont été guidés par cinq raisons : **FastAPI** parce qu'il partage le langage des modèles, traite les requêtes de façon asynchrone et produit automatiquement une documentation OpenAPI ; **XGBoost** pour sa performance sur données tabulaires et son explication exacte ; **Redis** parce qu'il lit un profil en moins d'une milliseconde, avec verrous et expiration automatique ; **PostgreSQL avec TimescaleDB** parce qu'il unit le relationnel et les séries temporelles, avec un partitionnement automatique par le temps ; **Kafka** pour le découplage entre la décision et le reste, le rejeu et les garanties de livraison.

### 3. Architecture de la solution

#### 3.1 Principes d'architecture

*Tableau III.33 — Principes d'architecture.*

| Principe | Mise en œuvre | Besoins servis |
|---|---|---|
| **Microservices** | Intégration, notation, back-office, workers et tâches d'apprentissage sont déployables séparément | BT-02, BT-27 |
| **Architecture orientée événements** | Le chemin critique (décision) est synchrone ; tout le reste (enregistrement, alertes, audit) passe par Kafka, de façon asynchrone | BT-01, BT-10 |
| **Schéma pivot** | Un format unique (`UnifiedTransaction`) entre l'intégration et la notation | BM-11, BT-06 |
| **Défense en profondeur** | Modèle appris, règles métier, lois physiques, analyse de réseau ; les règles ne peuvent que renforcer la décision | BM-03, BT-19 |
| **Explicabilité par conception** | Chaque décision est accompagnée de son explication et de ses preuves | BM-06, BT-14 |
| **Évolutivité maîtrisée** | Un nouveau modèle n'est promu que s'il est meilleur et passe les contrôles ; une politique de coût est simulée avant application | BM-15, BM-24, BT-17 |
| **Sécurité et confidentialité** | Moindre privilège, isolement par institution, aucun service externe | BT-20 à BT-23, BT-28 |

#### 3.2 Architecture logique

Le système est organisé en couches. Le diagramme de composants montre les composants et leurs dépendances (figure III.16).

![[paysage]Diagramme de composants](../uml/diagramme_composants.png)

*Figure III.16 — Diagramme de composants.*

*Tableau III.34 — Couches de l'architecture.*

| Couche | Composants | Responsabilité |
|---|---|---|
| Présentation | Nginx, tableau de bord Next.js | accès des utilisateurs internes |
| Intégration (API publique) | adaptateurs, format commun, clés, droits, quotas, retours, supervision | point d'entrée de toutes les institutions |
| Détection temps réel | magasin de profils, lois physiques, modèle hybride, typologie, SHAP, analyse de texte, cas similaires, politique de décision | décision en moins de 100 ms |
| Traitement asynchrone | Kafka ; workers *persister*, *alerter*, *auditor* | enregistrement, alertes, journal d'audit |
| Back-office | API interne : transactions, dossiers, rapports, audit, institutions, réentraînement, réseaux, revue, politique, équité | travail des analystes, des superviseurs et des administrateurs |
| Apprentissage continu | moniteur de dérive, planificateur, entraînement du challenger, MLflow | adaptation du modèle |
| Données | PostgreSQL / TimescaleDB, Redis, artefacts des modèles | persistance |
| Supervision | Prometheus, Grafana, Loki | observabilité |

Les diagrammes de ce chapitre présentent l'architecture de base. Les modules ajoutés ensuite (analyse de réseau, file de revue, politique de coût, équité, sécurité renforcée) s'intègrent au back-office sans modifier le chemin critique de la décision, sauf la politique de coût, que le service de notation recharge à chaud depuis Redis.

#### 3.3 Organisation du code

![[paysage]Diagramme de packages](../uml/diagramme_packages.png)

*Figure III.17 — Diagramme de packages.*

*Tableau III.35 — Packages du système.*

| Package | Contenu |
|---|---|
| `frontend/` | tableau de bord : pages, composants, accès à l'API |
| `services/integration-layer` | API publique : adaptateurs, format commun, gestion des partenaires, quotas |
| `services/scoring-service` | service de décision en temps réel |
| `services/backoffice-api` | API interne, migrations de la base (Alembic) |
| `services/workers` | workers *persister*, *alerter*, *auditor* |
| `ml/` | générateur, variables, lois physiques, modèles, entraînement, mise en service, surveillance, réentraînement, évaluations |
| `shared/` | modèles de base, schémas, sujets Kafka, NLP, cas similaires, graphe, politique de coût, utilitaires (taux de change, clés d'API) |
| `infra/` | Nginx, Prometheus, Grafana, Loki, Kubernetes |

#### 3.4 Modèle de données

![[paysage]Diagramme de classes](../uml/diagramme_classes.png)

*Figure III.18 — Diagramme de classes.*

*Tableau III.36 — Tables de la base de données.*

| Table | Rôle | Particularités |
|---|---|---|
| `scored_transactions` | toute opération notée : données, décision, explication, variables, étiquette | hypertable TimescaleDB partitionnée par le temps ; clé (`transaction_id`, `tx_time`) ; rattachée à une institution |
| `cases` | dossier d'alerte : statut, affectation, résolution, motif de revue | statuts OUVERT, EN_COURS, FRAUDE_CONFIRMEE, FAUX_POSITIF |
| `unblock_requests` | déblocages importants en attente d'un second validateur | une seule demande en attente par dossier |
| `notifications` | SMS et e-mails envoyés | liées au dossier |
| `audit_log` | journal d'audit inaltérable | chaînage `prev_hash` vers `hash` (SHA-256) ; modification et suppression interdites par déclencheur |
| `bo_users` | utilisateurs internes | rôle ANALYSTE, SUPERVISEUR ou ADMIN ; mot de passe haché par bcrypt ; secret TOTP chiffré, verrouillage |
| `institutions` | partenaires de l'API | type, droits, formats natifs, empreinte de la clé, quota de débit |
| `model_registry` | versions des modèles | statut CHAMPION, CHALLENGER, ARCHIVE ou REJETE ; métriques |
| `decision_policies` | versions de la politique de coût | auteur, justification, effet simulé ; une seule version active |
| `retrain_events`, `retrain_state` | journal et signaux de l'apprentissage continu | déclencheur AUTO ou MANUEL, motifs |

**Magasin de profils.** L'état comportemental de chaque client est conservé dans **Redis**, en mémoire, pour être lu en moins d'une milliseconde : agrégats de montants, appareils, agents et destinataires connus, dernière province, séquence des 10 dernières opérations. Les décisions y sont aussi conservées 30 minutes pour l'idempotence. La mise à jour du profil se fait sous **verrou**, afin que deux opérations simultanées d'un même client ne se contredisent pas (condition de concurrence).

**Journal d'audit chaîné.** Chaque entrée du journal contient l'empreinte de l'entrée précédente :

$$h_n = \mathrm{SHA256}\big(h_{n-1}\ \Vert\ \text{contenu}_n\big)$$

où SHA-256 est une fonction de hachage cryptographique (l'empreinte change entièrement au moindre changement du contenu et ne permet pas de retrouver ce contenu) et $\Vert$ la concaténation. Modifier une entrée passée change son empreinte et rompt toute la chaîne qui suit. Un déclencheur en base interdit en outre toute modification ou suppression. Une vérification de la chaîne, accessible au superviseur, prouve que le journal n'a pas été altéré.

#### 3.5 Comportement dynamique

**Notation d'une opération en temps réel.** L'institution envoie l'opération avant de l'exécuter ; l'API d'intégration vérifie la clé, le quota et le format, puis rattache l'opération à l'institution ; le service de notation vérifie l'idempotence, met à jour le profil sous verrou, calcule les variables et les lois physiques, applique le modèle hybride puis le classifieur de typologie, analyse le message éventuel et décide ; la décision est renvoyée de façon synchrone ; en parallèle, l'événement est publié dans Kafka et les workers enregistrent l'opération, ouvrent un dossier si nécessaire, préviennent le client et écrivent le journal d'audit (figure III.19).

![[paysage]Séquence du scoring](../uml/sequence_scoring_temps_reel.png)

*Figure III.19 — Diagramme de séquence de la notation en temps réel.*

**Processus cible de traitement d'une alerte.** Le diagramme d'activité suivant montre le processus complet, de la soumission de l'opération jusqu'au verdict de l'analyste. Il est à comparer au processus existant (figure II.2) : la détection a lieu avant l'exécution, la réponse est graduée, et le verdict de l'analyste alimente l'apprentissage.

![Processus cible](../uml/activite_traitement_alerte.png)

*Figure III.20 — Diagramme d'activité du processus cible.*

**Cycle de vie d'un dossier.** Un dossier naît OUVERT lorsqu'une décision VERIFY ou BLOCK est rendue, ou directement FRAUDE_CONFIRMEE lorsqu'il résulte d'une plainte ou d'un retour d'institution. Les deux états finaux produisent une étiquette ($y=1$ ou $y=0$) et ne peuvent plus être quittés. Déclarer faux positif une opération bloquée d'au moins 500 USD place le dossier en attente de la validation d'un second validateur avant de produire l'étiquette.

![États d'un dossier](../uml/etats_dossier.png)

*Figure III.21 — Diagramme d'états-transitions d'un dossier.*

**Réentraînement champion / challenger.** Le planificateur relève des signaux, entraîne un challenger, le soumet aux contrôles de qualité, puis ne le promeut que s'il est meilleur que le champion sur la même période (figure III.22).

![[paysage]Séquence du réentraînement](../uml/sequence_reentrainement.png)

*Figure III.22 — Diagramme de séquence du réentraînement.*

#### 3.6 Moteur de détection

Le moteur de détection assemble les composants décrits au chapitre II dans un ordre précis, sous le même service de notation : lois physiques et variables, modèle hybride (XGBoost, LSTM avec attention, autoencodeur, méta-apprenant), classifieur de typologie restreint au canal, analyse du message, **décision selon la politique de coût**, puis règles métier qui ne peuvent que renforcer l'action. Chaque réponse contient la probabilité, le niveau de risque, l'action, le type probable, les motifs, la version de la politique appliquée, les contributions SHAP, la part de chaque composante et les poids d'attention. Deux éléments sont **rechargés à chaud** sans interrompre le service : le modèle, quand un réentraînement promeut un nouveau champion (après un contrôle de cohérence ; en cas d'échec, l'ancien modèle est conservé et une alerte est levée), et la politique de coût, dans les dix secondes qui suivent son application par un superviseur.

#### 3.7 Interfaces de programmation

L'API partenaires ouvre le système aux opérateurs, aux banques et au régulateur. Elle est versionnée (`/v1`) et documentée au format OpenAPI (tableau III.37).

*Tableau III.37 — Routes de l'API partenaires.*

| Route | Droit requis | Rôle |
|---|---|---|
| `POST /v1/transactions` | transactions | notation au format commun |
| `POST /v1/transactions/{format}` | transactions | notation au format natif d'un opérateur (Vodacom, Airtel, Orange, Visa) |
| `GET /v1/transactions/{id}` | transactions | décision, dossier et étiquette d'une opération de l'institution |
| `POST /v1/feedback` | feedback | fraude constatée ou fausse alerte, devenant une étiquette |
| `GET /v1/stats` | transactions | statistiques de l'institution |
| `GET /v1/supervision/summary`, `/daily` | supervision | agrégats de toutes les institutions, sans donnée personnelle |

Les choix de conception sont les suivants. Le **patron *Adapter*** convertit chaque format d'opérateur vers `UnifiedTransaction` : ajouter un opérateur revient à écrire un adaptateur, sans toucher au moteur. Une **clé de 256 bits par institution** n'est conservée que sous forme d'empreinte SHA-256 et n'est affichée qu'une fois. Les **droits** sont portés par institution : un régulateur ne soumet pas d'opérations, une banque ne supervise pas le secteur. L'**isolement des données** est assuré par le code de l'institution, fixé par le serveur d'après la clé, et par une réponse 404 identique pour l'opération d'une autre institution et pour une opération inexistante. Un **quota** par institution (seau à jetons, réglable) protège le service, en plus de la limitation par adresse de Nginx.

Le back-office expose en outre les routes nécessaires aux écrans, dont les plus récentes sont présentées au tableau III.38.

*Tableau III.38 — Routes du back-office pour les fonctions de pilotage.*

| Route | Rôle |
|---|---|
| `GET /network/overview`, `GET /network/ego` | réseaux de fraude et voisinage d'un compte, d'un portefeuille, d'un appareil, d'un agent ou d'un marchand |
| `GET /feedback/queue`, `GET /feedback/quality` | file de revue (incertitude, nouveauté, réseau, témoin) ; précision réelle, fraudes manquées estimées, calibration |
| `GET /policy`, `POST /policy/simulate`, `PUT /policy` | politique de coût active, simulation d'une politique candidate, application d'une nouvelle version |
| `GET /fairness/live`, `GET /fairness/evaluation` | taux d'alerte par groupe en production, évaluation avec la vérité complète |
| `POST /auth/2fa/setup`, `/auth/2fa/enable`, `/auth/2fa/disable` | double authentification |
| `GET /cases/unblock-requests`, `POST /cases/unblock-requests/{id}/decision` | validation à quatre yeux des déblocages |

#### 3.8 Apprentissage continu

Quatre signaux déclenchent le réentraînement (tableau III.39).

*Tableau III.39 — Signaux de réentraînement.*

| Signal | Mesure | Déclenchement |
|---|---|---|
| Nouvelles étiquettes | verdicts d'analystes, plaintes, retours des institutions, revues ciblées | seuil d'étiquettes nouvelles atteint (500) |
| Dérive des données | test de Kolmogorov-Smirnov et indice PSI par variable, PSI du score | PSI au-dessus de 0,2 |
| Comportements nouveaux | part des opérations dont l'erreur de reconstruction dépasse le 99ᵉ centile de référence | taux supérieur à 4 % |
| Demande manuelle | superviseur | immédiat |

Le cycle suit quatre étapes : le planificateur décide, en respectant un délai de carence de six heures entre deux réentraînements ; un challenger est entraîné sur l'historique et sur les données de production étiquetées, les verdicts vérifiés pesant trois fois les étiquettes supposées ; il doit passer trois contrôles (le diagnostic de surapprentissage, la **porte de détection** qui exige un rappel minimal par type de fraude et un taux maximal de faux positifs, et la comparaison avec le champion sur la même période) ; s'il est meilleur, il est promu par écriture atomique, enregistré dans MLflow et rechargé à chaud.

#### 3.9 Sécurité

*Tableau III.40 — Menaces et contre-mesures.*

| Menace | Contre-mesure |
|---|---|
| Accès non autorisé à l'interface | Jeton JWT, rôles, routes protégées côté serveur et côté interface |
| Vol d'identifiants | Verrouillage après 5 échecs consécutifs ; double authentification par code à usage unique, secret chiffré en base, code déjà utilisé refusé |
| Déblocage frauduleux d'une opération importante | Validation à quatre yeux au-delà de 500 USD, par un second validateur différent du demandeur |
| Système partenaire non autorisé | Clés d'API par institution, droits, révocation |
| Fuite de données entre institutions | Rattachement fixé par le serveur, filtrage systématique |
| Altération des preuves | Journal d'audit chaîné, modification et suppression interdites en base |
| Abus et déni de service | Quota par institution, limitation de débit par adresse (Nginx), délais bornés |
| Fuite de données personnelles | Aucun service externe, texte des messages non stocké, supervision par agrégats |
| Injection SQL, XSS | Requêtes paramétrées (SQLAlchemy), échappement à l'affichage, en-têtes de sécurité |

*Tableau III.41 — Rôles et droits.*

| Rôle | Droits |
|---|---|
| Analyste | consulter les opérations, traiter ses dossiers, enregistrer les plaintes, examiner les comportements nouveaux, consulter les réseaux et la file de revue |
| Superviseur | droits de l'analyste + affecter les dossiers, valider les déblocages, régler la politique de décision, consulter l'équité et le journal d'audit, déclencher le réentraînement |
| Administrateur | droits du superviseur + gérer les utilisateurs (verrouillage, double authentification), les institutions, les quotas et les clés d'API |

#### 3.10 Interfaces utilisateur

L'interface est conçue pour l'analyste : chaque alerte présente d'emblée le niveau de risque, le type probable, les motifs et la procédure recommandée, afin de réduire le temps de traitement d'un dossier (tableau III.42).

*Tableau III.42 — Pages de l'interface.*

| Page | Rôle minimal | Contenu |
|---|---|---|
| Accueil (publique) | aucun | présentation du système, accès à la connexion |
| Connexion | aucun | authentification, code de double authentification |
| Tableau de bord | analyste | indicateurs temps réel, flux, alertes récentes, typologies, performance du modèle, apprentissage continu |
| Carte des fraudes | analyste | 26 provinces, intensité de la fraude |
| Transactions | analyste | recherche, filtres ; détail : SHAP, composantes, physique, analyse du message, cas similaires, revue |
| Alertes et dossiers | analyste | file priorisée, instruction, verdict, validations à quatre yeux |
| Réseaux de fraude | analyste | graphe des comptes, portefeuilles, appareils, agents et marchands liés |
| Revue et qualité | analyste | file de revue ciblée, précision réelle, fraudes manquées estimées, calibration |
| Sécurité du compte | analyste | activation de la double authentification |
| Politique de décision | superviseur | réglage des coûts, simulation avant application, historique des versions |
| Équité du modèle | superviseur | taux d'alerte par groupe, avec intervalles de confiance |
| Journal d'audit | superviseur | consultation du journal et vérification de la chaîne |
| Utilisateurs | administrateur | comptes, rôles, verrouillage, double authentification |
| Institutions et API | administrateur | partenaires, droits, quotas, clés d'API |

### 4. Architecture et services du déploiement

#### 4.1 Vue d'ensemble

Le prototype est déployé par **Docker Compose** sur un hôte unique. Chaque composant tourne dans son conteneur, sur un réseau interne commun ; seuls quelques ports sont publiés vers l'hôte (figure III.23).

![[paysage]Diagramme de déploiement](../uml/diagramme_deploiement.png)

*Figure III.23 — Diagramme de déploiement.*

#### 4.2 Services déployés

Vingt-trois services composent la plateforme : vingt-deux fonctionnent en continu et un (l'amorçage du magasin de profils) s'exécute une fois au démarrage (tableau III.43).

*Tableau III.43 — Services déployés.*

| Service | Rôle | Image | Port publié |
|---|---|---|---|
| `postgres` | base relationnelle et temporelle | TimescaleDB 2.14 (PostgreSQL 16) | 5432 |
| `redis` | magasin de profils, idempotence, politique de coût | Redis 7.2 | 6379 |
| `redpanda` | bus d'événements Kafka | Redpanda 24.1 | 19092 |
| `redpanda-console` | console du bus | Redpanda Console 2.6 | 8088 |
| `feature-store-seeder` | amorçage des profils (exécution unique) | image de notation | — |
| `scoring-service` | décision en temps réel | image de notation | 8001 |
| `integration-layer` | API publique des institutions | image d'intégration | 8002 |
| `backoffice-api` | API interne et migrations | image de back-office | 8003 |
| `worker-persister` | enregistrement des opérations | image des workers | — |
| `worker-alerter` | dossiers et notifications | image des workers | — |
| `worker-auditor` | journal d'audit | image des workers | — |
| `frontend` | tableau de bord | image du front | — |
| `nginx` | point d'entrée unique | Nginx 1.27 | 80 |
| `drift-monitor` | surveillance de la dérive | image d'apprentissage | — |
| `retrainer` | réentraînement automatique | image d'apprentissage | — |
| `mlflow` | registre des modèles | MLflow 2.16 | 5000 |
| `prometheus` | collecte des métriques | Prometheus 2.54 | 9090 |
| `grafana` | tableaux de bord de supervision | Grafana 11.2 | 3001 |
| `loki`, `promtail` | centralisation des journaux | Loki et Promtail 3.1 | — |
| `redis-exporter`, `postgres-exporter` | métriques des bases | exportateurs Prometheus | — |
| `mailpit` | boîte e-mail locale (alertes) | Mailpit 1.20 | 8025 |

Les services applicatifs reposent sur six images (notation, intégration, back-office, workers, apprentissage et front), construites à partir des mêmes dossiers `shared/` et `ml/` pour garantir la cohérence du code.

#### 4.3 Réseau et exposition

**Nginx** est l'unique point d'entrée : `/` mène au tableau de bord, `/ingest/` et `/v1/` à l'API d'intégration, avec une limitation de 200 requêtes par seconde et par adresse (rafale de 400), une taille de requête bornée à 64 Ko, des en-têtes de sécurité (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) et un délai de lecture borné. Une surcharge « production » (`docker-compose.prod.yml`) ferme tous les ports internes pour ne laisser exposés que Nginx (80) et Grafana (3001), impose des limites de ressources (par exemple 3 processeurs et 2 Gio au service de notation, 2 processeurs et 2 Gio à PostgreSQL), le redémarrage systématique des services et un comportement de repli strict de l'intégration (`FAIL_OPEN=false`) ; la console du bus et la boîte e-mail de démonstration passent dans un profil « outils » facultatif.

#### 4.4 Configuration, données persistantes et dépendances

La configuration passe par un fichier d'environnement (`.env`), dont un exemple documenté est versionné : secrets de signature des jetons, comptes de démonstration, clés des services, quotas, seuils de sécurité, durée de verrouillage. Les données de PostgreSQL, du bus, de Grafana, de Loki et de MLflow vivent dans des volumes persistants ; les artefacts des modèles sont montés en lecture seule dans les services qui les lisent et en écriture dans le seul service de réentraînement. Les dépendances sont déclarées avec leurs conditions de santé : le back-office attend PostgreSQL, Redis et le bus ; les workers, le frontend, Nginx et le réentraînement attendent la santé du back-office, qui applique les migrations à chaque démarrage de façon idempotente ; la notation attend l'amorçage du magasin de profils. Les services applicatifs et les bases de données disposent d'un contrôle de santé.

#### 4.5 Supervision

**Prometheus** collecte les métriques de tous les services : latence de décision, décisions par action, erreurs, relances, dérive, violations physiques, cohérence du magasin de profils, publications Kafka, quotas dépassés. **Grafana** les présente dans deux tableaux de bord provisionnés automatiquement (santé du système et dérive du modèle). **Loki**, alimenté par **Promtail**, centralise les journaux au format JSON. Treize règles d'alerte couvrent les pannes et les dérives : service indisponible, latence élevée, erreurs de notation, mode dégradé, pic du taux d'alerte, échecs de publication, worker en échec, dérive du modèle, nouveaux comportements, violations physiques élevées, nouveau modèle refusé, relances fréquentes du scoring, magasin de profils incohérent.

#### 4.6 Mise à l'échelle et Kubernetes

Le service de notation ne conserve aucun état local : le profil est dans Redis, les décisions dans le bus. On peut donc ajouter des copies du service pour réduire la latence ou absorber un plus grand débit. Les manifestes **Kubernetes** (`infra/kubernetes/`, organisés avec Kustomize) reprennent les mêmes images : une base commune (espace de noms, configuration, réseau, applications, bases de données) et deux déclinaisons, **Kinshasa** et **Katanga**, afin de rapprocher le service des opérateurs et d'assurer la continuité en cas de panne d'un site. Deux limites sont à noter. Le quota de débit par institution est compté **par processus**, de sorte qu'avec plusieurs copies le débit global toléré peut atteindre le quota multiplié par leur nombre ; et le prototype tourne sur un hôte unique, sans réplication des bases de données.

#### 4.7 Vérification du déploiement

Le déploiement est vérifié à chaque reconstruction complète par la suite de 158 tests automatisés (tableau III.44), puis par un contrôle de santé de chaque service, de chaque route de l'API du back-office et de chaque écran, et par un rejeu de transactions à travers toute la chaîne : API d'intégration, notation, bus, workers, base, tableau de bord.

*Tableau III.44 — Tests automatisés.*

| Suite | Contenu | Tests |
|---|---|---|
| Apprentissage (`ml/tests`) | générateur, variables, modèles, lois physiques, cas similaires, texte, graphe, politique de coût, apprentissage continu, garde-fou de détection | 96 |
| Back-office | authentification, rôles, dossiers, rapports, réseau, revue, équité, politique, sécurité (double authentification, verrouillage, quatre yeux) | 25 |
| API d'intégration | adaptateurs, API partenaires, quotas, résilience | 21 |
| Service de notation | API `/v1/score` avec le vrai modèle et un Redis simulé | 12 |
| Workers | persistance, journal d'audit chaîné | 4 |

<!-- CONCLUSION -->
Ce chapitre a présenté les résultats, puis l'implémentation du système. L'analyse exploratoire a décrit un jeu de 631 968 transactions, sain, très déséquilibré (1,33 % de fraudes) et dont les fraudes évoluent dans le temps. L'hybride, qui combine XGBoost, un LSTM avec attention et un autoencodeur, est le meilleur des huit modèles comparés (PR-AUC 0,9955) ; sa supériorité sur XGBoost et sur le LSTM est statistiquement établie, et elle se traduit par 42 % de fausses alertes et 45 % de fraudes manquées en moins. Les cinq hypothèses de recherche sont confirmées sur ces données simulées, avec des réserves précises sur la transposabilité à la carte (effet plafond) et sur l'évolution des fraudes (circularité).

Les résultats montrent aussi que le modèle appris ne suffit pas : les lois physiques détectent 100 % d'une attaque inédite que le modèle manque presque entièrement, l'analyse de réseau rattrape 54 fraudes, la décision selon le coût divise la perte par plus de deux, et des revues ciblées ramènent les fraudes manquées de 73 à 38. L'équité est mesurée et révèle que les clients modestes, les agriculteurs et les étudiants subissent davantage de fausses alertes. La comparaison avec la littérature confirme les tendances connues (boosting devant modèle linéaire, gain de la séquence selon le type d'opération, intérêt d'associer supervisé et non supervisé) sans que les valeurs absolues soient comparables.

L'implémentation traduit ces choix en une plateforme de vingt-trois services : une architecture en microservices orientée événements, une décision en 59 ms en médiane, une API ouverte aux institutions, un apprentissage continu maîtrisé, une sécurité renforcée et une supervision complète, vérifiées par 158 tests automatisés. Les limites principales, données simulées, nombre fini de mules et d'appareils réutilisés, 500 clients et coûts fixés par hypothèse, appellent une validation sur données réelles, qui est la première des perspectives.
