"""
RAG (retrieval-augmented generation) SANS modèle de langage externe : les preuves viennent
de sources vérifiables, jamais d'un texte inventé.

    1. Mémoire de cas (CaseMemory) : opérations passées dont le verdict est connu
       (historique d'entraînement + verdicts des analystes). On retrouve les cas les plus
       proches de l'opération examinée dans l'espace des variables comportementales.
    2. Base de connaissances (KnowledgeBase) : fiches de typologies de fraude (définition,
       signaux observables, vérifications recommandées), retrouvées par TF-IDF à partir
       des variables qui ont pesé dans la décision.
    3. Synthèse (build_evidence) : phrases construites à partir de ces éléments, avec le
       nombre de cas et leurs sources. Un indicateur de cohérence compare l'avis des cas
       proches à celui du modèle : en cas de divergence, la revue manuelle est conseillée.

Aucune donnée client ne quitte la plateforme. Dépendance : numpy uniquement.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
STOPWORDS = set("""le la les un une des de du d l et ou en au aux que qui est sont pour par sur dans avec sans
ce cette ces se son sa ses leur leurs il elle ils elles ne pas plus ni a y on""".split())

# Paramètres calibrés par ml/rag/evaluate_rag.py (écrits dans ml/reports/rag_evaluation.json)
DEFAULTS = {"k": 5, "min_similarity": 0.20, "fraud_share_cutoff": 0.5, "min_neighbors_weight": 3.0}


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [t for t in re.findall(r"[a-z0-9_]+", text) if len(t) > 1 and t not in STOPWORDS]


# --------------------------------------------------------------------------- connaissances
@dataclass
class Passage:
    source: str
    title: str
    type: str
    section: str
    text: str


class KnowledgeBase:
    def __init__(self, directory: Path = KNOWLEDGE_DIR):
        self.passages: list[Passage] = []
        for f in sorted(Path(directory).glob("*.md")):
            self._load(f)
        docs = [_tokens(p.section + " " + p.text) for p in self.passages]
        n = len(docs)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.vectors = [self._vec(d) for d in docs]

    def _load(self, path: Path) -> None:
        raw = path.read_text(encoding="utf-8")
        meta, body = {}, raw
        if raw.startswith("---"):
            _, head, body = raw.split("---", 2)
            meta = dict(line.split(":", 1) for line in head.strip().splitlines() if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        for block in re.split(r"^## ", body, flags=re.M)[1:]:
            section, _, text = block.partition("\n")
            self.passages.append(Passage(path.name, meta.get("titre", path.stem), meta.get("type", "GENERAL"),
                                         section.strip(), text.strip()))

    def _vec(self, tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query: str, fraud_type: str | None = None, k: int = 3) -> list[dict]:
        """Passages les plus pertinents. La fiche de la typologie est toujours consultée
        (sa « Définition » vient en premier), les autres passages sont classés par TF-IDF."""
        q = self._vec(_tokens(query))
        scored = []
        for p, v in zip(self.passages, self.vectors):
            score = sum(w * v.get(t, 0.0) for t, w in q.items())
            scored.append((score, p))
        pool = [(s, p) for s, p in scored if fraud_type and p.type == fraud_type] or \
               [(s, p) for s, p in scored if p.type == "GENERAL"]
        pool.sort(key=lambda x: (x[1].section != "Définition", -x[0]))
        picked = pool[:k]
        return [{"source": p.source, "title": p.title, "section": p.section, "text": p.text,
                 "relevance": round(float(s), 3)} for s, p in picked]


# --------------------------------------------------------------------------- mémoire de cas
class CaseMemory:
    """Index de cas étiquetés (fichier .npz construit par ml/rag/build_case_index.py)."""

    def __init__(self, index_path: str | Path):
        z = np.load(index_path, allow_pickle=False)
        self.X = z["X"].astype(np.float32)
        self.y = z["y"].astype(np.int8)
        self.w = z["w"].astype(np.float32)             # poids d'importance (sous-échantillonnage des légitimes)
        self.ftype = z["ftype"]
        self.ids = z["ids"]
        self.channel = z["channel"]
        self.tx_type = z["tx_type"]
        self.amount = z["amount"].astype(np.float32)
        self.mean = z["mean"].astype(np.float64)
        self.scale = z["scale"].astype(np.float64)
        self.clip = float(z["clip"])
        self.ref_dist = float(z["ref_dist"])           # distance médiane au plus proche voisin (échelle)
        self.feature_names = json.loads(str(z["feature_names"]))
        self._sq = (self.X ** 2).sum(axis=1)
        self.is_card_col = self.feature_names.index("is_card")

    def __len__(self) -> int:
        return len(self.y)

    def scale_vec(self, feats: dict) -> np.ndarray:
        raw = np.array([float(feats.get(f, 0.0)) for f in self.feature_names], dtype=np.float64)
        return np.clip((raw - self.mean) / self.scale, -self.clip, self.clip).astype(np.float32)

    def neighbors(self, feats: dict, k: int = 7, channel: str | None = None,
                  extra: list[dict] | None = None) -> list[dict]:
        """k cas les plus proches (même canal). `extra` : cas supplémentaires
        {id, features, label, fraud_type, channel, tx_type, amount_usd, source}."""
        x = self.scale_vec(feats)
        d2 = self._sq - 2.0 * (self.X @ x) + float(x @ x)
        mask = np.ones(len(d2), dtype=bool) if channel is None else (self.channel == channel)
        cand = np.where(mask)[0]
        rows = [{"d": math.sqrt(max(float(d2[i]), 0.0)), "id": str(self.ids[i]), "label": int(self.y[i]),
                 "fraud_type": str(self.ftype[i]) or None, "channel": str(self.channel[i]),
                 "tx_type": str(self.tx_type[i]), "amount_usd": float(self.amount[i]), "weight": float(self.w[i]),
                 "source": "historique"} for i in cand[np.argsort(d2[cand])[:k]]]
        for e in extra or []:
            if channel is not None and e.get("channel") != channel:
                continue
            v = self.scale_vec(e["features"])
            rows.append({"d": float(np.linalg.norm(v - x)), "id": e["id"], "label": int(e["label"]),
                         "fraud_type": e.get("fraud_type"), "channel": e.get("channel"),
                         "tx_type": e.get("tx_type"), "amount_usd": float(e.get("amount_usd") or 0.0),
                         "weight": 1.0, "source": e.get("source", "verdict analyste")})
        rows.sort(key=lambda r: r["d"])
        rows = rows[:k]
        for r in rows:
            r["similarity"] = round(1.0 / (1.0 + r["d"] / self.ref_dist), 4)
            r["d"] = round(r["d"], 4)
        return rows


# --------------------------------------------------------------------------- synthèse
def consensus(neigh: list[dict], params: dict | None = None) -> dict:
    """Part de fraude parmi les voisins (pondérée par similarité et par poids d'importance)."""
    p = {**DEFAULTS, **(params or {})}
    if not neigh:
        return {"fraud_share": None, "fraud_type_votes": {}, "mean_similarity": 0.0, "comparable": False}
    w = np.array([r["similarity"] * r["weight"] for r in neigh])
    lab = np.array([r["label"] for r in neigh])
    share = float((w * lab).sum() / w.sum())
    votes: dict[str, float] = {}
    for r, wi in zip(neigh, w):
        if r["label"] == 1 and r["fraud_type"]:
            votes[r["fraud_type"]] = votes.get(r["fraud_type"], 0.0) + float(wi)
    tot = sum(votes.values()) or 1.0
    mean_sim = float(np.mean([r["similarity"] for r in neigh]))
    return {"fraud_share": round(share, 4), "fraud_type_votes": {k: round(v / tot, 4) for k, v in
                                                                   sorted(votes.items(), key=lambda x: -x[1])},
            "mean_similarity": round(mean_sim, 4),
            "comparable": bool(mean_sim >= p["min_similarity"] and len(neigh) >= max(3, p["k"] // 2))}


def agreement(model_flagged: bool, cons: dict, params: dict | None = None) -> str:
    p = {**DEFAULTS, **(params or {})}
    if not cons["comparable"]:
        return "INSUFFISANT"
    return "COHERENT" if (cons["fraud_share"] >= p["fraud_share_cutoff"]) == model_flagged else "DIVERGENT"


def build_evidence(kb: KnowledgeBase, memory: CaseMemory, features: dict, *, model_flagged: bool,
                   probability: float, fraud_type: str | None, top_features: list[str], channel: str | None,
                   extra_cases: list[dict] | None = None, params: dict | None = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    neigh = memory.neighbors(features, k=p["k"], channel=channel, extra=extra_cases)
    cons = consensus(neigh, p)
    agree = agreement(model_flagged, cons, p)
    votes = cons["fraud_type_votes"]
    neigh_type = next(iter(votes), None)
    type_agree = None if not (fraud_type and neigh_type) else fraud_type == neigh_type

    query = " ".join(top_features + ([fraud_type] if fraud_type else []))
    passages = kb.search(query, fraud_type=fraud_type, k=3)

    n_fraud = sum(r["label"] for r in neigh)
    lines = []
    if neigh:
        lines.append(f"{n_fraud} des {len(neigh)} cas les plus proches (similarité moyenne "
                     f"{cons['mean_similarity']:.2f}) sont des fraudes confirmées.")
    if agree == "COHERENT":
        lines.append("L'avis des cas proches confirme la décision du modèle.")
    elif agree == "DIVERGENT":
        lines.append("Les cas proches penchent pour une fraude alors que le modèle ne l'a pas retenue : examiner l'opération manuellement."
                     if not model_flagged else
                     "Les cas proches penchent pour une opération légitime alors que le modèle l'a signalée : examiner l'opération manuellement.")
    else:
        lines.append("Opération peu comparable aux cas connus : la comparaison n'est pas concluante, "
                     "s'appuyer sur l'explication du modèle et la fiche de typologie.")
    if type_agree is True:
        lines.append(f"Le type de fraude retenu ({fraud_type}) est aussi celui des cas proches.")
    elif type_agree is False:
        lines.append(f"Les cas proches suggèrent plutôt {neigh_type} que {fraud_type}.")

    reliability = {"COHERENT": "ELEVEE", "DIVERGENT": "A_VERIFIER", "INSUFFISANT": "LIMITEE"}[agree]
    if agree == "COHERENT" and type_agree is False:
        reliability = "A_VERIFIER"
    return {"agreement": agree, "reliability": reliability, "model_probability": round(float(probability), 4),
            "model_flagged": bool(model_flagged), "neighbors": neigh, "consensus": cons,
            "type_agreement": type_agree, "knowledge": passages, "summary": " ".join(lines),
            "index_size": len(memory), "params": {k: p[k] for k in ("k", "min_similarity", "fraud_share_cutoff")}}
