import pytest

from shared.nlp.analyzer import analyze, normalize, sentiment, social_engineering


def test_scam_with_pin_request_and_authority_is_high():
    r = social_engineering("Je suis du service client Vodacom, votre compte sera bloqué. Envoyez-moi votre code PIN")
    cats = {c["category"] for c in r["cues"]}
    assert {"DEMANDE_CODE", "AUTORITE", "MENACE"} <= cats and r["level"] == "ELEVE"
    assert all(c["match"] for c in r["cues"])           # chaque indice est justifié par un extrait


def test_single_weak_cue_is_not_enough():
    assert social_engineering("Urgent, peux-tu m'envoyer le loyer avant midi")["level"] == "FAIBLE"
    assert social_engineering("Salaire du mois de septembre")["score"] == 0


def test_first_person_win_and_pin_talk_are_not_flagged():
    assert social_engineering("J'ai gagné au foot hier, voici ta part")["level"] == "FAIBLE"
    assert social_engineering("Mon code PIN a expiré, je le change demain")["level"] == "FAIBLE"


def test_accents_and_case_are_ignored():
    assert normalize("FÉLICITATIONS vous avez GAGNÉ") == "felicitations vous avez gagne"
    assert social_engineering("FÉLICITATIONS ! Vous avez gagné 500 USD, payez les frais de dossier de 20 USD")["level"] == "ELEVE"


def test_sentiment_with_negation_and_emotions():
    assert sentiment("Je ne suis pas content du tout")["label"] == "NEGATIF"
    s = sentiment("J'ai peur, on a retiré de l'argent sans mon accord, au secours")
    assert s["label"] == "NEGATIF" and {"PEUR", "DETRESSE"} <= set(s["emotions"])
    assert sentiment("Merci, le service est rapide et parfait")["label"] == "POSITIF"
    assert sentiment("Paiement facture d'eau")["label"] == "NEUTRE"


def test_empty_text_returns_none_and_long_text_is_bounded():
    assert analyze("   ") is None and analyze(None) is None
    assert analyze("a " * 5000)["social_engineering"]["level"] == "FAIBLE"


def test_corpus_test_precision_does_not_regress():
    from ml.nlp.evaluate_nlp import run
    r = run("test")
    assert r["ingenierie_sociale_MOYEN_ou_plus"]["precision"] >= 0.95
    assert r["ingenierie_sociale_MOYEN_ou_plus"]["rappel"] >= 0.65
