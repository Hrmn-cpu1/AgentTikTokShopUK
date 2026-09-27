from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Experiment(Base):
    __tablename__ = "experiments"
    experiment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    creative_id: Mapped[str] = mapped_column(String(100), nullable=False)
    publication_action_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    authority_evidence_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("market = 'UK' AND currency = 'GBP'", name="uk_gbp_only"),)


class CommerceEvent(Base):
    __tablename__ = "commerce_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), nullable=False)
    action_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_gbp: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    evidence_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("source", "external_event_id", name="uq_external_event"),
        Index("uq_one_publication_per_experiment", "experiment_id", unique=True,
              sqlite_where=text("event_type = 'PUBLISHED'"), postgresql_where=text("event_type = 'PUBLISHED'")),
        CheckConstraint("event_type IN ('PUBLISHED','ORDER_CREATED','DELIVERED','COMMISSION_SETTLED','REFUNDED')", name="known_event_type"),
        CheckConstraint("amount_gbp IS NULL OR amount_gbp >= 0", name="nonnegative_amount"),
        CheckConstraint("event_type NOT IN ('COMMISSION_SETTLED','REFUNDED') OR amount_gbp IS NOT NULL", name="economic_amount_required"),
    )


class ExperimentCost(Base):
    __tablename__ = "experiment_costs"
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), primary_key=True)
    amount_gbp: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("amount_gbp >= 0", name="nonnegative_cost"),)


class ExperimentCostAdjustment(Base):
    __tablename__ = "experiment_cost_adjustments"
    adjustment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), nullable=False)
    amount_gbp: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("amount_gbp > 0", name="positive_adjustment"),)


class OperatorSession(Base):
    __tablename__ = "operator_sessions"
    session_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TikTokOAuthIntent(Base):
    __tablename__ = "tiktok_oauth_intents"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_hash: Mapped[str] = mapped_column(ForeignKey("operator_sessions.session_hash"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platform: Mapped[str] = mapped_column(String(10), nullable=False, default="WEB")


class TikTokConnection(Base):
    __tablename__ = "tiktok_connections"
    connection_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operator_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    provider_user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    granted_scopes: Mapped[str] = mapped_column(String(1000), nullable=False)
    encrypted_access_token: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    manual_uk_evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_affiliate_evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED','REFRESH_FAILED','UNKNOWN')", name="valid_connection_status"),)
