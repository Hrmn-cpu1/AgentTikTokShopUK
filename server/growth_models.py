"""Durable Brazil growth-engine business truth. No external effect is implied by a row."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class NicheHypothesis(Base):
    __tablename__="growth_niches"
    niche_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    market:Mapped[str]=mapped_column(String(2),nullable=False,default="BR")
    language:Mapped[str]=mapped_column(String(10),nullable=False,default="pt-BR")
    hypothesis:Mapped[str]=mapped_column(Text,nullable=False)
    trend_evidence:Mapped[str]=mapped_column(Text,nullable=False)
    production_cost_centavos:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    risk:Mapped[str]=mapped_column(String(20),nullable=False,default="LOW")
    status:Mapped[str]=mapped_column(String(20),nullable=False,default="EXPLORING")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(CheckConstraint("status IN ('EXPLORING','PROMISING','WINNER','DECLINING','KILLED')",name="growth_niche_status"),)

class TrendSignal(Base):
    __tablename__="growth_trends"
    trend_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    source:Mapped[str]=mapped_column(String(40),nullable=False)
    source_ref:Mapped[str]=mapped_column(String(1000),nullable=False)
    topic:Mapped[str]=mapped_column(String(300),nullable=False)
    market:Mapped[str]=mapped_column(String(2),nullable=False,default="BR")
    language:Mapped[str]=mapped_column(String(10),nullable=False,default="pt-BR")
    metrics_json:Mapped[str]=mapped_column(Text,nullable=False,default="{}")
    evidence:Mapped[str]=mapped_column(Text,nullable=False)
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class GrowthCreative(Base):
    __tablename__="growth_creatives"
    creative_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    niche_id:Mapped[str]=mapped_column(ForeignKey("growth_niches.niche_id"),nullable=False)
    trend_id:Mapped[str]=mapped_column(ForeignKey("growth_trends.trend_id"),nullable=False)
    experiment_id:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    plan_json:Mapped[str]=mapped_column(Text,nullable=False)
    evidence_ref:Mapped[str]=mapped_column(String(1000),nullable=False)
    state:Mapped[str]=mapped_column(String(30),nullable=False,default="SCRIPTED")
    media_ref:Mapped[str|None]=mapped_column(String(1000))
    media_hash:Mapped[str|None]=mapped_column(String(64))
    purpose:Mapped[str]=mapped_column(String(40),nullable=False,default="LEGACY_UNCLASSIFIED")
    creative_learning_eligible:Mapped[bool]=mapped_column(default=False,nullable=False)
    style_baseline_eligible:Mapped[bool]=mapped_column(default=False,nullable=False)
    mrwho_public:Mapped[bool]=mapped_column(default=False,nullable=False)
    exclusion_reason:Mapped[str|None]=mapped_column(String(100))
    quality_status:Mapped[str]=mapped_column(String(20),nullable=False,default="NOT_EVALUATED")
    quality_json:Mapped[str]=mapped_column(Text,nullable=False,default="{}")
    policy_status:Mapped[str]=mapped_column(String(24),nullable=False,default="NOT_EVALUATED",server_default="NOT_EVALUATED")
    scheduled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(CheckConstraint("state IN ('IDEA','SCRIPTED','ASSETS_PENDING','ASSETS_READY','RENDERING','READY','QUEUED','PUBLISHING','PUBLISHED','OBSERVING','LEARNED','FAILED','BLOCKED')",name="growth_creative_state"),)

class PublicationIntent(Base):
    __tablename__="growth_publication_intents"
    publication_intent_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    creative_id:Mapped[str]=mapped_column(ForeignKey("growth_creatives.creative_id"),nullable=False)
    idempotency_key:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    media_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    provider:Mapped[str]=mapped_column(String(40),nullable=False)
    provider_publish_id:Mapped[str|None]=mapped_column(String(300))
    provider_status:Mapped[str]=mapped_column(String(40),nullable=False,default="NOT_CONFIGURED")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class FollowerSnapshot(Base):
    __tablename__="growth_follower_snapshots"
    snapshot_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    account_id:Mapped[str]=mapped_column(String(200),nullable=False)
    followers:Mapped[int|None]=mapped_column(Integer)
    source:Mapped[str]=mapped_column(String(40),nullable=False)
    evidence_ref:Mapped[str]=mapped_column(String(1000),nullable=False)
    truth_classification:Mapped[str]=mapped_column(String(30),nullable=False,default="UNKNOWN",server_default="UNKNOWN")
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(
        CheckConstraint("followers IS NULL OR followers >= 0",name="followers_nonnegative"),
        CheckConstraint("truth_classification IN ('UNKNOWN','OWNER_REPORTED','PROVIDER_VERIFIED')",
                        name="follower_truth_classification"),
    )

class GrowthObservation(Base):
    __tablename__="growth_observations"
    observation_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    creative_id:Mapped[str]=mapped_column(ForeignKey("growth_creatives.creative_id"),nullable=False)
    views:Mapped[int|None]=mapped_column(Integer)
    likes:Mapped[int|None]=mapped_column(Integer)
    comments:Mapped[int|None]=mapped_column(Integer)
    shares:Mapped[int|None]=mapped_column(Integer)
    publication_identity:Mapped[str|None]=mapped_column(String(500))
    truth_classification:Mapped[str]=mapped_column(String(30),nullable=False,default="UNKNOWN")
    followers_before:Mapped[int|None]=mapped_column(Integer)
    followers_after:Mapped[int|None]=mapped_column(Integer)
    source:Mapped[str]=mapped_column(String(40),nullable=False)
    evidence_ref:Mapped[str]=mapped_column(String(1000),nullable=False)
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class GrowthLearning(Base):
    __tablename__="growth_learning"
    learning_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    creative_id:Mapped[str]=mapped_column(ForeignKey("growth_creatives.creative_id"),nullable=False)
    verdict:Mapped[str]=mapped_column(String(30),nullable=False)
    rationale:Mapped[str]=mapped_column(Text,nullable=False)
    next_mutation_json:Mapped[str]=mapped_column(Text,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class GrowthControl(Base):
    __tablename__="growth_control"
    control_id:Mapped[str]=mapped_column(String(20),primary_key=True)
    mode:Mapped[str]=mapped_column(String(20),nullable=False,default="READY")
    scheduler_enabled:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True,server_default="true")
    scheduler_interval_seconds:Mapped[int]=mapped_column(Integer,nullable=False,default=300,server_default="300")
    daily_experiment_quota:Mapped[int]=mapped_column(Integer,nullable=False,default=3,server_default="3")
    daily_handoff_quota:Mapped[int]=mapped_column(Integer,nullable=False,default=3,server_default="3")
    follower_goal:Mapped[int]=mapped_column(Integer,nullable=False,default=1000,server_default="1000")
    last_scheduler_tick_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(
        CheckConstraint("scheduler_interval_seconds >= 60",name="growth_scheduler_interval_min"),
        CheckConstraint("daily_experiment_quota BETWEEN 1 AND 24",name="growth_daily_experiment_quota"),
        CheckConstraint("daily_handoff_quota BETWEEN 1 AND 24",name="growth_daily_handoff_quota"),
        CheckConstraint("follower_goal >= 1",name="growth_follower_goal_positive"),
    )


class GrowthPolicyAssessment(Base):
    __tablename__="growth_policy_assessments"
    assessment_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    creative_id:Mapped[str]=mapped_column(ForeignKey("growth_creatives.creative_id"),nullable=False)
    artifact_id:Mapped[str]=mapped_column(ForeignKey("growth_media_artifacts.artifact_id"),nullable=False,unique=True)
    policy_pack_version:Mapped[str]=mapped_column(String(60),nullable=False)
    policy_status:Mapped[str]=mapped_column(String(24),nullable=False)
    originality_status:Mapped[str]=mapped_column(String(24),nullable=False)
    creative_dna_digest:Mapped[str]=mapped_column(String(64),nullable=False)
    originality_signature:Mapped[str]=mapped_column(String(64),nullable=False)
    provenance_digest:Mapped[str]=mapped_column(String(64),nullable=False)
    aigc_classification:Mapped[str]=mapped_column(String(50),nullable=False)
    disclosure_required:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True,server_default="true")
    reasons_json:Mapped[str]=mapped_column(Text,nullable=False,default="[]")
    evaluated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(
        CheckConstraint("policy_status IN ('POLICY_PASS','POLICY_REVIEW','POLICY_FAIL')",
                        name="growth_policy_status"),
        CheckConstraint("originality_status IN ('ORIGINAL','DUPLICATE','REVIEW')",
                        name="growth_originality_status"),
        Index("ix_growth_policy_creative_time","creative_id","evaluated_at"),
        Index("ix_growth_policy_signature","originality_signature"),
    )


class GrowthQuotaEvent(Base):
    __tablename__="growth_quota_events"
    event_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    idempotency_key:Mapped[str]=mapped_column(String(180),nullable=False,unique=True)
    event_type:Mapped[str]=mapped_column(String(20),nullable=False)
    creative_id:Mapped[str|None]=mapped_column(ForeignKey("growth_creatives.creative_id"))
    delivery_id:Mapped[str|None]=mapped_column(String(36))
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(
        CheckConstraint("event_type IN ('EXPERIMENT','HANDOFF')",name="growth_quota_event_type"),
        Index("ix_growth_quota_type_time","event_type","occurred_at"),
    )


class GrowthSchedulerTick(Base):
    __tablename__="growth_scheduler_ticks"
    tick_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    decision:Mapped[str]=mapped_column(String(30),nullable=False)
    reason:Mapped[str]=mapped_column(String(200),nullable=False)
    creative_id:Mapped[str|None]=mapped_column(String(100))
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(
        CheckConstraint("decision IN ('STARTED','WAITING','BLOCKED','GOAL_REACHED','QUOTA_REACHED')",
                        name="growth_scheduler_decision"),
        Index("ix_growth_scheduler_tick_time","observed_at"),
    )

class GrowthStateTransition(Base):
    __tablename__="growth_state_transitions"
    transition_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    experiment_id:Mapped[str|None]=mapped_column(String(100))
    job_id:Mapped[str|None]=mapped_column(String(100))
    source_state:Mapped[str]=mapped_column(String(40),nullable=False)
    target_state:Mapped[str]=mapped_column(String(40),nullable=False)
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    transitioned_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(Index("ix_growth_transition_experiment_time", "experiment_id", "transitioned_at"),)

class GrowthMediaArtifact(Base):
    """Immutable identity and verification record for one physical render artifact."""
    __tablename__ = "growth_media_artifacts"
    artifact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    creative_id: Mapped[str] = mapped_column(ForeignKey("growth_creatives.creative_id"), nullable=False)
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    render_job_id: Mapped[str] = mapped_column(ForeignKey("growth_jobs.job_id"), nullable=False)
    source_render_attempt: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="RAILWAY_VOLUME")
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    staging_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="video/mp4")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    codec: Mapped[str] = mapped_column(String(30), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_manifest: Mapped[str] = mapped_column(Text, nullable=False)
    storage_state: Mapped[str] = mapped_column(String(30), nullable=False, default="STORAGE_PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("render_job_id", "source_render_attempt", name="uq_media_job_attempt"),
        UniqueConstraint("artifact_id", "creative_id", name="uq_media_artifact_creative"),
        Index("ix_media_creative_state_created", "creative_id", "storage_state", "created_at"),
        CheckConstraint("storage_provider = 'RAILWAY_VOLUME'", name="media_storage_provider"),
        CheckConstraint("storage_state IN ('RENDERED_TEMPORARY','STORAGE_PENDING','STORING','STORED_UNVERIFIED','STORED_VERIFIED','STORAGE_FAILED','ARTIFACT_DISCARDED','ARTIFACT_MISSING','ARTIFACT_CORRUPT','UNKNOWN')", name="media_storage_state"),
        CheckConstraint("size_bytes > 0 AND duration_ms > 0 AND width > 0 AND height > 0 AND version > 0", name="media_positive_metadata"),
        CheckConstraint("length(sha256) = 64", name="media_sha256_length"),
    )
