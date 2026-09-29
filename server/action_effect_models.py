"""Durable action contracts, effect identity, outbox, attempts and evidence."""
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, DDL, ForeignKey,
    ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class ActionContract(Base):
    __tablename__ = "action_contracts"
    action_contract_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    market: Mapped[str] = mapped_column(String(2), nullable=False)
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    creative_id: Mapped[str] = mapped_column(ForeignKey("growth_creatives.creative_id"), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False)
    job_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    required_capability: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    target_account_id: Mapped[str | None] = mapped_column(String(200))
    business_parameters: Mapped[str] = mapped_column(Text, nullable=False)
    business_parameters_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PREPARED")
    lease_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lease_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["artifact_id", "creative_id"],
            ["growth_media_artifacts.artifact_id", "growth_media_artifacts.creative_id"],
            name="fk_action_contract_artifact_creative"),
        ForeignKeyConstraint(["job_id", "creative_id"],
            ["growth_jobs.job_id", "growth_jobs.creative_id"], name="fk_action_contract_job_creative"),
        CheckConstraint("length(business_parameters_digest) = 64 AND length(request_digest) = 64", name="action_contract_digest_length"),
        CheckConstraint("length(artifact_sha256) = 64", name="action_contract_artifact_sha_length"),
        CheckConstraint("contract_version > 0", name="action_contract_version_positive"),
        CheckConstraint("status IN ('PREPARED','REJECTED','CANCELLED')", name="action_contract_status"),
        CheckConstraint("market IN ('BR','UK','US','DE','FR','ES','JP','KR','CN','IN','ID','VN','TH','SG','RU')", name="action_contract_market"),
        Index("ix_action_contract_creative_created", "creative_id", "created_at"),
    )


class EffectLedger(Base):
    __tablename__ = "effect_ledger"
    effect_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    effect_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    action_contract_id: Mapped[str] = mapped_column(ForeignKey("action_contracts.action_contract_id"), nullable=False, unique=True)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PREPARED")
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    current_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_reference: Mapped[str | None] = mapped_column(String(300))
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("effect_id", "action_contract_id", name="uq_effect_contract_pair"),
        CheckConstraint("state IN ('PREPARED','DISPATCH_PENDING','UNKNOWN','RECONCILIATION_REQUIRED','CONFIRMED','REJECTED','FAILED_BEFORE_EFFECT')", name="effect_state"),
        CheckConstraint("length(request_digest) = 64 AND length(artifact_sha256) = 64", name="effect_digest_length"),
        CheckConstraint("current_attempt >= 0", name="effect_attempt_nonnegative"),
        CheckConstraint("state NOT IN ('UNKNOWN','RECONCILIATION_REQUIRED') OR reconciliation_required = TRUE", name="effect_unknown_requires_reconciliation"),
        CheckConstraint("state != 'CONFIRMED' OR confirmed_at IS NOT NULL", name="effect_confirmation_timestamp"),
        Index("ix_effect_reconciliation", "reconciliation_required", "updated_at"),
    )


class EffectOutbox(Base):
    __tablename__ = "effect_outbox"
    outbox_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    effect_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_contract_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    lease_attempt_id: Mapped[str | None] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        ForeignKeyConstraint(["effect_id", "action_contract_id"],
            ["effect_ledger.effect_id", "effect_ledger.action_contract_id"], name="fk_outbox_effect_contract"),
        UniqueConstraint("outbox_id", "effect_id", name="uq_outbox_id_effect_pair"),
        CheckConstraint("state IN ('PENDING','CLAIMED','ACKED')", name="outbox_state"),
        CheckConstraint("length(payload_digest) = 64", name="outbox_payload_digest_length"),
        CheckConstraint("lease_generation >= 0 AND revision >= 0 AND attempts >= 0", name="outbox_counters_nonnegative"),
        CheckConstraint("state != 'ACKED' OR acked_at IS NOT NULL", name="outbox_ack_timestamp"),
        CheckConstraint("state != 'CLAIMED' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL AND lease_attempt_id IS NOT NULL)", name="outbox_claim_lease"),
        Index("ix_effect_outbox_due", "state", "available_at", "lease_until"),
    )


class EffectAttempt(Base):
    __tablename__ = "effect_attempts"
    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    effect_id: Mapped[str] = mapped_column(String(36), nullable=False)
    outbox_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("growth_jobs.job_id"), nullable=False)
    job_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    job_lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outbox_worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outbox_lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outbox_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    result_class: Mapped[str] = mapped_column(String(60), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(100))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    provider_response_digest: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(["outbox_id", "effect_id"],
            ["effect_outbox.outbox_id", "effect_outbox.effect_id"], name="fk_effect_attempt_outbox_effect"),
        ForeignKeyConstraint(["effect_id"], ["effect_ledger.effect_id"], name="fk_effect_attempt_effect"),
        UniqueConstraint("effect_id", "outbox_attempt_id", name="uq_effect_outbox_attempt"),
        CheckConstraint("length(job_attempt_id) > 0 AND length(outbox_attempt_id) > 0 AND length(job_worker_id) > 0 AND length(outbox_worker_id) > 0", name="effect_attempt_identity"),
        CheckConstraint("job_lease_generation > 0 AND outbox_lease_generation > 0", name="effect_attempt_generation_positive"),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="effect_attempt_time_order"),
        CheckConstraint("provider_response_digest IS NULL OR length(provider_response_digest) = 64", name="effect_attempt_response_digest"),
        Index("ix_effect_attempts_effect_started", "effect_id", "started_at"),
    )


class EffectEvidence(Base):
    __tablename__ = "effect_evidence"
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    effect_id: Mapped[str] = mapped_column(ForeignKey("effect_ledger.effect_id"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("effect_id", "evidence_type", "payload_digest", name="uq_effect_evidence_digest"),
        CheckConstraint("classification IN ('SYSTEM_OBSERVED','PROVIDER_OBSERVED','OWNER_REPORTED','RECONCILIATION_RESULT')", name="effect_evidence_classification"),
        CheckConstraint("length(payload_digest) = 64", name="effect_evidence_digest_length"),
        Index("ix_effect_evidence_effect_observed", "effect_id", "observed_at"),
    )


# Keep Base.metadata.create_all test databases subject to the same immutability
# law as migrated SQLite databases. PostgreSQL production enforcement is installed
# by migration 0012 with a PL/pgSQL trigger.
_IMMUTABLE_SQLITE_COLUMNS = (
    "idempotency_key", "action_type", "market", "experiment_id", "creative_id",
    "artifact_id", "job_id", "job_attempt_id", "required_capability", "provider",
    "target_account_id", "business_parameters", "business_parameters_digest",
    "request_digest", "artifact_sha256", "requested_at", "created_at", "contract_version",
    "lease_owner", "lease_generation", "lease_attempt_id",
)
_sqlite_changed = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in _IMMUTABLE_SQLITE_COLUMNS)
event.listen(ActionContract.__table__, "after_create", DDL(
    f"CREATE TRIGGER IF NOT EXISTS trg_action_contract_immutable BEFORE UPDATE ON action_contracts "
    f"WHEN {_sqlite_changed} BEGIN SELECT RAISE(ABORT, 'action contract fields are immutable'); END"
).execute_if(dialect="sqlite"))
