# Formules mathématiques du système

Toutes les formules ci-dessous correspondent au code du dépôt (fichier indiqué pour chaque section). Elles sont écrites
en LaTeX (`$…$`) et peuvent être reprises telles quelles dans le mémoire.

---

## 0. Notations

| Symbole | Signification |
|---|---|
| $u$ | client (titulaire du portefeuille ou de la carte) |
| $x_t$ | transaction du client à l'instant $t$ |
| $a_t$ | montant en USD de la transaction |
| $B_t$ | solde avant la transaction |
| $n_u$ | nombre de transactions passées du client |
| $\mathcal{H}_u(t,\Delta)$ | transactions du client dans la fenêtre $]t-\Delta, t]$ |
| $y \in \{0,1\}$ | étiquette (1 = fraude) |
| $p$ | probabilité de fraude prédite |
| $\sigma(z)=\frac{1}{1+e^{-z}}$ | fonction logistique |

---

## 1. Variables de profilage comportemental (`ml/features/feature_engineering.py`)

Chaque variable est calculée **uniquement à partir du passé** du client (rejeu chronologique), ce qui évite toute fuite
d'information.

### 1.1 Écart au montant habituel

Moyenne et écart-type du logarithme des montants passés :

$$\mu_u=\frac{1}{n_u}\sum_{i=1}^{n_u}\ln(1+a_i),\qquad
s_u=\sqrt{\max\Big(\tfrac{1}{n_u}\sum_i \ln^2(1+a_i)-\mu_u^2,\;0\Big)}+0{,}25$$

$$z_{\text{montant}}=\operatorname{clip}\!\left(\frac{\ln(1+a_t)-\mu_u}{s_u},\,-10,\,10\right)\quad(n_u\ge 3)$$

Rapport au montant moyen : $\;r_t=\ln\!\Big(1+\dfrac{a_t}{\bar a_u+10^{-6}}\Big)$, avec $\bar a_u$ le montant moyen.

### 1.2 Solde et plafond

$$\text{part du solde}=\min\!\Big(\frac{a_t}{B_t+1},\,5\Big),\qquad
\text{vidage}=\mathbb{1}\big[B_t>1 \wedge a_t\ge 0{,}85\,B_t\big],\qquad
\text{plafond KYC}=\frac{a_t}{L_{\text{KYC}}}$$

### 1.3 Vélocité (fréquence)

$$N_\Delta(t)=\big|\mathcal{H}_u(t,\Delta)\big|,\quad \Delta\in\{1\,\text{h},\,24\,\text{h},\,7\,\text{j}\},\qquad
S_{24\text{h}}=\ln\!\Big(1+\sum_{i\in\mathcal{H}_u(t,24\text{h}),\ \text{débit}}a_i\Big)$$

$$\text{délai}=\ln\big(1+\max(t-t_{\text{préc}},0)\big)\quad(\text{en secondes})$$

### 1.4 Contexte (nouveauté)

$$\text{nouvel appareil}=\mathbb{1}[n_u>0 \wedge d_t\notin D_u],\qquad
\text{destinataire lié}=\ln\big(1+|\{v\neq u:\ v \text{ a échangé avec } c_t\}|\big)$$

(même principe pour la province, l'agent et le marchand ; les comptes « mules » apparaissent comme des destinataires liés à
de nombreux clients).

### 1.5 Variables temporelles

Heure cyclique : $\;\theta_t=\dfrac{2\pi h_t}{24},\qquad (\sin\theta_t,\ \cos\theta_t)$

Habitude nocturne lissée : $\;\rho_u=\dfrac{N_u^{\text{nuit}}+0{,}05}{n_u+1},\qquad
\text{nuit inhabituelle}=\mathbb{1}[h_t\le 5]\,(1-\rho_u)$

Écart à l'heure habituelle (statistique circulaire) :

$$\bar C=\tfrac1{n_u}\sum_i\cos\theta_i,\quad \bar S=\tfrac1{n_u}\sum_i\sin\theta_i,\quad R=\sqrt{\bar C^2+\bar S^2},\quad
\bar\theta=\operatorname{atan2}(\bar S,\bar C)$$

$$\delta_t=\min\big(|\theta_t-\bar\theta| \bmod 2\pi,\ 2\pi-|\theta_t-\bar\theta| \bmod 2\pi\big),\qquad
\text{écart horaire}=\frac{\delta_t}{\pi}\,R\quad(R>0{,}1)$$

### 1.6 Normalisation

$$\tilde x_j=\operatorname{clip}\!\left(\frac{x_j-m_j}{\sigma_j},\,-10,\,10\right)$$

$m_j$ et $\sigma_j$ sont estimés sur la période d'entraînement uniquement.

---

## 2. Modèle hybride (`ml/models/`)

