# Questions et réponses pour la soutenance du mémoire complet

**Détection de fraude Mobile Money en RDC par profilage comportemental, avec extension aux cartes virtuelles**

Ce document couvre tout le mémoire, de l'introduction générale à la conclusion générale. Il est organisé comme le mémoire. Chaque question est suivie d'une réponse prête à dire à l'oral. Les chiffres viennent du mémoire corrigé.

Conseil de travail. Lisez d'abord la partie 8, qui explique clairement tous les concepts d'IA du mémoire, puis apprenez la partie 0 et la partie 7 (questions pièges). Les parties 1 à 6 servent à répondre en profondeur quand le jury creuse un point.

---

## 0. L'essentiel à savoir par cœur

### 0.1 Le mémoire en trois minutes

> « Le Mobile Money est devenu le principal canal financier de millions de Congolais, et la fraude y progresse. Les systèmes actuels reposent sur des règles fixes. Elles ignorent l'individu, se contournent facilement et n'expliquent pas leurs décisions. Ma recherche demande comment concevoir un modèle d'intelligence artificielle qui apprend le comportement habituel de chaque utilisateur pour détecter les fraudes en temps réel et de façon explicable, et dans quelle mesure cette approche se transpose aux cartes virtuelles.
>
> Faute de données réelles accessibles, j'ai conduit une évaluation expérimentale en environnement simulé. J'ai construit un générateur de 631 968 transactions entre 2019 et 2025, avec huit typologies de fraude, et j'ai décrit chaque opération par 58 variables qui mesurent l'écart au comportement habituel du client. J'ai comparé huit méthodes avec un protocole statistique rigoureux. Le modèle hybride, qui associe XGBoost, un LSTM avec attention et un autoencodeur, est le meilleur, avec une PR-AUC de 0,9955, un rappel de 97,8 % et une précision de 95,1 %.
>
> Trois hypothèses sont confirmées sur données synthétiques, deux sont partiellement vérifiées. J'ai ensuite implémenté une plateforme de vingt-trois services qui décide en 59 ms en médiane, explique ses décisions et apprend en continu. Ces résultats valent pour la simulation. La validation sur données réelles d'un opérateur est ma première perspective. »

### 0.2 Les chiffres clés

