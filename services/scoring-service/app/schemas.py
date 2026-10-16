from pydantic import BaseModel


class FeatureContribution(BaseModel):
    feature: str
    shap: float
    value: float


class Explanation(BaseModel):
    top_features: list[FeatureContribution]
    branch_scores: dict[str, float]
    branch_contributions: dict[str, float]
    attention_on_history: list[float]


class FraudTypeCandidate(BaseModel):
    type: str
    probability: float


class ScoreResponse(BaseModel):
    transaction_id: str
    duplicate: bool = False     # True : transaction déjà scorée, la décision d'origine est renvoyée sans nouveau calcul
    fraud_probability: float
    is_fraud_predicted: bool
    threshold: float
    action: str                 # APPROVE | VERIFY | BLOCK
    risk_level: str             # FAIBLE | MOYEN | ELEVE | CRITIQUE
    reason: str
    fraud_type: str | None = None             # typologie probable, si la transaction est signalée
    fraud_type_probability: float | None = None
    fraud_type_candidates: list[FraudTypeCandidate] = []
    fraud_type_source: str | None = None      # "modele" ou "texte" (message du transfert)
    physics: dict | None = None               # lois physiques : violations, gravité, mode (shadow / enforce)
    text_analysis: dict | None = None         # sentiment et indices d'ingénierie sociale du memo, s'il y en a un
    expected_costs_usd: dict[str, float]
    rules_triggered: list[str]
    policy_version: str | None = None         # version de la politique de coût appliquée
    known_user: bool
    explanation: Explanation
    degraded: bool
    degraded_branches: list[str]
    model_version: str
    latency_ms: float
    features: dict[str, float]