### 2.1 Branche XGBoost (profil instantané)

Modèle additif de $K$ arbres : $\;F(\tilde x)=\sum_{k=1}^{K}f_k(\tilde x)$, avec le score brut (logit) $s_{\text{XGB}}=F(\tilde x)$.

Objectif minimisé (perte logistique pondérée et régularisée) :

$$\mathcal{L}=\sum_i w_i\Big[-y_i\ln\sigma(F_i)-(1-y_i)\ln\big(1-\sigma(F_i)\big)\Big]+\sum_k\Omega(f_k),\qquad
w_i=\begin{cases}N^-/N^+ & y_i=1\\ 1 & y_i=0\end{cases}$$

où $\Omega(f)=\gamma T+\tfrac12\lambda\lVert w\rVert^2$ ($T$ feuilles). L'arrêt précoce se fait sur la PR-AUC de la
tranche *early_stop*.

### 2.2 Branche LSTM + attention (séquence)

Séquence des $L=10$ dernières transactions $(\tilde x_{t-9},\dots,\tilde x_t)$. Cellule LSTM :

$$\begin{aligned}
i_\tau&=\sigma(W_i x_\tau+U_i h_{\tau-1}+b_i), & f_\tau&=\sigma(W_f x_\tau+U_f h_{\tau-1}+b_f),\\
o_\tau&=\sigma(W_o x_\tau+U_o h_{\tau-1}+b_o), & g_\tau&=\tanh(W_g x_\tau+U_g h_{\tau-1}+b_g),\\
c_\tau&=f_\tau\odot c_{\tau-1}+i_\tau\odot g_\tau, & h_\tau&=o_\tau\odot\tanh(c_\tau).
\end{aligned}$$

Attention (les positions vides sont masquées) :

$$e_\tau=v^\top\tanh(W_a h_\tau+b_a),\qquad
\alpha_\tau=\frac{e^{e_\tau}}{\sum_{\tau'}e^{e_{\tau'}}},\qquad c=\sum_\tau\alpha_\tau h_\tau$$

$$s_{\text{LSTM}}=\operatorname{MLP}\big([\,c\,;\,h_L\,]\big)$$

Perte : entropie croisée pondérée, $\;w^+=\sqrt{N^-_{\text{échantillonnés}}/N^+}$, les légitimes étant sous-échantillonnés
(30 %) à chaque époque. Les poids $\alpha_\tau$ servent d'explication (transactions passées qui ont compté).

### 2.3 Branche autoencodeur (anomalie)

Encodeur et décodeur $58\to32\to16\to8\to16\to32\to58$, entraînés **sur les seules transactions légitimes** :

$$\min_\phi\ \frac{1}{N}\sum_i\big\lVert \tilde x_i-g_\phi(\tilde x_i)\big\rVert_2^2,\qquad
s_{\text{AE}}=\ln\!\Big(\tfrac{1}{58}\lVert \tilde x-g_\phi(\tilde x)\rVert_2^2+10^{-6}\Big)$$

### 2.4 Méta-apprenant (empilement)

Scores standardisés sur la validation : $\;z_k=\dfrac{s_k-\mu_k}{\sigma_k},\ k\in\{\text{XGB},\text{LSTM},\text{AE}\}$

$$p=\sigma\Big(\beta_0+\sum_k\beta_k z_k\Big),\qquad \text{contribution de la branche }k=\beta_k z_k$$

### 2.5 Seuil de décision

$$\tau^*=\arg\max_\tau F_1(\tau)=\arg\max_\tau\frac{2\,P(\tau)\,R(\tau)}{P(\tau)+R(\tau)}\quad\text{(sur la validation)}$$

### 2.6 Explication SHAP (XGBoost, TreeSHAP exact)

$$F(\tilde x)=\phi_0+\sum_{j=1}^{58}\phi_j,\qquad
\phi_j=\sum_{S\subseteq M\setminus\{j\}}\frac{|S|!\,(|M|-|S|-1)!}{|M|!}\big[F_{S\cup\{j\}}(\tilde x)-F_S(\tilde x)\big]$$

---

## 3. Décision coût-sensible (`ml/serving/decision.py`)

