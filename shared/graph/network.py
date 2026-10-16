"""
Analyse de réseau : relier les transactions entre elles pour révéler les RÉSEAUX de fraude
(portefeuilles mules qui reçoivent de nombreuses victimes, appareils de fraudeurs réutilisés,
agents compromis), que le score transaction par transaction ne voit pas.

Graphe biparti :
    comptes clients (U)  <->  entités utilisées : portefeuille destinataire/émetteur d'un transfert (W),
                              appareil (D), agent (A), marchand (M).
Chaque arête agrège les transactions d'un compte avec une entité : nombre, montant, et SUSPICION
cumulée = somme, sur les transactions, de l'étiquette de l'analyste (1 fraude / 0 légitime) ou à défaut
de la probabilité de fraude du modèle (espérance du nombre de fraudes).

Trois niveaux de score, tous interprétables par un analyste :
    1. risque DIRECT d'une entité : part de fraude de ses transactions, lissée par un a priori bêta
       centré sur le taux global (une seule fraude ne suffit pas à condamner une entité très utilisée) ;
    2. EXPOSITION d'un compte (1 saut) : OU probabiliste (noisy-OR) de l'excès de risque direct de ses entités
       au-dessus du taux global ;
    3. risque PROPAGÉ d'une entité partagée (2 sauts : entité -> comptes -> autres entités) : exposition
       moyenne de ses comptes, en excluant l'entité elle-même (sinon elle s'auto-alimenterait).
       Score final = 1 - (1 - direct) x (1 - ALPHA x propagé).
Les RÉSEAUX (anneaux) sont les composantes connexes du sous-graphe restreint aux entités à risque DIRECT
élevé partagées par au moins deux comptes.

Dépendances : bibliothèque standard uniquement (utilisable par le back-office comme par l'évaluation).
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

KINDS = {"U": "compte", "W": "portefeuille", "D": "appareil", "A": "agent", "M": "marchand"}
P2P_TYPES = {"P2P_SEND", "P2P_RECEIVE"}

PRIOR_STRENGTH = 4.0      # poids de l'a priori bêta (en nombre de transactions « virtuelles »)
ALPHA = 0.5               # poids du risque propagé (2 sauts) dans le score final
RING_MIN_SCORE = 0.30     # seuil de risque DIRECT d'une entité pour relier les comptes d'un réseau
_MAX_P = 0.999            # borne pour les produits de (1 - p)


def node_id(kind: str, raw: str) -> str:
    return f"{kind}:{raw}"


def split_node(node: str) -> tuple[str, str]:
    kind, _, raw = node.partition(":")
    if kind not in KINDS or not raw:
        raise ValueError(f"identifiant de nœud invalide : {node!r} (attendu U:, W:, D:, A: ou M:)")
    return kind, raw


def _present(v) -> bool:
    return v is not None and v != "" and not (isinstance(v, float) and math.isnan(v))


def tx_entities(tx: dict) -> list[str]:
    """Entités touchées par une transaction (hors compte titulaire)."""
    out = []
    if tx.get("tx_type") in P2P_TYPES and _present(tx.get("counterparty_id")):
        out.append(node_id("W", str(tx["counterparty_id"])))
    for kind, key in (("D", "device_id"), ("A", "agent_id"), ("M", "merchant_id")):
        if _present(tx.get(key)):
            out.append(node_id(kind, str(tx[key])))
    return out


@dataclass
class EdgeStats:
    n: int = 0              # transactions
    n_known: int = 0        # transactions dont la suspicion est connue (étiquette ou score)
    s: float = 0.0          # suspicion cumulée (espérance du nombre de fraudes)
    amount: float = 0.0     # montant cumulé (USD)


@dataclass
class GraphScores:
    """Instantané des scores (calculé à la demande ; le graphe peut continuer d'évoluer)."""
    base_rate: float
    direct: dict[str, float]            # entité -> risque direct
    propagated: dict[str, float]        # entité partagée -> risque propagé
    entity: dict[str, float]            # entité -> score final
    account: dict[str, float]           # compte -> exposition

    def score(self, node: str) -> float:
        return self.account.get(node, 0.0) if node.startswith("U:") else self.entity.get(node, 0.0)


@dataclass
class TransactionGraph:
    edges: dict[tuple[str, str], EdgeStats] = field(default_factory=lambda: defaultdict(EdgeStats))
    by_account: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    by_entity: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    # ------------------------------------------------------------------ construction
    def add(self, tx: dict, suspicion: float | None = None) -> None:
        """Ajoute une transaction. `suspicion` : étiquette (0/1), probabilité du modèle, ou None (inconnue)."""
        if not _present(tx.get("user_id")):
            return
        u = node_id("U", str(tx["user_id"]))
        amount = float(tx.get("amount_usd") or 0.0)
        for e in tx_entities(tx):
            st = self.edges[(u, e)]
            st.n += 1
            st.amount += amount
            if suspicion is not None:
                st.n_known += 1
                st.s += min(max(float(suspicion), 0.0), 1.0)
            self.by_account[u].add(e)
            self.by_entity[e].add(u)

    def add_edge(self, account: str, entity: str, n: int, n_known: int, s: float, amount: float) -> None:
        """Ajoute une arête déjà agrégée (par exemple GROUP BY en SQL) : bien plus rapide que transaction par transaction."""
        u, e = node_id("U", str(account)), str(entity)
        split_node(e)
        st = self.edges[(u, e)]
        st.n += int(n)
        st.n_known += int(n_known)
        st.s += float(s or 0.0)
        st.amount += float(amount or 0.0)
        self.by_account[u].add(e)
        self.by_entity[e].add(u)

    def relabel(self, tx: dict, old: float | None, new: float | None) -> None:
        """Remplace la suspicion d'une transaction déjà ajoutée (score du modèle -> verdict de l'analyste)."""
        u = node_id("U", str(tx["user_id"]))
        for e in tx_entities(tx):
            st = self.edges.get((u, e))
            if st is None:
                continue
            if old is not None:
                st.n_known -= 1
                st.s -= min(max(float(old), 0.0), 1.0)
            if new is not None:
                st.n_known += 1
                st.s += min(max(float(new), 0.0), 1.0)

    @property
    def n_nodes(self) -> int:
        return len(self.by_account) + len(self.by_entity)

    # ------------------------------------------------------------------ scores
    def compute_scores(self, prior_strength: float = PRIOR_STRENGTH, alpha: float = ALPHA) -> GraphScores:
        tot_s = sum(st.s for st in self.edges.values())
        tot_k = sum(st.n_known for st in self.edges.values())
        base = tot_s / tot_k if tot_k else 0.01

        # 1. risque direct des entités (lissage bêta vers le taux global)
        agg_s: dict[str, float] = defaultdict(float)
        agg_k: dict[str, int] = defaultdict(int)
        for (_, e), st in self.edges.items():
            agg_s[e] += st.s
            agg_k[e] += st.n_known
        direct = {e: (agg_s[e] + prior_strength * base) / (agg_k[e] + prior_strength) for e in self.by_entity}

        # 2. exposition des comptes : noisy-OR de l'EXCÈS de risque au-dessus du taux global (sinon un compte actif,
        #    relié à des dizaines d'entités saines, cumulerait le taux de base de chacune et paraîtrait exposé)
        room = max(1.0 - base, 1e-9)
        log_safe = {e: math.log(1.0 - min(max(p - base, 0.0) / room, _MAX_P)) for e, p in direct.items()}
        acc_log = {u: sum(log_safe[e] for e in ents) for u, ents in self.by_account.items()}
        account = {u: 1.0 - math.exp(lg) for u, lg in acc_log.items()}

        # 3. risque propagé des entités partagées (exposition des comptes SANS l'entité elle-même)
        propagated, entity = {}, {}
        for e, users in self.by_entity.items():
            d = direct[e]
            if len(users) >= 2:
                p = sum(1.0 - math.exp(acc_log[u] - log_safe[e]) for u in users) / len(users)
                propagated[e] = p
                entity[e] = 1.0 - (1.0 - d) * (1.0 - alpha * p)
            else:
                entity[e] = d
        return GraphScores(base, direct, propagated, entity, account)

    def tx_network_score(self, tx: dict, scores: GraphScores) -> dict:
        """Score réseau d'une transaction entrante (calculé AVANT de l'ajouter au graphe)."""
        ents = [(e, scores.entity.get(e, 0.0)) for e in tx_entities(tx)]
        top = max(ents, key=lambda t: t[1], default=(None, 0.0))
        u = node_id("U", str(tx.get("user_id")))
        return {"score": top[1], "entity": top[0], "account_exposure": scores.account.get(u, 0.0)}

    # ------------------------------------------------------------------ réseaux
    def rings(self, scores: GraphScores, min_score: float = RING_MIN_SCORE, min_accounts: int = 2,
              include_members: bool = False) -> list[dict]:
        """Composantes connexes reliées par des entités partagées à risque DIRECT élevé, du plus au moins dangereux.

        Le lien repose sur la preuve observée (risque direct), pas sur le risque propagé : sinon une entité saine
        fréquentée par d'anciennes victimes relierait entre eux des comptes sans rapport (composante géante)."""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        risky = {e for e, users in self.by_entity.items()
                 if len(users) >= 2 and scores.direct.get(e, 0.0) >= min_score}
        for e in risky:
            for u in self.by_entity[e]:
                ra, rb = find(u), find(e)
                if ra != rb:
                    parent[ra] = rb
        comps: dict[str, list[str]] = defaultdict(list)
        for x in list(parent):
            comps[find(x)].append(x)

        out = []
        for members in comps.values():
            accounts = [m for m in members if m.startswith("U:")]
            if len(accounts) < min_accounts:
                continue
            ents = [m for m in members if not m.startswith("U:")]
            mset = set(members)
            n_tx, s, amount = 0, 0.0, 0.0
            for u in accounts:
                for e in self.by_account[u]:
                    if e in mset:
                        st = self.edges[(u, e)]
                        n_tx += st.n
                        s += st.s
                        amount += st.amount
            kinds: dict[str, int] = defaultdict(int)
            for e in ents:
                kinds[e[0]] += 1
            ents.sort(key=lambda e: -scores.entity.get(e, 0.0))
            accounts.sort(key=lambda u: -scores.account.get(u, 0.0))
            ring = {
                "id": ents[0],                                   # entité la plus risquée = « pivot » du réseau
                "score": round(scores.entity.get(ents[0], 0.0), 4),
                "n_accounts": len(accounts), "n_entities": len(ents),
                "entity_kinds": {KINDS[k]: v for k, v in sorted(kinds.items())},
                "n_tx": n_tx, "expected_frauds": round(s, 2), "amount_usd": round(amount, 2),
                "top_entities": ents[:10], "top_accounts": accounts[:10],
            }
            if include_members:
                ring["entities"], ring["accounts"] = ents, accounts
            out.append(ring)
        out.sort(key=lambda r: (-r["score"], -r["expected_frauds"]))
        return out

    # ------------------------------------------------------------------ voisinage
    def ego(self, node: str, scores: GraphScores, hops: int = 2, max_nodes: int = 80, max_fanout: int = 25) -> dict:
        """Sous-graphe autour d'un nœud : à chaque saut, on garde les voisins les plus risqués."""
        split_node(node)
        if node not in self.by_account and node not in self.by_entity:
            return {"center": node, "nodes": [], "edges": [], "truncated": False}
        keep = {node: 0}
        frontier = [node]
        truncated = False
        for depth in range(1, hops + 1):
            nxt = []
            for x in frontier:
                neigh = self.by_account.get(x) or self.by_entity.get(x) or set()
                ranked = sorted((n for n in neigh if n not in keep), key=lambda n: -scores.score(n))
                if len(ranked) > max_fanout:
                    truncated = True
                for n in ranked[:max_fanout]:
                    if len(keep) >= max_nodes:
                        truncated = True
                        break
                    keep[n] = depth
                    nxt.append(n)
            frontier = nxt

        nodes = []
        for n, depth in keep.items():
            kind, raw = split_node(n)
            linked = self.by_account.get(n) if kind == "U" else self.by_entity.get(n)
            pairs = [(n, e) for e in linked] if kind == "U" else [(u, n) for u in linked]
            n_tx = sum(self.edges[p].n for p in pairs)
            s = sum(self.edges[p].s for p in pairs)
            nodes.append({
                "id": n, "kind": kind, "kind_label": KINDS[kind], "raw_id": raw, "depth": depth,
                "score": round(scores.score(n), 4),
                "direct": round(scores.direct[n], 4) if n in scores.direct else None,
                "degree": len(linked), "n_tx": n_tx, "expected_frauds": round(s, 2),
            })
        edges = []
        for (u, e), st in self.edges.items():
            if u in keep and e in keep:
                edges.append({"source": u, "target": e, "n_tx": st.n,
                              "expected_frauds": round(st.s, 2), "amount_usd": round(st.amount, 2)})
        return {"center": node, "nodes": nodes, "edges": edges, "truncated": truncated}
