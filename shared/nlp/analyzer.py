"""
Analyse de messages (français) : sentiment, émotions et indices d'ingénierie sociale.

Approche volontairement TRANSPARENTE (lexique + motifs pondérés, sans modèle externe) :
    - chaque indice déclenché est renvoyé avec l'extrait de texte qui l'a provoqué, pour qu'un
      analyste puisse vérifier et contester ;
    - aucune donnée de message ne quitte la plateforme ;
    - pas de données d'apprentissage nécessaires : les lexiques se corrigent à la main
      (shared/nlp/lexicon.py) à mesure que de nouvelles arnaques apparaissent.

Sources de texte : motif / référence d'un transfert (champ `memo`), plainte d'un client,
SMS ou message signalé par un client.

Score d'ingénierie sociale = combinaison « ou bruité » des poids des catégories d'indices
distinctes : 1 − Π(1 − poids). Un indice faible (« urgent ») ne suffit pas, plusieurs indices
concordants (urgence + autorité + demande de code) font monter le score.

Limites : français uniquement (le lingala et le swahili ne sont pas couverts), détection de
motifs connus et non de sens ; une arnaque formulée autrement peut passer inaperçue.
"""
from __future__ import annotations

import re
import unicodedata

from shared.nlp.lexicon import EMOTIONS, NEGATION, NEGATIVE, POSITIVE, SE_CUES

SE_LEVELS = (("ELEVE", 0.70), ("MOYEN", 0.40))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    text = re.sub(r"[’`´]", "'", text)
    return re.sub(r"\s+", " ", text).strip()


_SE = [(cat, label, weight, re.compile(pat)) for cat, (label, weight, pats) in SE_CUES.items() for pat in pats]
_EMO = {e: [re.compile(p) for p in pats] for e, pats in EMOTIONS.items()}
_NEG = [re.compile(p) for p in NEGATIVE]
_POS = [re.compile(p) for p in POSITIVE]
_NEGATION = re.compile(NEGATION)


def _negated(text: str, start: int) -> bool:
    """Mot d'opinion précédé d'une négation dans les 3 mots qui précèdent (« pas content »)."""
    before = " ".join(text[:start].split()[-3:])
    return bool(_NEGATION.search(before))


def sentiment(text: str) -> dict:
    t = normalize(text)
    pos = neg = 0.0
    for rx in _NEG:
        for m in rx.finditer(t):
            if _negated(t, m.start()):
                pos += 0.5
            else:
                neg += 1.0
    for rx in _POS:
        for m in rx.finditer(t):
            if _negated(t, m.start()):
                neg += 0.5
            else:
                pos += 1.0
    if "!" in text and neg > pos:
        neg += 0.5          # insistance typographique : point d'exclamation dans un message négatif
    polarity = (pos - neg) / (pos + neg + 1.0)
    label = "NEGATIF" if polarity <= -0.2 else "POSITIF" if polarity >= 0.2 else "NEUTRE"
    emotions = sorted(e for e, rxs in _EMO.items() if any(rx.search(t) for rx in rxs))
    return {"polarity": round(polarity, 3), "label": label, "emotions": emotions}


def social_engineering(text: str) -> dict:
    t = normalize(text)
    best: dict[str, dict] = {}
    for cat, label, weight, rx in _SE:
        m = rx.search(t)
        if m and (cat not in best or weight > best[cat]["weight"]):
            best[cat] = {"category": cat, "label": label, "weight": weight, "match": m.group(0).strip()}
    keep = 1.0
    for c in best.values():
        keep *= 1.0 - c["weight"]
    score = round(1.0 - keep, 3)
    level = next((lv for lv, thr in SE_LEVELS if score >= thr), "FAIBLE")
    return {"score": score, "level": level, "cues": sorted(best.values(), key=lambda c: -c["weight"])}


def analyze(text: str | None) -> dict | None:
    """Analyse complète d'un message ; None si le texte est vide."""
    if not text or not text.strip():
        return None
    text = text.strip()[:2000]
    se = social_engineering(text)
    sent = sentiment(text)
    return {"sentiment": sent, "social_engineering": se,
            "summary": summarize(sent, se), "language": "fr"}


def summarize(sent: dict, se: dict) -> str:
    parts = []
    if se["level"] != "FAIBLE":
        labels = ", ".join(c["label"] for c in se["cues"][:3])
        parts.append(f"Indices d'ingénierie sociale ({se['level'].lower()}) : {labels}.")
    else:
        parts.append("Pas d'indice net d'ingénierie sociale.")
    tone = {"NEGATIF": "négatif", "POSITIF": "positif", "NEUTRE": "neutre"}[sent["label"]]
    emo = f" ({', '.join(e.lower() for e in sent['emotions'])})" if sent["emotions"] else ""
    parts.append(f"Ton {tone}{emo}.")
    return " ".join(parts)