Pour une probabilité $p$, un montant $m$ et les paramètres du canal (friction $c_f$, taux de capture $\kappa$, coût fixe
d'un blocage à tort $c_b$, part du montant perdue $\lambda$) :

$$\begin{aligned}
\mathbb{E}[\text{coût}\mid\text{APPROVE}]&=p\,m\\
\mathbb{E}[\text{coût}\mid\text{VERIFY}]&=c_f+p\,m\,(1-\kappa)\\
\mathbb{E}[\text{coût}\mid\text{BLOCK}]&=(1-p)\,(c_b+\lambda m)
\end{aligned}
\qquad a^*=\arg\min_a\mathbb{E}[\text{coût}\mid a]$$

Exceptions : BLOCK si $p\ge 0{,}97$ ; APPROVE si $p<0{,}01$. Les règles métier et physiques ne peuvent que renforcer
l'action. Niveau de risque : CRITIQUE si $p\ge\max(0{,}9,\tau^*)$, ÉLEVÉ si $p\ge\tau^*$, MOYEN si $p\ge\tau^*/5$, FAIBLE sinon.

---

## 4. Typologie de fraude (`ml/training/train_fraud_type.py`)

Classifieur multiclasse (XGBoost, softmax) sur les transactions frauduleuses :

$$P(k\mid\tilde x)=\frac{e^{F_k(\tilde x)}}{\sum_{k'}e^{F_{k'}(\tilde x)}}$$

Restriction aux typologies possibles pour le canal $\mathcal{K}_c$, puis renormalisation :

$$\hat P(k\mid\tilde x,c)=\frac{P(k\mid\tilde x)\,\mathbb{1}[k\in\mathcal{K}_c]}{\sum_{k'\in\mathcal{K}_c}P(k'\mid\tilde x)},\qquad
\hat k=\arg\max_k\hat P(k\mid\tilde x,c)$$

---

## 5. Lois physiques (`ml/physics/laws.py`)

### 5.1 Cinématique

Distance de grand cercle (haversine), $R_\oplus=6371$ km :

$$d=2R_\oplus\arcsin\sqrt{\sin^2\!\tfrac{\varphi_2-\varphi_1}{2}+\cos\varphi_1\cos\varphi_2\sin^2\!\tfrac{\lambda_2-\lambda_1}{2}}$$

Durée minimale physiquement possible (route $v_r=80$ km/h ; avion $v_a=800$ km/h et $t_0=2$ h de formalités) :

$$t_{\min}(d)=\min\Big(\frac{d}{v_r},\ t_0+\frac{d}{v_a}\Big)$$

Infaisabilité, avec $\Delta t$ le temps écoulé depuis la dernière opération du client :

$$I=\max\Big(0,\ \frac{t_{\min}(d)}{\Delta t}-1\Big)\qquad(I=0:\ \text{faisable};\ I\ge 1:\ \text{violation nette})$$

### 5.2 Conservation

$$D=\frac{\max(0,\ a_t-B_t)}{a_t},\qquad
\tau_{\text{vidage}}=\frac{B_t}{Q},\quad Q=\sum_{i\in\mathcal{H}_u(t,1\text{h}),\ \text{débit}}a_i+a_t\quad(\text{USD/h})$$

### 5.3 Score physique

$$S_{\text{phys}}=\max\Big(\min\big(1,\ \tfrac{\ln(1+I)}{\ln 11}\big),\ \min(1,D)\Big)$$

---

## 6. Mémoire de cas – RAG (`shared/rag/retriever.py`)

Distance et similarité, avec $d_{\text{réf}}$ la distance médiane au plus proche voisin dans l'index :

$$d(x,x_i)=\lVert\tilde x-\tilde x_i\rVert_2,\qquad \operatorname{sim}_i=\frac{1}{1+d(x,x_i)/d_{\text{réf}}}$$

Part de fraude parmi les $k$ plus proches voisins, pondérée par la similarité et par le poids d'importance $\omega_i$ :

$$\pi=\frac{\sum_{i=1}^{k}\operatorname{sim}_i\,\omega_i\,y_i}{\sum_{i=1}^{k}\operatorname{sim}_i\,\omega_i},\qquad
\omega_i=\begin{cases}1 & y_i=1\\ N^-_{\text{réel}}/N^-_{\text{gardé}} & y_i=0\end{cases}$$

Cohérence : COHÉRENT si $\mathbb{1}[\pi\ge 0{,}5]=\mathbb{1}[p\ge\tau^*]$, DIVERGENT sinon, INSUFFISANT si la similarité moyenne
est inférieure à 0,2.

---

## 7. Analyse de texte – NLP (`shared/nlp/analyzer.py`)

Score d'ingénierie sociale (« ou bruité » sur les catégories d'indices détectées $\mathcal{C}$, de poids $w_c$) :

$$S_{\text{IS}}=1-\prod_{c\in\mathcal{C}}(1-w_c)$$

