from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "scoring-service"
    ARTIFACTS_DIR: str = "ml/artifacts"
    REDIS_URL: str = "redis://localhost:6379/0"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:19092"
    KAFKA_ENABLED: bool = True
    # Clés d'API des systèmes autorisés à demander un score (integration-layer, tests).
    # Séparées par des virgules ; à remplacer en production (secret Kubernetes).
    SCORING_API_KEYS: str = "dev-scoring-key"
    EXPLAIN_TOP_K: int = 6
    # Durée pendant laquelle une transaction déjà scorée renvoie sa décision d'origine (relances des opérateurs)
    IDEMPOTENCY_TTL_S: int = 1800
    # Lois physiques : "off" (ignorées), "shadow" (calculées, affichées et comptées, sans effet sur la décision),
    # "enforce" (une violation nette de la cinématique impose une vérification, par défaut). Repasser en « shadow »
    # si, sur les données réelles de l'opérateur, trop d'opérations légitimes violent la cinématique.
    PHYSICS_MODE: str = "enforce"


settings = Settings()
