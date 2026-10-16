"""
Modèle de données PostgreSQL / TimescaleDB, partagé par le backoffice-api et les workers.

    bo_users             utilisateurs du back-office (analystes, superviseurs, admins)
    scored_transactions  toutes les transactions scorées + décision + explication
                         (hypertable TimescaleDB partitionnée sur tx_time) ; sert aussi de
                         journal des prédictions pour l'apprentissage continu (label)
    cases                dossiers ouverts pour les alertes (VERIFY / BLOCK)
    unblock_requests     déblocages importants en attente d'un second validateur (quatre yeux)
    notifications        alertes envoyées (e-mail, SMS, webhook opérateur)
    audit_log            journal d'audit inaltérable, chaîné par hachage SHA-256
                         (UPDATE / DELETE interdits par trigger) — traçabilité BCC
    model_registry       versions du modèle, métriques, statut champion/challenger
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger,
                        String, Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BackofficeUser(Base):
    __tablename__ = "bo_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))            # ANALYSTE | SUPERVISEUR | ADMIN
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # double authentification (TOTP, RFC 6238) : secret chiffré, dernier pas utilisé (anti-rejeu)
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # verrouillage temporaire après plusieurs échecs de connexion
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoredTransaction(Base):
    __tablename__ = "scored_transactions"
    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tx_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)   # heure locale RDC
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    operator: Mapped[str | None] = mapped_column(String(20))
    tx_type: Mapped[str] = mapped_column(String(20))
    access_channel: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    amount_usd: Mapped[float] = mapped_column(Float)
    province: Mapped[str] = mapped_column(String(40))
    device_id: Mapped[str] = mapped_column(String(64))
    counterparty_id: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    merchant_id: Mapped[str | None] = mapped_column(String(64))
    fraud_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(255))
    rules_triggered: Mapped[list] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(String(40))
    latency_ms: Mapped[float] = mapped_column(Float)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[dict] = mapped_column(JSONB)
    # typologie probable (SIM_SWAP, SMURFING, ...) : renseignée pour les transactions signalées
    fraud_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fraud_type_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    features: Mapped[dict] = mapped_column(JSONB)
    # étiquette issue du retour des analystes : 1 fraude confirmée, 0 faux positif
    label: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # institution partenaire qui a soumis la transaction (code de la table institutions)
    institution: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_scored_action_time", "action", "tx_time"),
        Index("ix_scored_risk_time", "risk_level", "tx_time"),
        Index("ix_scored_fraud_type_time", "fraud_type", "tx_time"),
        Index("ix_scored_scored_at", "scored_at"),   # KPIs temps réel (horloge réelle)
        Index("ix_scored_institution_time", "institution", "tx_time"),
    )


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tx_time: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    tx_type: Mapped[str] = mapped_column(String(20))
    amount_usd: Mapped[float] = mapped_column(Float)
    fraud_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(10), index=True)
    action: Mapped[str] = mapped_column(String(10))
    fraud_type: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    # OUVERT -> EN_COURS -> FRAUDE_CONFIRMEE | FAUX_POSITIF
    status: Mapped[str] = mapped_column(String(20), default="OUVERT", index=True)
    institution: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # pourquoi ce cas a été revu : ALERTE du modèle, PLAINTE client, REVUE libre, ou file de revue
    # (INCERTITUDE, NOUVEAUTE, RESEAU, TEMOIN = échantillon aléatoire des transactions approuvées)
    review_reason: Mapped[str] = mapped_column(String(16), default="ALERTE", server_default="ALERTE", index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("bo_users.id"), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("bo_users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class UnblockRequest(Base):
    """Principe des quatre yeux : débloquer une transaction bloquée d'un montant important (verdict « faux positif »)
    demande la validation d'un second utilisateur, superviseur ou administrateur, différent du demandeur."""
    __tablename__ = "unblock_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(String(64))
    amount_usd: Mapped[float] = mapped_column(Float)
    requested_by: Mapped[int] = mapped_column(ForeignKey("bo_users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="EN_ATTENTE", server_default="EN_ATTENTE", index=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("bo_users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class DecisionPolicyVersion(Base):
    """Version de la politique de coût (shared/policy/costs.py) : qui l'a réglée, pourquoi, avec quel effet simulé."""
    __tablename__ = "decision_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(ForeignKey("bo_users.id"))
    params: Mapped[dict] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    simulation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # effet simulé au moment du réglage


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(10))       # EMAIL | SMS | WEBHOOK
    recipient: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10))        # ENVOYE | ECHEC
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(12))        # CHAMPION | CHALLENGER | ARCHIVE | REJETE
    metrics: Mapped[dict] = mapped_column(JSONB)
    trained_on: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrainEvent(Base):
    """Journal de l'apprentissage continu : pourquoi un réentraînement a été demandé, attendu ou lancé,
    et ce qu'il a donné. Les lignes DEMANDEE sont créées par le back-office (bouton) et prises en charge
    par le planificateur (handled_at renseigné)."""
    __tablename__ = "retrain_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    trigger: Mapped[str] = mapped_column(String(12))       # AUTO | MANUEL
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    # DEMANDEE | EN_ATTENTE | CHAMPION | CHALLENGER | REJETE | IGNORE | ERREUR
    status: Mapped[str] = mapped_column(String(12))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetrainState(Base):
    """Dernier relevé des signaux évalués par le planificateur (une seule ligne, id = 1)."""
    __tablename__ = "retrain_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    signals: Mapped[dict] = mapped_column(JSONB)


class Institution(Base):
    """Institution partenaire qui utilise le système par l'API : opérateur Mobile Money, banque, émetteur de cartes,
    ou régulateur (BCC, supervision en lecture seule). La clé d'API n'est jamais stockée : seulement son empreinte
    SHA-256 ; elle n'est montrée qu'une fois, à la création ou au renouvellement."""
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)       # ex. vodacom, rawbank, bcc
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))      # OPERATEUR_MM | BANQUE | EMETTEUR_CARTE | REGULATEUR
    scopes: Mapped[list] = mapped_column(JSONB, default=list)      # transactions | feedback | supervision
    providers: Mapped[list] = mapped_column(JSONB, default=list)   # formats natifs autorisés : vodacom, airtel…
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # requêtes par seconde autorisées à cette institution (vide = valeur par défaut de l'integration-layer)
    rate_limit_per_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