Polarité du sentiment ($n^+$, $n^-$ : indices positifs et négatifs, une négation inverse l'indice avec un poids 0,5) :

$$\text{pol}=\frac{n^+-n^-}{n^++n^-+1},\qquad \text{NÉGATIF si pol}\le-0{,}2,\ \text{POSITIF si pol}\ge 0{,}2$$

---

## 8. Évaluation (`ml/training/evaluation.py`, `significance.py`)

### 8.1 Métriques

$$P=\frac{TP}{TP+FP},\quad R=\frac{TP}{TP+FN},\quad F_1=\frac{2PR}{P+R},\quad FPR=\frac{FP}{FP+TN}$$

PR-AUC (précision moyenne, sur les seuils triés) :

$$\text{AP}=\sum_n (R_n-R_{n-1})\,P_n$$

Rappel à 1 % de faux positifs : $\;R@1\%=\max\{TPR(\tau):\ FPR(\tau)\le 0{,}01\}$

### 8.2 Intervalles de confiance (bootstrap apparié par usager)

On tire $B$ fois les **usagers** avec remise (les transactions d'un même usager restent groupées), on recalcule la métrique
$\hat\theta^{(b)}$ de chaque modèle sur le même échantillon, puis :

$$IC_{95\%}=\big[\hat\theta_{(2{,}5\%)},\ \hat\theta_{(97{,}5\%)}\big],\qquad
\Delta^{(b)}=\hat\theta_A^{(b)}-\hat\theta_B^{(b)},\qquad
p=2\min\Big(\tfrac1B\sum_b\mathbb{1}[\Delta^{(b)}\le0],\ \tfrac1B\sum_b\mathbb{1}[\Delta^{(b)}\ge0]\Big)$$

La différence est significative si l'IC à 95 % de $\Delta$ ne contient pas 0.

### 8.3 Test de McNemar exact

Avec $b$ (seul A a raison) et $c$ (seul B a raison), test binomial bilatéral sous $H_0$ : « A et B se trompent aussi
souvent l'un que l'autre » :

$$X\sim\mathcal{B}\big(b+c,\ \tfrac12\big),\qquad p=\min\Big(1,\ 2\,P\big(X\le\min(b,c)\big)\Big)$$

### 8.4 Transposition Mobile Money → Visa (H4)

$$\text{rapport de transfert}=\frac{\text{PR-AUC}_{\text{Visa}}(\text{modèle Mobile Money seul})}{\text{PR-AUC}_{\text{Visa}}(\text{modèle mixte})},\qquad
\text{gain sur le hasard}=\frac{\text{PR-AUC}}{\text{prévalence}}$$

### 8.5 Évolution dans le temps (H5)

Pour chaque année évaluée $Y$ : $\;\Delta_Y=\text{PR-AUC}_Y(\text{réentraîné})-\text{PR-AUC}_Y(\text{figé})$, puis la pente de la
droite des moindres carrés $\Delta_Y=\alpha+\beta Y$ ($\beta>0$ : l'écart se creuse).

---

## 9. Dérive et nouveaux comportements (`ml/monitoring/drift_detector.py`)

Kolmogorov-Smirnov : $\;D=\sup_x|F_{\text{réf}}(x)-F_{\text{prod}}(x)|$

Population Stability Index sur $K$ classes (quantiles de la référence) :

$$\text{PSI}=\sum_{k=1}^{K}(q_k-r_k)\ln\frac{q_k}{r_k}$$

Variable en dérive si $(D>0{,}1 \wedge p_{KS}<0{,}01)$ ou $\text{PSI}>0{,}2$.

Taux de nouveauté (autoencodeur), $Q_{0{,}99}$ étant le 99ᵉ centile de $s_{\text{AE}}$ sur la référence :

$$\nu=\frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\big[s_{\text{AE},i}>Q_{0{,}99}\big],\qquad \text{alarme si }\nu\ge 0{,}04\ (\text{attendu}:\ 0{,}01)$$

---

## 10. Diagnostic d'apprentissage (`ml/training/diagnostics.py`)

À l'époque retenue $b$ par l'arrêt précoce :

$$G=\frac{\mathcal{L}_{\text{val}}(b)-\mathcal{L}_{\text{ent}}(b)}{\mathcal{L}_{\text{ent}}(b)},\qquad
M=\text{PR-AUC}_{\text{ent}}(b)-\text{PR-AUC}_{\text{val}}(b),\qquad
R=\frac{\mathcal{L}_{\text{val}}(\text{fin})-\min\mathcal{L}_{\text{val}}}{\min\mathcal{L}_{\text{val}}}$$

Surapprentissage net si $M>0{,}05$ (ou $G>1$ sans PR-AUC) ; léger si $M>0{,}02$, $G>0{,}3$, ou $R>5\,\%$ avec une perte
d'entraînement en baisse.

---

## 11. Conversion monétaire (`shared/utils/fx.py`)

$$a^{\text{USD}}_t=\begin{cases}a_t & \text{devise USD}\\[2pt] \dfrac{a_t}{\text{taux}_{\text{USD/CDF}}(\text{année}(t))} & \text{devise CDF}\end{cases}$$

(taux annuels approximatifs, paramètres de simulation à remplacer par le cours officiel BCC.)
