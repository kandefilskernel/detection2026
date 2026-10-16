from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SERVICE_NAME: str = "backoffice-api"
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480          # une journée de travail d'analyste
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:19092"
    KAFKA_ENABLED: bool = True
    # Compte administrateur créé au premier démarrage s'il n'existe aucun utilisateur
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@fraud-rdc.local"
    BOOTSTRAP_ADMIN_PASSWORD: str = "ChangeMoi-2026!"
    CORS_ORIGINS: str = "http://localhost:3000"
    # Mémoire de cas du RAG (index construit par `python -m ml.rag.case_index`)
    RAG_INDEX_PATH: str = "ml/artifacts/case_index.npz"
    RAG_EXTRA_CASES: int = 2000       # verdicts d'analystes récents ajoutés à la mémoire
    # Sécurité : rôles tenus d'activer la double authentification. Vide (par défaut) = facultative pour tous,
    # activable par chacun dans « Sécurité du compte » ; en production : "SUPERVISEUR,ADMIN"
    REQUIRE_2FA_ROLES: str = ""
    TOTP_ENCRYPTION_KEY: str = ""     # clé Fernet ; vide = dérivée de JWT_SECRET_KEY
    MAX_FAILED_LOGINS: int = 5        # échecs consécutifs avant verrouillage
    LOCKOUT_MINUTES: int = 15
    # Quatre yeux : débloquer (faux positif) une transaction BLOQUÉE d'au moins ce montant exige un second validateur
    FOUR_EYES_MIN_USD: float = 500.0
    # Redis : publication de la politique de coût active, rechargée à chaud par le scoring
    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()
