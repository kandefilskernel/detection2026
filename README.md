# Détection de fraude Mobile Money RDC (+ cartes Visa virtuelles)

Mémoire : « Conception et évaluation d'un modèle IA de profilage comportemental pour la détection
de fraude Mobile Money en RDC : extension comparative aux cartes Visa virtuelles ».

Algorithme, architecture et limites : [docs/ARCHITECTURE_CIBLE.md](docs/ARCHITECTURE_CIBLE.md).

> **Statut : prototype de recherche.** Toutes les données sont synthétiques. Avant tout usage réel :
> pilote en mode silencieux avec un opérateur, audit de sécurité, validation juridique et
> réglementaire (BCC, protection des données).

## Architecture en bref

```
Opérateurs ──► Nginx /ingest ──► integration-layer ──► scoring-service ──► décision (≈ 20 ms)
 (Vodacom, Airtel,               (adaptateurs)          │ profil Redis + modèle hybride
  Orange, Visa)                                         │ XGBoost + LSTM-Attention + Autoencodeur
                                                        ▼
                                 Kafka (Redpanda) : transactions.scored, fraud.alerts, audit.logs
                                    │ persister → TimescaleDB   │ alerter → dossiers + SMS/e-mail
                                    │ auditor → journal chaîné  │ drift-monitor → Prometheus
                                                        ▼
            Tableau de bord Next.js  ◄── backoffice-api (JWT, rôles, dossiers, rapports, audit)
            Grafana / Prometheus / Loki (supervision)   retrainer (champion / challenger)
```

## Lancer le projet (Windows + Docker Desktop + VS Code)

Commandes à taper dans le terminal PowerShell de VS Code, à la racine du projet.

