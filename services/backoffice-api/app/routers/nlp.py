from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security import get_current_user
from shared.nlp.analyzer import analyze

router = APIRouter(prefix="/nlp", tags=["nlp"])


class TextIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


@router.post("/analyze")
def analyze_message(body: TextIn, _=Depends(get_current_user)):
    """Sentiment, émotions et indices d'ingénierie sociale d'un message (SMS reçu par un client,
    plainte, motif de transfert). Analyse locale par lexique : rien n'est conservé."""
    return analyze(body.text)