| Élément | Valeur |
|---|---|
| Période simulée | du 1er janvier 2019 au 31 décembre 2025 |
| Transactions | 631 968, dont 8 426 fraudes (1,33 %), soit 74 opérations légitimes pour une fraude |
| Clients et agents simulés | 500 clients, 800 agents |
| Variables par transaction | 58 |
| Typologies de fraude | 8 (5 Mobile Money, 3 carte virtuelle) |
| Jeu de test | du 13/12/2024 au 31/12/2025, 183 240 transactions dont 2 437 fraudes |
| Modèle retenu | Hybride (XGBoost, LSTM avec attention, autoencodeur, méta-apprenant) |
| PR-AUC de l'hybride | 0,9955 (XGBoost 0,9895, LSTM 0,9894) |
| Précision, rappel, F1 | 95,1 %, 97,8 %, 0,964 |
| MCC | 0,964 |
| Erreurs sur le test | 122 fausses alertes et 54 fraudes manquées (XGBoost 210 et 99) |
| Gain sur XGBoost seul | 42 % de fausses alertes en moins, 45 % de fraudes manquées en moins |
| Test de McNemar | 156 contre 23 (l'hybride a raison 156 fois, XGBoost 23 fois) |
| Sans historique du client | PR-AUC de 0,989 à 0,753 |
| Règles métier | 0,2726 de PR-AUC |
| Transfert vers la carte | PR-AUC 0,9849 sans donnée de carte |
| Modèle figé contre mis à jour | écart de +0,0299 en 2025 |
| Latence de bout en bout | 59 ms en médiane, 104 ms au 95e centile, 299 ms au 99e |
| Plateforme | 23 services, 158 tests automatisés |
| Décision selon le coût | perte divisée par plus de deux (2 354 à 1 017 USD) |
| Attaque inédite | modèle 0,3 %, lois physiques 100 % |
| Réseaux de mules | 54 fraudes récupérées, pour 831 fausses alertes de plus |

### 0.3 Les cinq hypothèses et leur statut

| Hypothèse | Contenu | Statut |
|---|---|---|
| H1 | Le profilage améliore la détection par rapport aux approches statiques | Confirmée sur données synthétiques |
| H2 | Les variables temporelles, fréquentielles et contextuelles contribuent à la discrimination | Confirmée sur données synthétiques (les variables temporelles sont redondantes) |
| H3 | Les performances varient selon les familles de modèles | Confirmée sur données synthétiques |
| H4 | La logique se transpose, au moins partiellement, vers les cartes virtuelles | Partiellement vérifiée (effet plafond) |
| H5 | Un modèle mis à jour reste meilleur qu'un modèle figé | Partiellement vérifiée (circularité du générateur) |

---

## 1. Introduction générale

**Q1. Quel est le problème que vous traitez ?**
R. La fraude dans les services de Mobile Money en RDC. Le Mobile Money est un canal majeur de transaction, mais les dispositifs de détection reposent surtout sur des règles statiques. Elles ne s'adaptent pas à l'individu et suivent mal l'évolution des fraudes. Le travail cherche un modèle qui apprend le comportement habituel de chaque usager.

**Q2. Quelle est votre question centrale ?**
R. Comment concevoir et évaluer un modèle d'intelligence artificielle capable de profiler le comportement transactionnel des usagers du Mobile Money en RDC pour détecter efficacement les fraudes, tout en vérifiant sa pertinence pour les cartes virtuelles.

**Q3. Pourquoi les cartes virtuelles ?**
R. Parce qu'elles forment un continuum avec le Mobile Money. Un portefeuille compromis peut servir à exploiter la carte qui lui est adossée. Les deux canaux ont des surfaces de risque différentes, l'un local et fermé, l'autre en ligne et international. Les comparer permet de tester si un comportement appris sur l'un se transpose à l'autre.

**Q4. Combien de questions de recherche, combien d'hypothèses, et comment se correspondent-elles ?**
R. Six questions et cinq hypothèses. La correspondance figure au tableau II.4. QR1 (comportements observables) et QR5 (indicateurs d'évaluation) n'appellent pas d'hypothèse, car l'une est descriptive et l'autre méthodologique. QR2 correspond à H2, QR3 à H1 et H3, QR4 à H4 et QR6 à H5.

**Q5. Quels sont vos objectifs spécifiques ?**
R. Il y en a six, notés OS1 à OS6. Construire un profil par utilisateur, comparer plusieurs familles de modèles avec un protocole statistique rigoureux, mesurer la transposition vers la carte virtuelle, intégrer le modèle dans une architecture temps réel explicable, l'ouvrir aux institutions par une API, et mesurer ce que le modèle laisse passer et à qui il nuit, y compris l'équité.

**Q6. Quelle est la nature de votre recherche ?**
R. Une évaluation expérimentale en environnement simulé, de type science de la conception. Je construis un artefact, le système de détection, et je l'évalue. Toutes les données sont synthétiques et aucune transaction réelle n'a été utilisée.

**Q7. Dans une version précédente, on lisait « dont 10 % est réelle ». Qu'en est-il ?**
R. C'était une formulation erronée, et je l'ai supprimée. Les données sont entièrement synthétiques. Le générateur est paramétré à partir de statistiques officielles (ARPTC, BCC, Banque mondiale), mais aucun journal de transactions réelles n'a servi. Le mémoire le dit maintenant de façon cohérente dès l'introduction.

**Q8. Quel est l'intérêt de l'étude ?**
R. Scientifique, parce qu'il y a peu de travaux contextualisés à la RDC et sur la transition Mobile Money vers carte virtuelle. Méthodologique, grâce à un protocole statistique complet et reproductible. Pratique, avec une plateforme ouverte aux opérateurs, aux banques et au régulateur.

**Q9. Quelle est la délimitation du sujet ?**
R. La fraude financière numérique en RDC, avec un accent sur le Mobile Money. Les cartes virtuelles sont abordées de manière comparative. Les dimensions juridiques, réglementaires et organisationnelles ne sont pas couvertes de manière exhaustive.

**Q10. Comment le mémoire est-il structuré ?**
R. Trois chapitres. Le chapitre I est l'état de l'art. Le chapitre II est l'analyse des besoins et la méthodologie. Le chapitre III présente les résultats puis l'implémentation. Une conclusion générale termine le mémoire.

---

## 2. Chapitre I. État de l'art

**Q11. Quelles sont les spécificités du contexte congolais que vous retenez ?**
R. Une bancarisation limitée, une forte informalité, d'importantes disparités entre provinces, une adoption rapide du Mobile Money (M-Pesa, Orange Money, Airtel Money), et surtout la coexistence durable du franc congolais et du dollar. Cette double monnaie complique l'analyse des montants et des comportements.

**Q12. Quelles fraudes décrivez-vous ?**
R. Pour le Mobile Money, l'ingénierie sociale, l'échange de SIM (SIM swap), la prise de contrôle de compte, la fraude d'agent et le fractionnement (smurfing). Pour la carte virtuelle, le vol des identifiants, le test de cartes (BIN testing) et l'achat frauduleux, en lien avec le compte Mobile Money adossé.

**Q13. Pourquoi les systèmes à règles ne suffisent-ils pas ?**
R. Ils reposent sur des seuils fixes, ignorent l'historique de chaque client, produisent beaucoup de faux positifs et se laissent contourner, par exemple en fractionnant sous un seuil. Je ne les rejette pas, car ils restent utiles pour la conformité et les schémas connus. Je les garde comme couche du dispositif, qui ne peut que durcir une décision.

**Q14. Quelles familles de méthodes la littérature offre-t-elle ?**
R. Cinq orientations. Les modèles ensemblistes comme XGBoost, le profilage comportemental, l'apprentissage profond séquentiel avec attention, le traitement en flux pour le temps réel, et l'explicabilité avec la gestion du risque. Le mémoire retient une combinaison de ces approches.

**Q15. Qu'est-ce que le profilage comportemental ?**
R. L'idée que la transaction n'est pas une unité isolée. Elle exprime un comportement plus large. Une opération suspecte est celle qui rompt avec les habitudes de la personne, et pas seulement celle qui paraît anormale en valeur absolue.

**Q16. Quelles lacunes de la littérature identifiez-vous ?**
R. Cinq. La bidevise est peu prise en compte, Mobile Money et carte sont traités séparément, les simulateurs contextualisés manquent, la tension entre performance, explicabilité et temps réel n'est pas résolue, et les travaux empiriques sur la RDC sont rares.

**Q17. Pourquoi simuler des données ?**
R. Il n'existe aucun jeu de données réel de transactions Mobile Money congolaises accessible au public, pour des raisons de confidentialité et d'accès. La simulation est une pratique établie. PaySim s'appuie sur un échantillon de journaux réels d'un pays africain. MoMTSim est un simulateur multi-agents calibré pour le Mobile Money. Le mien repose entièrement sur des hypothèses paramétrées, car aucun échantillon réel n'est disponible pour la RDC.

**Q18. Quelle est la différence entre votre travail et PaySim ou MoMTSim ?**
R. Le contexte congolais est pris en compte explicitement, avec l'USSD, la double monnaie au taux de l'année, les déplacements entre provinces et les statistiques officielles. Je simule aussi la carte virtuelle, des épisodes de fraude et des fraudes qui imitent le comportement normal.

**Q19. Comment avez-vous justifié le choix des huit typologies ?**
R. Elles s'appuient sur la littérature et sur les rapports sectoriels consultés sur le Mobile Money et les cartes. Je reconnais que leur poids respectif dans le contexte congolais mérite d'être mieux documenté par des sources locales. C'est une piste d'amélioration signalée.

**Q20. Votre bibliographie contient-elle des erreurs ?**
R. J'ai vérifié les références et corrigé celles qui étaient inexactes ou incomplètes, notamment les auteurs, les années et les titres. J'ai aussi retiré les doublons entre listes. J'indique clairement que les références ont été revues.

---

## 3. Chapitre II. Analyse des besoins et méthodologie

### 3.1 Besoins et données

**Q21. Qui sont les acteurs du système ?**
R. Le client, l'agent, l'analyste antifraude, le superviseur, l'administrateur, l'opérateur ou la banque partenaire et le régulateur. Chacun a des droits distincts, attribués par rôle et par institution.

**Q22. Comment avez-vous construit vos données ?**
R. Avec un générateur reproductible, à graine fixée. Il simule 500 clients et 800 agents sur sept ans, avec leurs habitudes, leurs appareils, leurs provinces et la croissance de l'activité. Les fraudes sont injectées par épisodes, avec des trajectoires crédibles. Le générateur est confronté aux statistiques officielles pour vérifier sa cohérence.

**Q23. Votre modèle n'apprend-il pas simplement les règles de votre générateur ?**
R. C'est une limite réelle et je l'ai écrite dans les menaces sur la validité. Pour la réduire, le générateur produit des cas légitimes difficiles (changement de téléphone, voyages, usage nocturne) et des fraudes qui imitent le normal. La tâche n'est pas triviale, car les règles métier n'atteignent que 0,2726 de PR-AUC et l'Isolation Forest ne détecte que 39 % des fraudes. La comparaison entre méthodes reste valide, car toutes sont évaluées dans les mêmes conditions.

**Q24. Pourquoi 500 clients seulement ?**
R. C'est une contrainte de calcul sur un poste sans processeur graphique. La conséquence est que 92 % des clients subissent au moins un épisode de fraude, ce qui dépasse la densité d'un portefeuille réel. Cela réduit la portée des intervalles de confiance par client. C'est la troisième limite du mémoire.

### 3.2 Variables et prétraitement

**Q25. Quelles variables utilisez-vous ?**
R. 58 variables regroupées en familles. Les montants (écart au montant habituel, en logarithme), la fréquence (vélocité sur une heure, un jour), le contexte (nouveauté de l'appareil, de la province, du destinataire, nombre de clients partageant un appareil), le temps (heure circulaire, nuit inhabituelle), les soldes et le plafond KYC, et les variables physiques de déplacement.

**Q26. Pourquoi le logarithme des montants ?**
R. Les montants sont très asymétriques. En Mobile Money, la médiane légitime est de 24,11 USD pour une moyenne de 44,06 USD, avec une asymétrie de 4,63. Le logarithme ramène la distribution vers quelque chose de plus symétrique et rend l'écart au montant habituel comparable d'un client à l'autre.

**Q27. Comment évitez-vous la fuite d'information ?**
R. Chaque variable est calculée uniquement à partir du passé de la transaction. Le découpage est chronologique, jamais aléatoire, et le même code calcule les variables à l'entraînement et en production, ce qui évite le décalage entre les deux.

**Q28. Comment gérez-vous le déséquilibre des classes ?**
R. Avec deux mécanismes et une métrique adaptée, la PR-AUC. Pour XGBoost, chaque fraude est pondérée dans la fonction de perte par le rapport entre légitimes et fraudes, soit environ 74. Pour le LSTM, seuls 30 % des opérations légitimes, tirées au hasard, sont conservés à chaque époque. Un modèle qui déclarerait tout légitime aurait 98,67 % d'exactitude sans rien détecter. L'effet du sous-échantillonnage sur la calibration est mesuré.

**Q29. Quel est le découpage des données ?**
R. Chronologique. L'apprentissage porte sur les premières années, une tranche distincte sert à l'arrêt précoce, la validation sert à fixer le seuil, et le test va du 13 décembre 2024 au 31 décembre 2025. Le seuil n'est jamais ajusté sur le test.

### 3.3 Modèles et métriques

**Q30. Quels modèles comparez-vous ?**
R. Huit méthodes. Les règles métier, la régression logistique, le Random Forest, XGBoost, l'Isolation Forest, l'autoencodeur, le LSTM avec attention et l'hybride. L'hybride est un empilement qui combine XGBoost, le LSTM et l'autoencodeur par un méta-apprenant.

**Q31. Pourquoi un modèle hybride ?**
R. Les composantes ne se trompent pas sur les mêmes opérations. XGBoost capte les relations non linéaires sur le profil instantané, le LSTM lit la dynamique des séquences, l'autoencodeur signale la nouveauté. Sur les 179 opérations où l'hybride et XGBoost divergent, l'hybride a raison 156 fois.

**Q32. Pourquoi la PR-AUC comme métrique principale ?**
R. Parce que les classes sont très déséquilibrées. La ROC-AUC reste élevée, 0,95 ou plus, même pour l'Isolation Forest qui ne détecte que 39 % des fraudes. La PR-AUC reflète ce qui compte, la précision et le rappel sur la classe rare.

**Q33. Quels autres indicateurs utilisez-vous ?**
R. Précision, rappel, F1, F2, MCC, spécificité, taux de faux positifs, rappel à budget de fausses alertes fixé (0,05 %, 0,1 %, 0,5 %, 1 %), score de Brier pour la calibration, perte attendue et équité entre groupes.

**Q34. Comment prouvez-vous que les écarts ne sont pas dus au hasard ?**
R. Par un bootstrap apparié par client (1 000 tirages), qui donne des intervalles de confiance sur la PR-AUC, et par le test de McNemar exact au seuil retenu. Le premier porte sur une métrique globale, le second sur les décisions opération par opération. Aucun intervalle de confiance de l'écart ne contient zéro.

**Q35. Pourquoi un écart de 0,006 de PR-AUC compte-t-il ?**
R. Parce qu'il se traduit par une réduction de 42 % des fausses alertes (de 210 à 122) et de 45 % des fraudes manquées (de 99 à 54). À une PR-AUC proche de 1, de petits écarts représentent de grandes différences d'erreurs.

**Q36. Comment avez-vous choisi le modèle final ?**
R. Par une matrice multicritère (performance, explicabilité, temps réel, dynamique, détection de l'inédit). L'hybride obtient 4,45 sur 5 et arrive premier dans 91 % de 2 000 pondérations tirées au hasard. Avec des poids égaux, il reste en tête. XGBoost est la solution de repli.

**Q37. Quelles sont les menaces sur la validité que vous reconnaissez ?**
R. Données simulées, nombre fini de mules et d'appareils réutilisés, 500 clients seulement, canal carte très facile à séparer, circularité de l'évolution des fraudes, coûts fixés par hypothèse. Elles sont traitées dans la section 6.4 du chapitre II et rappelées dans les limites du chapitre III.

---

## 4. Chapitre III. Résultats

### 4.1 Analyse exploratoire

**Q38. Que montre l'analyse exploratoire ?**
R. Le jeu est de bonne qualité, sans valeur manquante non structurelle. L'activité passe de 35 541 transactions en 2019 à 175 360 en 2025. Les fraudes sont 1,33 % du total. L'échange de SIM (2 220) et l'ingénierie sociale (1 850) dominent. La carte virtuelle a un taux de fraude de 3,06 % contre 1,24 % pour le Mobile Money. Les fraudes sont plus grosses (médiane de 95 USD) et 29,1 % surviennent la nuit contre 3,4 % pour les opérations légitimes.

**Q39. Quelles variables sont les plus corrélées à la fraude ?**
R. Le nombre de clients partageant l'appareil (0,70), la nouveauté de l'appareil (0,47), l'adresse IP étrangère (0,26), le nombre de débits sur une heure (0,22), le rapport au montant habituel (0,19) et la nouveauté du destinataire (0,19). Certaines variables sont redondantes entre elles, ce qui explique le faible poids des variables temporelles en ablation.

### 4.2 Comparaison des modèles

**Q40. Quel est le meilleur modèle et de combien ?**
R. L'hybride, avec une PR-AUC de 0,9955 contre 0,9895 pour XGBoost et 0,9894 pour le LSTM. Il obtient le meilleur résultat sur toutes les mesures au seuil, sauf la précision, la spécificité et les fausses alertes, où l'autoencodeur seul fait mieux, mais au prix de 937 fraudes manquées, soit dix-sept fois plus.

**Q41. Où l'hybride fait-il vraiment la différence ?**
R. Sur l'ingénierie sociale, la fraude la plus difficile, car c'est la victime elle-même qui paie. Le rappel passe de 85,9 % avec XGBoost à 92,1 % avec l'hybride. Il est aussi plus fort quand le budget d'alertes est serré. À 0,05 % de faux positifs, il détecte 96,9 % des fraudes contre 92,3 % pour XGBoost.

**Q42. Une PR-AUC de 0,9955, n'est-ce pas trop beau pour être vrai ?**
R. Sur des données simulées, les fraudes sont plus nettes qu'en réalité, et je le dis. Ce chiffre ne démontre pas une efficacité équivalente en production. Ce qui est robuste, c'est la comparaison, car toutes les méthodes sont évaluées dans les mêmes conditions et les écarts sont significatifs. En production, j'attends des chiffres plus bas, d'où le mode observation avant tout blocage.

**Q43. Pourquoi l'autoencodeur, s'il apporte si peu ?**
R. Il apporte peu en PR-AUC sur les fraudes connues, mais il réduit les fausses alertes et reste la seule composante qui signale les comportements jamais vus. Son taux de nouveauté déclenche aussi le réentraînement.

### 4.3 Les hypothèses

**Q44. Quel est le résultat pour H1 ?**
R. Le modèle de profilage atteint 0,9893 de PR-AUC. Sans historique du client, il tombe à 0,753, et les règles métier à 0,2726. Le rappel de l'ingénierie sociale passe de 0,856 à 0,137 sans historique. H1 est confirmée sur données synthétiques.

**Q45. Quel est le résultat pour H2 ?**
R. Les familles contextuelles (appareil, localisation, contrepartie) pèsent le plus. Sans elles, la PR-AUC passe de 0,989 à 0,843. Les montants et la fréquence comptent aussi. Les variables temporelles sont redondantes et leur retrait n'est pas significatif. H2 est confirmée, avec cette nuance.

**Q46. Pourquoi H4 n'est-elle que partiellement vérifiée ?**
R. Entraîné uniquement sur le Mobile Money, le modèle atteint 0,9849 de PR-AUC sur la carte virtuelle. Le classement des opérations se transpose très bien, le seuil moins bien (F1 de 0,929, puis 0,950 une fois recalibré). Mais la carte simulée est très facile à séparer, donc c'est un effet plafond. Dans l'autre sens, un modèle appris sur la carte seule s'effondre sur le Mobile Money (PR-AUC 0,555). La transposabilité est probablement surestimée.

**Q47. Pourquoi H5 n'est-elle que partiellement vérifiée ?**
R. Un modèle figé perd en qualité, de 0,986 de PR-AUC en 2022 à 0,968 en 2025, alors qu'un modèle réentraîné progresse. L'écart est de +0,0299 en 2025. Mais l'évolution des fraudes est un paramètre de mon générateur, donc le raisonnement est en partie circulaire. H5 montre que le mécanisme de mise à jour fonctionne, pas que les fraudes réelles évolueront de cette façon.

**Q48. Pourquoi avoir nuancé le statut des hypothèses ?**
R. Pour ne pas dépasser le périmètre des tests. Une hypothèse confirmée sur données synthétiques n'est pas confirmée en réel. Je distingue donc ce qui est confirmé, partiellement vérifié et à valider.

### 4.4 Compléments au modèle

**Q49. Que sont les lois physiques et pourquoi les ajouter ?**
R. Des contrôles de cinématique. Une personne ne peut pas être à 1 568 km de sa dernière opération trois minutes plus tard. Face à une attaque inédite de session relayée, le modèle appris n'en voit que 0,3 %, alors que les lois physiques les détectent toutes, avec 0,01 % de vérifications inutiles. C'est ce qui justifie la défense en profondeur. Le scénario est toutefois construit pour l'étude.

**Q50. Qu'apporte l'analyse de réseau ?**
R. Elle relie les comptes qui partagent un destinataire ou un appareil, ce qui révèle les mules. La règle « modèle ou réseau » récupère 54 fraudes manquées (50 d'ingénierie sociale et 4 de fractionnement), pour 831 fausses alertes de plus. Le rappel de l'ingénierie sociale passe de 92,1 % à 100 %.

**Q51. Comment fonctionne la décision selon le coût ?**
R. Elle compare le coût attendu de chaque action (laisser passer, vérifier, bloquer) selon la probabilité de fraude, le montant et le coût d'une fausse alerte. Elle divise la perte par plus de deux par rapport à un seuil unique (de 2 354 à 1 017 USD) et arrête 99,9 % des fraudes au lieu de 98,4 %, au prix de plus de vérifications peu coûteuses (0,63 % de clients dérangés contre 0,08 %).

**Q52. Comment expliquez-vous une décision ?**
R. Par TreeSHAP, qui donne la contribution exacte de chaque variable, par la contribution de chaque composante, par les poids d'attention sur les opérations passées, et par des cas passés similaires. Quand les cas proches confirment une alerte, elle est fondée dans 98 % des cas, contre 60,9 % quand ils la contredisent. Tout est inscrit dans un journal d'audit chaîné.

**Q53. Que fait la boucle de retour des analystes ?**
R. Les verdicts des analystes deviennent des étiquettes. Sur un rejeu de 13 mois, revoir les cas incertains ramène les fraudes manquées de 73 à 38 avec verdicts pondérés. L'échantillon témoin est la seule source qui mesure sans biais le taux de fraudes manquées.

**Q54. Votre modèle est-il équitable ?**
R. Pas parfaitement, et je le mesure. Le rappel reste proche de 100 % dans tous les groupes, mais neuf groupes reçoivent significativement plus de fausses alertes. Les clients modestes en reçoivent 2,3 fois plus et les agriculteurs 3,3 fois plus que les commerçants. L'écart s'explique en partie par leur taux de fraude de base plus élevé, mais il reste un coût inégal à surveiller. Ni l'opérateur ni le type de téléphone ne créent d'inégalité.

**Q55. Le choix du seuil est-il robuste ?**
R. Le seuil de 0,538 est choisi sur la validation et jamais sur le test. Sur le test, il tombe dans un plateau, car entre 0,45 et 0,75 le F1 varie de moins d'un point. Les probabilités sont bien séparées, avec un score de Brier de 0,00077, mais surestiment le taux réel dans la zone intermédiaire.

---

## 5. Chapitre III. Implémentation

**Q56. Décrivez l'architecture.**
R. Une architecture en microservices orientée événements. Un service de notation rend la décision, une couche d'intégration traduit les formats des opérateurs, des workers traitent les événements via un bus Kafka (Redpanda), un back-office sert les analystes, et une couche d'apprentissage réentraîne le modèle. Les données sont dans PostgreSQL avec TimescaleDB, et le profil de chaque client est dans Redis. L'ensemble forme vingt-trois services déployés avec Docker Compose.

**Q57. Est-ce une architecture CQRS ?**
R. Non, pas au sens strict. Il n'y a ni bus de commandes, ni modèles de lecture dédiés, ni projections, et les deux côtés partagent la même base. Il existe une séparation de fait, avec le service de notation côté écriture et le back-office côté lecture. Je la décris comme une architecture orientée événements avec séparation des responsabilités par service, sans la présenter comme du CQRS.

**Q58. Pourquoi Kafka ?**
R. Pour séparer la décision du reste du traitement, permettre le rejeu et bénéficier de garanties de livraison. La décision n'attend pas l'écriture en base.

**Q59. Pourquoi Redis pour le profil ?**
R. Pour lire l'état d'un client en moins d'une milliseconde. Le service de notation ne garde aucun état local, ce qui permet d'ajouter des copies pour réduire la latence. Le profil est mis à jour sous verrou, pour éviter que deux opérations simultanées du même client se contredisent.

**Q60. Le temps réel est-il tenu ?**
R. La latence de bout en bout est de 59,5 ms en médiane, 104,4 ms au 95e centile et 299 ms au 99e, sur un rejeu de 19 165 opérations à 15 par seconde. Le 95e centile est à la limite de l'objectif de 100 ms. Le prototype tourne sur un seul poste. Les 111 épisodes de fraude du rejeu sont tous détectés.

**Q61. Comment garantissez-vous l'idempotence ?**
R. Les décisions sont conservées 30 minutes dans Redis. Si une institution renvoie la même opération, elle reçoit la même décision sans double comptage dans le profil.

**Q62. Qu'est-ce que le journal d'audit chaîné ?**
R. Chaque entrée contient l'empreinte SHA-256 de la précédente. Modifier une entrée passée rompt toute la chaîne qui suit. Un déclencheur en base interdit aussi toute modification ou suppression, et une vérification de la chaîne est accessible au superviseur.

**Q63. Comment le modèle est-il mis à jour ?**
R. Quatre signaux déclenchent le réentraînement (nouvelles étiquettes, dérive des données, comportements nouveaux, demande manuelle), avec un délai minimal de six heures. Un challenger est entraîné, soumis à trois contrôles, à savoir le diagnostic de surapprentissage, la porte de détection (rappel minimal par type de fraude et taux maximal de faux positifs) et la comparaison avec le champion sur la même période. Il n'est promu que s'il fait mieux, puis enregistré dans MLflow et rechargé à chaud.

**Q64. Comment sécurisez-vous la plateforme ?**
R. Authentification par jetons, rôles, double authentification facultative, clés d'API de 256 bits stockées sous forme d'empreinte, quotas par institution, journal inaltérable, double validation pour tout déblocage d'au moins 500 USD, limitation de débit et en-têtes de sécurité à l'entrée Nginx, et configuration de production qui ferme les ports internes.

**Q65. Comment avez-vous testé le système ?**
R. 158 tests automatisés, exécutés à chaque reconstruction complète, puis un contrôle de santé de chaque service et de chaque route, et enfin un rejeu de transactions qui traverse toute la chaîne.

**Q66. Quelles technologies, et pourquoi ?**
R. Toutes libres, sans coût de licence. FastAPI pour l'asynchrone et la documentation OpenAPI automatique, PostgreSQL avec TimescaleDB pour le relationnel et les séries temporelles, Redis, Kafka, Prometheus, Grafana, Loki et MLflow pour la supervision et le suivi des modèles, Kubernetes avec Kustomize pour la mise à l'échelle.

---

## 6. Limites, éthique et perspectives

**Q67. Quelles sont les principales limites ?**
R. Six. Les données sont simulées et leurs fraudes plus nettes que dans la réalité. Un nombre fini d'appareils de fraudeurs et de mules est réutilisé. Seuls 500 clients sont simulés. Le canal carte est très facile à séparer et H5 est circulaire. Les rejeux de la boucle de retour supposent des analystes sans erreur. Les coûts sont fixés par hypothèse.

**Q68. Que se passe-t-il pour un client honnête bloqué à tort ?**
R. Dans les cas intermédiaires, le système fait vérifier au lieu de bloquer. Le client confirme par PIN ou OTP et l'opération passe. Le blocage est réservé aux probabilités très élevées ou aux gros montants. Chaque blocage ouvre un dossier qu'un analyste peut déclarer faux positif, ce qui devient une étiquette de correction.

**Q69. Quelles considérations éthiques ?**
R. Une fausse alerte peut retarder un paiement vital. L'évaluation de l'équité montre que ce coût pèse davantage sur les clients modestes, les agriculteurs et les étudiants. Le système le mesure et l'affiche. Les décisions sont expliquées, le journal d'audit est inaltérable, les données restent sur la plateforme et tout déblocage important exige un second validateur.

**Q70. Pourquoi ne pas utiliser un grand modèle de langage pour les explications ?**
R. Pour la confidentialité (aucune donnée client ne doit quitter la plateforme), pour la connectivité (pas de dépendance à un service en ligne) et pour la fiabilité (un modèle de langage peut inventer). Mes explications viennent uniquement de sources vérifiables.

**Q71. Que faire si les fraudeurs s'adaptent au modèle ?**
R. Les tests adversariaux sont une perspective. Le protocole est rédigé, mais les résultats restent à produire, et je ne les présente pas comme obtenus. Les lois physiques et les règles ne dépendent pas de l'apprentissage, donc elles tiennent même face à une fraude inédite. L'apprentissage continu absorbe la dérive.

**Q72. Quelles sont vos perspectives ?**
R. D'abord la validation sur données réelles d'un opérateur, avec une période d'observation avant tout blocage. Ensuite les tests adversariaux, la recalibration isotonique et les réseaux de neurones sur graphes, puis l'apprentissage fédéré entre opérateurs et l'extension de l'analyse de texte au lingala et au swahili.

---

## 7. Questions pièges du jury

**Q73. « Votre contribution est-elle vraiment originale ? »**
R. Oui, par l'assemblage et le contexte. Je propose un système complet adapté au contexte congolais, avec profilage sans dépendre du smartphone, double monnaie au taux de l'année, lois physiques entre provinces, décision graduée selon le coût, explication sans modèle de langage externe, API ouverte aux opérateurs et au régulateur, et un protocole statistique rigoureux sur un générateur reproductible.

**Q74. « Vos résultats sont-ils applicables en production ? »**
R. Pas directement, et je ne le prétends pas. Ils valent pour le périmètre de la simulation. Le passage en production passe par une validation sur données réelles, d'abord en mode observation.

**Q75. « Pourquoi avoir confirmé les cinq hypothèses au départ, puis nuancé ? »**
R. Les cinq sont confirmées au sens du critère statistique fixé, sur données synthétiques. Après relecture, j'ai distingué ce qui est confirmé (H1, H2, H3) de ce qui est partiellement vérifié (H4 et H5), pour ne pas laisser croire que la transposition et l'évolution des fraudes sont démontrées en réel.

**Q76. « Le deep learning n'est-il pas plus moderne que XGBoost ? »**
R. Sur des données tabulaires, les arbres boostés rivalisent avec les réseaux profonds et sont plus légers et plus explicables. Le LSTM seul égale XGBoost (0,9894 contre 0,9895). C'est leur combinaison qui est significativement meilleure, car le LSTM lit la dynamique des séquences.

**Q77. « Pourquoi vos règles métier sont-elles si faibles ? »**
R. Elles détectent 45 % du fractionnement mais seulement 0,3 % de l'ingénierie sociale, car celle-ci ressemble à un comportement normal. Elles restent utiles comme garde-fou, car elles ne peuvent que durcir une décision et sont auditables.

**Q78. « Le McNemar et le bootstrap disent-ils la même chose ? »**
R. Ils sont complémentaires. Le bootstrap porte sur une métrique globale, la PR-AUC sur tous les seuils, et donne un intervalle de confiance. McNemar porte sur les décisions au seuil retenu, opération par opération. Les deux concluent à la supériorité de l'hybride.

**Q79. « Comment gérez-vous la protection des données personnelles ? »**
R. Les données sont synthétiques et ne contiennent aucune donnée personnelle réelle. Dans le système, le texte des messages n'est jamais stocké en clair, les données restent sur la plateforme, et les droits sont attribués par institution avec un isolement des données.

**Q80. « Que feriez-vous avec six mois de plus ? »**
R. Je négocierais un accès à un échantillon anonymisé d'un opérateur pour valider les résultats sur données réelles, j'exécuterais les tests adversariaux déjà protocolés, et j'augmenterais le nombre de clients simulés pour affiner les intervalles de confiance.

---

## 8. Comprendre les concepts d'IA du mémoire

Cette partie explique, simplement et dans l'ordre logique, chaque concept d'intelligence artificielle utilisé dans le mémoire. Pour chacun, on trouve l'idée en une phrase, une image pour la comprendre, l'exemple du mémoire, la raison du choix et le piège à éviter à l'oral. Lisez-la du début à la fin au moins une fois, car chaque concept s'appuie sur le précédent.

### 8.1 Les bases

**Apprentissage automatique (machine learning)**
- L'idée. Au lieu d'écrire des règles à la main, on montre des exemples à un programme, et il en déduit lui-même les règles.
- L'image. Un enfant apprend à reconnaître un chien en voyant beaucoup de chiens, pas en lisant une définition.
- Dans le mémoire. On montre au modèle des centaines de milliers de transactions déjà étiquetées « fraude » ou « légitime », et il apprend ce qui distingue les deux.
- Le piège. Le modèle ne comprend rien, il repère des régularités statistiques. Si les données sont biaisées ou simulées, ses « règles » le sont aussi.

**Apprentissage supervisé et non supervisé**
- Supervisé. On donne au modèle les exemples et la bonne réponse (l'étiquette). Il apprend à la prédire. Dans le mémoire, ce sont la régression logistique, le Random Forest, XGBoost et le LSTM.
- Non supervisé. On ne donne pas de bonne réponse. Le modèle apprend ce qui est « normal » et signale ce qui s'en écarte. Dans le mémoire, ce sont l'Isolation Forest et l'autoencodeur.
- Pourquoi les deux. Le supervisé est précis sur les fraudes déjà vues. Le non supervisé peut signaler une fraude jamais vue, car il ne dépend pas d'exemples de fraude.
- Le piège. Une fraude qui imite parfaitement le comportement normal n'est pas une anomalie. C'est pourquoi l'autoencodeur seul rate l'ingénierie sociale (rappel de 0,3 %).

**Classification binaire**
- L'idée. Répondre par oui ou non. Ici, fraude ou pas fraude.
- Le modèle ne répond pas directement oui ou non. Il donne d'abord une probabilité entre 0 et 1, puis un seuil transforme cette probabilité en décision.

**Variable (feature) et ingénierie des variables**
- L'idée. Une variable est une information décrivant la transaction que le modèle peut utiliser, comme le montant, l'heure ou la nouveauté de l'appareil. L'ingénierie des variables consiste à les fabriquer intelligemment.
- Dans le mémoire. 58 variables, dont la plupart mesurent un écart au comportement habituel du client plutôt qu'une valeur brute.
- Pourquoi. Un montant de 200 USD est normal pour un commerçant et alarmant pour un étudiant. La même valeur brute n'a pas le même sens. La variable utile est « combien ce montant s'écarte de ce que ce client fait d'habitude ».
- Le piège. Une bonne variable vaut souvent plus qu'un modèle sophistiqué. L'ablation (voir plus bas) le montre, car retirer les variables de contexte fait chuter la PR-AUC de 0,989 à 0,843.

### 8.2 Préparer les données sans tricher

**Découpage apprentissage, validation, test**
- L'idée. On divise les données en trois parties. L'apprentissage sert à entraîner, la validation à régler (par exemple choisir le seuil), le test à juger une seule fois à la fin.
- L'image. Un élève s'entraîne avec des exercices, révise avec un examen blanc, puis passe l'examen final dont il n'a jamais vu les questions.
- Dans le mémoire. Découpage chronologique, avec un test du 13 décembre 2024 au 31 décembre 2025 (183 240 transactions dont 2 437 fraudes).
- Pourquoi chronologique. En production, on prédit l'avenir avec le passé. Un tirage aléatoire mélangerait le futur dans l'apprentissage et donnerait des résultats trop beaux.
- Le piège. Si l'on règle quelque chose sur le test, il n'est plus un vrai test. Le seuil du mémoire (0,538) est fixé sur la validation, jamais sur le test.

**Fuite d'information (data leakage)**
- L'idée. Donner au modèle, sans le vouloir, une information qu'il n'aurait pas en réalité au moment de décider.
- Exemple. Calculer le « montant habituel » d'un client en incluant les opérations futures. Le modèle verrait l'avenir.
- Dans le mémoire. Chaque variable n'utilise que le passé de la transaction, et le même code calcule les variables à l'entraînement et en production.

**Normalisation**
- L'idée. Ramener des variables d'échelles très différentes (un montant en dollars, un nombre d'opérations, une heure) à une échelle comparable, pour que le modèle ne favorise pas celles qui ont de grands nombres. On centre sur la moyenne et on divise par l'écart-type.
- Surtout utile pour les réseaux de neurones et la régression logistique, moins pour les arbres.

**Logarithme des montants et z-score**
- Le problème. Les montants sont très asymétriques, avec beaucoup de petits montants et quelques très gros. En Mobile Money, la médiane légitime est de 24,11 USD et le 99e centile de 276 USD.
- Le logarithme. Il rapproche les gros montants des petits et rend la distribution plus symétrique.
- Le z-score. Il dit à combien d'écarts-types un montant se trouve de la moyenne habituelle du client. Un z-score de 0 veut dire « comme d'habitude », un z-score de 4 veut dire « très inhabituel pour cette personne ».
- Dans le mémoire. L'écart logarithmique au montant habituel du client est l'une des variables phares.

**Déséquilibre des classes**
- Le problème. 1,33 % de fraudes, soit une fraude pour 74 opérations légitimes. Un modèle qui dit toujours « légitime » a 98,67 % d'exactitude et ne sert à rien.
- Deux remèdes dans le mémoire. XGBoost donne à chaque fraude un poids d'environ 74 dans sa fonction de perte, donc une erreur sur une fraude coûte autant que 74 erreurs sur du légitime. Le LSTM, lui, ne garde que 30 % des opérations légitimes à chaque époque.
- Le piège. L'exactitude (accuracy) est une mauvaise métrique ici. On utilise la PR-AUC.

### 8.3 Les modèles, du plus simple au plus riche

**Règles métier (système expert)**
- L'idée. Des conditions écrites à la main, du type « si le montant dépasse un seuil, alors alerte ».
- Dans le mémoire. Elles servent de référence statique, avec 0,2726 de PR-AUC, et de garde-fou en production, car elles ne peuvent que durcir une décision.
- Force et faiblesse. Transparentes et auditables, mais elles ignorent l'individu et se contournent, par exemple en fractionnant sous un seuil.

**Régression logistique**
- L'idée. Un modèle linéaire qui combine les variables avec des poids, puis transforme le résultat en probabilité entre 0 et 1.
- Pourquoi la garder. Simple, rapide, très explicable. C'est la référence « modèle classique ».
- Limite. Elle ne capte que des relations linéaires, alors que la fraude combine des signaux de façon complexe.

**Arbre de décision et Random Forest**
- Arbre. Une suite de questions oui ou non (« le destinataire est-il nouveau ? le montant est-il supérieur à 3 fois l'habituel ? ») qui conduit à une décision.
- Random Forest. On construit beaucoup d'arbres différents sur des échantillons aléatoires et on les fait voter. La moyenne de nombreux arbres est plus stable qu'un seul.

**Boosting et XGBoost**
- L'idée. Au lieu de construire les arbres en parallèle, on les construit l'un après l'autre. Chaque nouvel arbre se concentre sur les erreurs des précédents.
- L'image. Une équipe où chaque nouveau membre est recruté pour corriger ce que les autres ratent.
- Pourquoi c'est la référence. Sur des données en tableau, XGBoost est très performant, rapide et explicable. Dans le mémoire, il atteint 0,9895 de PR-AUC. Les études comme Hájek et al. le citent comme robuste pour les paiements mobiles.

**Isolation Forest**
- L'idée. Non supervisé. Il isole les points en coupant l'espace au hasard. Un point étrange est isolé en très peu de coupes, un point banal en demande beaucoup. Peu de coupes veut dire anomalie.
- Résultat dans le mémoire. Il ne détecte que 39 % des fraudes, ce qui montre que la fraude n'est pas seulement « bizarre ».

**Autoencodeur**
- L'idée. Un réseau de neurones qui apprend à compresser puis reconstruire des données normales. Si on lui présente une opération anormale, il la reconstruit mal, et cette erreur de reconstruction sert de score d'anomalie.
- L'image. Un copiste qui n'a recopié que des textes en français. Face à du chinois, il fait des fautes énormes, et ces fautes le trahissent.
- Rôle dans l'hybride. Peu utile seul sur les fraudes connues, mais c'est la seule composante qui signale la nouveauté. Il réduit aussi les fausses alertes.

**Réseau de neurones et LSTM**
- Réseau de neurones. Des couches de petites unités de calcul qui transforment les données et apprennent leurs poids par essais successifs.
- LSTM. Un réseau récurrent conçu pour lire des séquences, comme l'historique des opérations d'un client. Il possède une « mémoire » qui décide quoi retenir et quoi oublier.
- Pourquoi dans le mémoire. Une fraude est souvent une dynamique, par exemple une escalade de montants ou une salve d'opérations. Un LSTM lit cette dynamique, qu'un résumé instantané décrit mal.

**Attention**
- L'idée. Le modèle apprend à pondérer l'importance de chaque opération passée. Il « regarde » davantage celles qui comptent pour la décision.
- Intérêt. Les poids d'attention servent aussi d'explication, car ils montrent quelles opérations passées ont pesé.

**Modèle hybride et empilement (stacking)**
- L'idée. Combiner plusieurs modèles différents. Un méta-apprenant apprend à pondérer leurs sorties.
- Dans le mémoire. XGBoost, LSTM et autoencodeur alimentent un méta-apprenant. Il leur attribue des coefficients de 1,69 pour XGBoost, 1,56 pour le LSTM et 0,46 pour l'autoencodeur.
- Pourquoi ça marche. Les composantes ne se trompent pas sur les mêmes opérations. Sur 179 opérations où l'hybride et XGBoost divergent, l'hybride a raison 156 fois.
- Le piège. Le gain en PR-AUC est modeste (0,006) mais il se traduit par 42 % de fausses alertes et 45 % de fraudes manquées en moins.

### 8.4 Mesurer la qualité

**Matrice de confusion et les quatre cas**
Sur le jeu de test du mémoire (183 240 opérations dont 2 437 fraudes), le modèle hybride donne ceci.

| | Fraude réelle | Légitime réelle |
|---|---|---|
| Alerte du modèle | 2 383 (vrais positifs) | 122 (faux positifs) |
| Pas d'alerte | 54 (faux négatifs) | 180 681 (vrais négatifs) |

**Précision, rappel, F1**
- Précision. Parmi les alertes, combien sont de vraies fraudes. 2 383 sur 2 505, soit 95,1 %. Elle mesure la gêne causée aux honnêtes gens.
- Rappel. Parmi les fraudes, combien sont détectées. 2 383 sur 2 437, soit 97,8 %. Il mesure les fraudes laissées passer.
- F1. Une moyenne harmonique des deux. Elle est basse si l'un des deux est bas. Ici 0,964.
- Le compromis. Monter le rappel baisse en général la précision. Le seuil règle ce compromis.

**MCC (coefficient de Matthews)**
- L'idée. Une note unique de 1 (parfait) à -1 qui tient compte des quatre cases de la matrice. Elle est robuste quand les classes sont déséquilibrées.
- Dans le mémoire. 0,964 pour l'hybride, 0,766 pour l'autoencodeur seul, ce qui montre que sa bonne précision cachait des fraudes manquées.

**Seuil de décision**
- L'idée. Le modèle sort une probabilité. Le seuil dit à partir de quelle probabilité on déclenche l'alerte.
- Dans le mémoire. 0,538, choisi pour maximiser le F1 sur la validation. Sur le test, le F1 varie de moins d'un point entre 0,45 et 0,75, donc le choix est robuste.

**Courbe ROC et ROC-AUC contre courbe PR et PR-AUC**
- ROC-AUC. Compare le taux de fraudes détectées au taux de fausses alertes sur tous les seuils. Avec très peu de fraudes, le taux de fausses alertes reste minuscule même avec beaucoup de faux positifs en valeur absolue, donc la ROC-AUC paraît toujours excellente.
- PR-AUC. Compare la précision et le rappel sur tous les seuils. Elle se concentre sur la classe rare, donc elle punit vraiment les fausses alertes.
- La preuve dans le mémoire. L'Isolation Forest a une ROC-AUC supérieure à 0,95 alors qu'il ne détecte que 39 % des fraudes. D'où le choix de la PR-AUC comme métrique principale.
- Repère. Un modèle au hasard a une PR-AUC égale à la proportion de fraudes, ici 1,33 %. L'hybride est à 99,55 %.

**Rappel à budget de fausses alertes fixé**
- L'idée. Un opérateur ne peut traiter qu'un nombre limité d'alertes. On mesure donc le rappel quand on n'autorise que 0,05 %, 0,1 %, 0,5 % ou 1 % de fausses alertes.
- Dans le mémoire. À 0,05 %, l'hybride détecte 96,9 % des fraudes contre 92,3 % pour XGBoost. L'avantage est le plus fort quand le budget est serré.

**Calibration et score de Brier**
- Calibration. Une probabilité est calibrée si, parmi les opérations notées 0,8, environ 80 % sont réellement des fraudes.
- Score de Brier. La moyenne des carrés des écarts entre probabilité et réalité. Plus il est bas, mieux c'est. Ici 0,00077.
- Nuance. Dans la zone intermédiaire, la probabilité prédite surestime le taux réel. Une opération notée 0,45 n'est pas fraudeuse une fois sur deux.

### 8.5 Prouver que ce n'est pas le hasard

**Intervalle de confiance et bootstrap**
- Intervalle de confiance. Une fourchette dans laquelle se trouve probablement la vraie valeur. Un écart dont l'intervalle ne contient pas zéro est jugé réel.
- Bootstrap. On refait le calcul des centaines de fois sur des échantillons tirés au hasard avec remise, et on observe comment le résultat varie.
- Dans le mémoire. 1 000 tirages, et un tirage par client entier et non par transaction. Les transactions d'un même client se ressemblent, donc les mélanger gonflerait artificiellement la confiance.

**Test de McNemar**
- L'idée. On ne regarde que les opérations où deux modèles ne sont pas d'accord, et on teste si l'un a raison plus souvent que l'autre.
- Dans le mémoire. « 156 contre 23 » veut dire que l'hybride a raison 156 fois et XGBoost 23 fois. L'écart est loin de ce que le hasard donnerait.
- Différence avec le bootstrap. Le bootstrap porte sur une métrique globale. McNemar porte sur les décisions au seuil retenu.

**Variance selon la graine**
- L'idée. Les modèles contiennent du hasard (initialisation, tirages). On relance avec plusieurs graines pour voir si le résultat tient. Dans le mémoire, la PR-AUC du profilage varie de 0,9895 à plus ou moins 0,0004 seulement.

**Ablation**
- L'idée. Retirer une pièce et mesurer ce qu'on perd. Si la performance chute, la pièce est utile.
- Dans le mémoire. Retirer une composante de l'hybride dégrade toujours le résultat. Retirer les variables contextuelles fait passer la PR-AUC de 0,989 à 0,843. Retirer les variables temporelles ne change presque rien, car elles sont redondantes.

**Surapprentissage (overfitting)**
- L'idée. Le modèle apprend par cœur les données d'entraînement, y compris leur bruit, et généralise mal.
- L'image. Un élève qui mémorise les corrections au lieu de comprendre.
- Détection. On compare la performance à l'entraînement et sur des données jamais vues. Dans le mémoire, XGBoost et le LSTM montrent un léger surapprentissage, sans perte de performance sur le test (écart de PR-AUC de 0,006).

### 8.6 Les compléments du système

**Explicabilité, SHAP et TreeSHAP**
- Pourquoi. Dans la finance, il ne suffit pas de dire « fraude ». Il faut pouvoir justifier devant un client, un analyste ou le régulateur.
- SHAP. Une méthode qui attribue à chaque variable sa contribution à la décision, en s'inspirant de la théorie des jeux. TreeSHAP en donne la valeur exacte pour les modèles à arbres.
- Lecture. « L'appareil est nouveau, ce qui ajoute beaucoup de risque. Le montant est habituel, ce qui en retire un peu. »
- Dans le mémoire. S'y ajoutent la contribution de chaque composante, les poids d'attention et les cas passés similaires.

**Recherche de cas similaires**
- L'idée. Retrouver, dans l'historique, les cas les plus proches de l'opération à juger et regarder leur verdict.
- Dans le mémoire. Quand les cas proches confirment une alerte, elle est fondée dans 98 % des cas. Quand ils la contredisent, elle ne l'est plus que dans 60,9 %. C'est un contrôle de cohérence pour l'analyste.

**Décision selon le coût**
- L'idée. Choisir l'action (laisser passer, vérifier, bloquer) qui minimise la perte attendue, au lieu d'appliquer un seuil unique.
- Pourquoi. Laisser passer une fraude coûte son montant. Bloquer un honnête coûte peu, vérifier coûte encore moins. Ces coûts sont asymétriques.
- Résultat. La perte passe de 2 354 à 1 017 USD, avec 99,9 % des fraudes stoppées. Le résultat découle de l'asymétrie des coûts et ne dépend pas de la simulation, mais les montants de coût sont des hypothèses.

**Lois physiques**
- L'idée. Des contraintes que le monde réel impose. On ne peut pas faire Kinshasa puis le Haut-Katanga en trois minutes. Ces règles ne dépendent pas de l'apprentissage.
- Intérêt. Elles couvrent ce que le modèle n'a jamais vu. Face à une attaque inédite, le modèle voit 0,3 % des cas, les lois physiques 100 %.

**Analyse de réseau**
- L'idée. Représenter comptes, appareils et destinataires comme un graphe. Un destinataire qui reçoit l'argent de plusieurs victimes est suspect, même si chaque victime paye seule.
- Dans le mémoire. L'analyse récupère 54 fraudes que le modèle avait manquées, surtout de l'ingénierie sociale.

**Traitement du langage (NLP) sur les messages**
- L'idée. Repérer des signes de manipulation dans un texte, par mots-clés et indices pondérés, sans modèle de langage externe.
- Résultat. Précision de 1,00 sans fausse alerte, rappel de 0,73. Le texte seul impose une vérification, jamais un blocage.

**Apprentissage actif et boucle de retour**
- L'idée. Faire revoir par les analystes les cas où le modèle hésite, puisque c'est là qu'une étiquette humaine apporte le plus.
- Résultat. Les fraudes manquées passent de 73 à 38 avec les verdicts pondérés par trois.
- Échantillon témoin. Un petit tirage aléatoire revu par des humains permet de mesurer sans biais le taux de fraudes manquées.

**Dérive et apprentissage continu**
- Dérive. Les données évoluent (nouveaux comportements, nouvelles fraudes) et le modèle figé se dégrade.
- Apprentissage continu. On surveille la dérive et on réentraîne.
- Champion et challenger. Le champion est le modèle en production. Le challenger est un candidat entraîné sur les données récentes. Il ne le remplace que s'il fait mieux sur la même période.
- Attention à H5. Dans le mémoire, l'évolution des fraudes est un paramètre du générateur. Le résultat montre que la mise à jour fonctionne, pas que les fraudes réelles évolueront ainsi.

**Équité**
- L'idée. Vérifier que les erreurs ne pèsent pas plus sur certains groupes.
- Dans le mémoire. Le rappel reste proche de 100 % partout, mais les clients modestes reçoivent 2,3 fois plus de fausses alertes et les agriculteurs 3,3 fois plus que les commerçants. Cela s'explique en partie par leur taux de fraude de base plus élevé, mais c'est un coût inégal à surveiller.

### 8.7 Deux idées qui reviennent dans tout le mémoire

**Données synthétiques, effet plafond et circularité**
- Données synthétiques. Produites par un générateur. Utiles quand les données réelles sont inaccessibles, mais elles reflètent les hypothèses de celui qui les écrit.
- Effet plafond. Quand la tâche est si facile que tous les modèles approchent de 100 %, la mesure ne permet plus de les distinguer. C'est le cas de la carte virtuelle simulée.
- Circularité. Quand le résultat est en partie imposé par la manière dont les données ont été fabriquées. C'est le cas de H5.
- Pourquoi c'est important. Ces trois notions expliquent pourquoi trois hypothèses sont « confirmées » et deux seulement « partiellement vérifiées », et pourquoi la validation sur données réelles est la première perspective.

**Défense en profondeur**
- L'idée. Ne pas compter sur une seule couche. Le modèle, les lois physiques, l'analyse de réseau, les règles et l'analyste se complètent. Chaque couche couvre les angles morts des autres.
- La phrase à retenir. Le modèle appris ne suffit pas à lui seul.

---

## 9. Glossaire express

| Terme | Sens |
|---|---|
| Profilage comportemental | Modéliser les habitudes de chaque client pour repérer les ruptures |
| PR-AUC | Aire sous la courbe précision-rappel, adaptée aux classes déséquilibrées |
| ROC-AUC | Aire sous la courbe ROC, trompeuse quand la classe rare est très rare |
| MCC | Coefficient de corrélation de Matthews, mesure équilibrée de la classification |
| Rappel | Part des fraudes détectées parmi toutes les fraudes |
| Précision | Part des alertes qui sont réellement des fraudes |
| Stacking (empilement) | Combiner plusieurs modèles par un méta-apprenant |
| LSTM | Réseau récurrent qui lit des séquences |
| Autoencodeur | Réseau non supervisé qui signale ce qui s'écarte du normal |
| TreeSHAP | Explication exacte de la contribution de chaque variable pour les arbres |
| Bootstrap apparié | Rééchantillonnage pour obtenir un intervalle de confiance sur un écart |
| McNemar | Test sur les décisions divergentes de deux modèles |
| Effet plafond | Résultat proche du maximum qui ne permet plus de discriminer |
| Circularité | Résultat en partie imposé par la manière dont les données ont été générées |
| Idempotence | Rejouer la même requête donne la même réponse sans effet double |
| CQRS | Séparation stricte des modèles d'écriture et de lecture, non retenue ici |
| Champion / challenger | Modèle en production et modèle candidat à le remplacer |
| Dérive | Changement des données qui dégrade un modèle figé |
| KYC | Connaissance du client, avec des plafonds de montant |
| USSD | Canal de téléphonie mobile sans smartphone |