### 1. Première installation
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1          # si refusé : Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
copy .env.example .env               # puis changer les mots de passe
```

### 2. Données et modèle (si `ml/data` est vide)
```powershell
.\scripts\run_pipeline.ps1                  # génération + variables + entraînement (~10 min)
.\scripts\run_pipeline.ps1 -SkipGeneration  # réutilise les données existantes
```

### Jeu de données pluriannuel 2019-2025
Même structure de fichiers que le jeu d'origine (`transactions.csv`, `users.csv`, `agents.csv`, `merchants.csv`), environ
630 000 opérations sur 2019-2025, avec les 8 typologies de fraude dont le mélange évolue d'année en année, l'ouverture
progressive des comptes, la croissance de l'activité, le lancement de la carte Visa virtuelle (2021, hypothèse), un taux
USD/CDF par année (`shared/utils/fx.py`, valeurs approximatives) et des voyages légitimes physiquement cohérents.
```powershell
python ml/generator/generate_synthetic_data.py --multi-year                    # -> ml/data/raw_2019_2025 (n'écrase rien)
.\scriptsun_pipeline.ps1 -MultiYear                                          # régénère dans ml/data/raw et réentraîne tout
```
Le jeu d'origine (180 jours, 2025) reste reproductible à l'identique sans `--multi-year`.

### 3. Démarrer toute la plateforme
Docker Desktop doit être lancé.
```powershell
docker compose up -d --build        # 1re fois : ~15 min (téléchargement de PyTorch)
docker compose ps                   # tous les services « Up » / « healthy »
python scripts\seed_database.py     # comptes de démonstration (analyste, superviseur)
```

| Adresse | Contenu |
|---|---|
| http://localhost | Tableau de bord (comptes dans `scripts/seed_database.py`, admin dans `.env`) |
| http://localhost/ingest/v1/transactions/{vodacom\|airtel\|orange\|visa} | API des opérateurs |
| http://localhost:8001/docs · :8002/docs · :8003/docs | Documentation des API (scoring, intégration, back-office) |
| http://localhost:3001 | Grafana (admin / `GRAFANA_ADMIN_PASSWORD`) |
| http://localhost:9090 | Prometheus (cibles, règles d'alerte) |
| http://localhost:8088 | Console Kafka (Redpanda) |
| http://localhost:8025 | Boîte mail locale (e-mails d'alerte) |
| http://localhost:5000 | MLflow (expériences et registre des modèles) |

### 4. Démonstration temps réel
```powershell
python scripts\simulate_transactions.py --rate 20                        # trafic des 4 opérateurs
python scripts\simulate_transactions.py --only-fraud-episodes --rate 5   # démo jury
```
Latence réaliste : lancer le simulateur **dans** le réseau Docker (sinon le relais de ports de
Docker Desktop ajoute ~40 ms) :
```powershell
docker run --rm --network fraud-detection-rdc_default -v ${PWD}:/work:ro -w /work --entrypoint sh fraud-rdc/scoring-service:dev -c "pip install -q --user httpx==0.27.0; python scripts/simulate_transactions.py --url http://integration-layer:8002 --rate 40"
```

### 5. Apprentissage continu
Le planificateur (`retrainer`) relève toutes les 10 minutes des **signaux** et réentraîne le modèle quand l'un d'eux le justifie :
nouvelles étiquettes (verdicts d'analystes, plaintes), nouvelles données (20 000 transactions), **dérive** des variables,
**nouveaux comportements** (part anormale de transactions « jamais vues » par l'autoencodeur, `NOVELTY_RATE`), modèle trop
ancien, ou **demande manuelle** (bouton « Réentraîner maintenant », superviseur ou administrateur).
Garde-fous : minimum de données étiquetées et de fraudes confirmées (sinon l'événement est noté « en attente » avec ce qui
manque), repos de 6 h entre deux entraînements automatiques, et le nouveau modèle n'est **promu que s'il est meilleur**
(champion / challenger). Tout est visible dans la carte « Apprentissage continu » du tableau de bord (signaux, journal,
comportements nouveaux à examiner). Une revue d'analyste (bouton sur la page d'une transaction) produit l'étiquette.
```powershell
python scripts\simulate_feedback.py                      # démo : verdicts d'analystes et plaintes
docker compose exec retrainer python -m ml.retraining.retrain --dry-run --quick   # essai sans promotion
python -m ml.monitoring.build_reference --ae-only        # ajoute la référence de nouveauté à une référence existante
```

### Typologie de fraude et évaluation de recherche
Chaque transaction signalée (VERIFY / BLOCK) porte le **type de fraude probable** (échange de SIM, ingénierie
sociale, smurfing, fraude d'agent, prise de contrôle de compte, test de carte, carte non présente, vidage par
rechargement), avec sa probabilité et les autres hypothèses. Un second modèle (`ml/training/train_fraud_type.py`)
le détermine ; il est affiché dans les transactions, les dossiers, la carte, le tableau de bord, filtrable, et
inclus dans l'e-mail des alertes critiques. Migration : `0002_fraud_type`.
```powershell
python -m ml.training.train_fraud_type          # entraîne le classifieur de typologie (ml/reports/fraud_type_results.json)
python -m ml.training.research_evaluation       # teste H1-H4 avec IC95 et tests (ml/reports/research_evaluation.md)
```

Détection en temps réel par typologie (rejoue les 254 clients victimes de la période de test, 5 068 opérations, via
l'integration-layer ; réamorcer Redis avant pour partir de profils neufs) :
```powershell
docker compose run --rm feature-store-seeder python -m ml.serving.seed_feature_store
python scripts\simulate_transactions.py --only-fraud-episodes --fraud-users 254 --rate 12 --quiet --report
```
Le rapport (`ml/reports/realtime_replay.json`) donne, par typologie et par épisode, le taux de détection, la part
d'épisodes stoppés dès la première opération, le type identifié à la première alerte et la perte avant alerte.

### RAG : éléments de preuve pour chaque décision
La page d'une transaction affiche des **preuves** (`GET /transactions/{id}/evidence`) : les 5 cas passés les plus
proches avec leur verdict, la fiche de la typologie de fraude (`shared/rag/knowledge/*.md`) et un indicateur de
cohérence entre l'avis de ces cas et la décision du modèle (« décision confortée » / « à vérifier »). La mémoire
s'enrichit des verdicts des analystes. Aucun modèle de langage externe : toutes les phrases sont construites à partir
de sources citées, et aucune donnée client ne quitte la plateforme. Le détail est dans `ml/reports/rag_evaluation.md`.
```powershell
python -m ml.rag.case_index        # construit la mémoire de cas (ml/artifacts/case_index.npz)
python -m ml.rag.evaluate_rag      # mesure l'apport du RAG (ml/reports/rag_evaluation.md)
```

### NLP : sentiment et ingénierie sociale dans les messages
Le motif / référence d'un transfert (champ optionnel `memo`), une plainte client ou un SMS signalé sont analysés
par un lexique transparent (`shared/nlp/`) : sentiment (négatif / neutre / positif), émotions (peur, colère,
détresse) et indices de manipulation (demande de PIN, faux agent, faux gain, menace de blocage, secret, urgence…),
chacun justifié par l'extrait de texte qui l'a déclenché. Un message très manipulateur impose une vérification
(règle `TEXTE_INGENIERIE_SOCIALE`, jamais un blocage à lui seul) et fixe le type « ingénierie sociale ». Une plainte
qui décrit une manipulation renseigne ce type pour les fraudes que le modèle n'avait pas signalées. Le texte brut
n'est ni stocké ni publié dans Kafka. Outil d'analyste : encadré « Analyser un message » dans Alertes & dossiers.
```powershell
python -m ml.nlp.evaluate_nlp --dev    # corpus de réglage
python -m ml.nlp.evaluate_nlp          # corpus gelé -> ml/reports/nlp_evaluation.json
python scripts\simulate_transactions.py --only-fraud-episodes --demo-memos   # démo avec messages rédigés par l'équipe
```
Limites : français seulement ; corpus écrits par l'équipe (non collectés) ; détection de motifs connus.

### Modèle hybride : données + lois physiques
Deux modèles complémentaires jugent chaque transaction. Le **modèle de données** (XGBoost + LSTM + autoencodeur) repère ce qui
est statistiquement inhabituel. Le **modèle par les lois physiques** (`ml/physics/laws.py`) repère ce qui est impossible quel que
soit le comportement du client : **cinématique** (deux provinces trop éloignées pour le temps écoulé : route 80 km/h, avion
800 km/h + 2 h de formalités) et **conservation** (débit supérieur au solde, temps avant vidage). La décision finale est
l'hybride : alerte si l'un OU l'autre signale. `PHYSICS_MODE` règle l'effet : `off`, `shadow` (calcul, affichage et métriques
`scoring_physics_violations_total`, sans effet sur la décision) ou `enforce` (**par défaut** : une violation nette de la
cinématique impose une vérification, règle `LOI_PHYSIQUE_CINEMATIQUE`, sans jamais bloquer à elle seule). Sur le simulateur,
qui ne respecte pas la physique des déplacements, `enforce` soumet environ 0,6 % des opérations légitimes à vérification ;
sur des données réelles cette fréquence doit être mesurée, et le mode repassé en `shadow` si elle est trop élevée.
```powershell
python -m ml.physics.evaluate_physics     # violations, valeur ajoutée, coût, test de robustesse -> ml/reports/physics_evaluation.md
```

### Courbes d'apprentissage et surapprentissage
Chaque entraînement (`train_model`, réentraînement automatique) enregistre la perte d'entraînement et celle de validation de
chaque branche, et rend un verdict (`ml/training/diagnostics.py`) : sain, peut encore apprendre, surapprentissage léger ou
net. Un nouveau modèle en **surapprentissage net** (perte de validation plus du double de celle d'entraînement,
`OVERFIT_MAX_GAP`) n'est jamais promu, même s'il a de meilleures métriques. Les courbes sont visibles dans la carte
« Apprentissage continu ». Diagnostic sans toucher au modèle déployé :
```powershell
python -m ml.training.diagnose_training    # -> ml/artifacts/training_diagnostics.json et ml/reports/training_diagnostics.md
```

### Stabilité de la détection
- **Idempotence** : une transaction reçue deux fois (relance d'un opérateur après un délai dépassé) renvoie sa décision d'origine
  (`duplicate: true`, 30 min) sans toucher au profil ni republier dans Kafka ; sinon la vélocité compterait deux fois la même
  opération et fausserait les alertes.
- **Relances bornées** de l'integration-layer sur les échecs transitoires (profil occupé, coupure réseau) avant la politique de
  repli ; sûres grâce à l'idempotence.
- **Contrôle de sanité des modèles** : un modèle promu est scoré sur des cas de contrôle avant d'être activé à chaud ; s'il donne
  des probabilités invalides ou des branches indisponibles, il est refusé et l'ancien reste en service (alerte `NouveauModeleRefuse`).
- **Garde-fou de non-régression** : `python -m ml.training.detection_gate` vérifie que le modèle en place tient ses planchers
  (PR-AUC, rappel à 1 % de faux positifs, rappel par typologie) sur la période de test ; test `ml/tests/test_detection_gate.py`.
- Nginx résout les adresses des services à chaque requête (plus de « 502 » après une reconstruction).
- **Cohérence du feature store** : l'amorçage Redis utilise les artefacts montés (et non ceux figés dans l'image) et
  enregistre l'empreinte du scaler ; le scoring la compare au modèle servi (`/health` → `feature_store_consistent`,
  alerte `FeatureStoreIncoherent`). **Après tout réentraînement complet (`train_model`), relancer l'amorçage** :
  `docker compose run --rm feature-store-seeder python -m ml.serving.seed_feature_store`.

### 6. Tests, charge, Kubernetes
```powershell
.\scripts\run_tests.ps1                               # toutes les suites (PostgreSQL requis)
python -m ml.serving.parity_check --n 2000            # parité entraînement / production
python scripts\load\build_payloads.py
docker run --rm --network fraud-detection-rdc_default -v ${PWD}/scripts/load:/load grafana/k6:0.53.0 run /load/k6_ingest.js
kubectl kustomize infra\kubernetes\overlays\kinshasa  # manifests zone Kinshasa (ou katanga)
```

### Arrêter
```powershell
docker compose down        # ajouter -v pour effacer aussi les données
```

## Dépannage
- **La construction échoue en téléchargeant PyTorch** : connexion instable ; relancer
  `docker compose build` — le cache pip conserve ce qui a déjà été téléchargé.
- **Le scoring ne démarre pas (« feature store vide »)** : `python -m ml.serving.seed_feature_store`.
- **Remettre la démo à zéro** : `python -m ml.serving.seed_feature_store` (profils) puis vider les
  tables `scored_transactions`, `cases`, `notifications` (le journal d'audit est inaltérable par conception).
