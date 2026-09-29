"""Durable delivery identity bound to the immutable action/effect ledger."""
from datetime import datetime

from sqlalchemy import (CheckConstraint, DateTime, ForeignKeyConstraint, Index,
    String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class DeliveryEffect(Base):
    __tablename__ = "delivery_effects"

    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action_contract_id: Mapped[str] = mapped_column(String(36), nullable=False)
    effect_id: Mapped[str] = mapped_column(String(36), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    creative_id: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    target_account_id: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PREPARED")
    provider_reference: Mapped[str | None] = mapped_column(String(300))
    public_post_id: Mapped[str | None] = mapped_column(String(300))
    failure_class: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["effect_id", "action_contract_id"],
            ["effect_ledger.effect_id", "effect_ledger.action_contract_id"],
            name="fk_delivery_effect_contract",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "creative_id"],
            ["growth_media_artifacts.artifact_id", "growth_media_artifacts.creative_id"],
            name="fk_delivery_artifact_creative",
        ),
        UniqueConstraint("effect_id", name="uq_delivery_effect"),
        UniqueConstraint("action_contract_id", name="uq_delivery_contract"),
        CheckConstraint(
            "target IN ('ANDROID_SHARE_HANDOFF','TIKTOK_OFFICIAL_DIRECT_POST','TIKTOK_OFFICIAL_UPLOAD_DRAFT')",
            name="delivery_target",
        ),
        CheckConstraint(
            "state IN ('UNKNOWN','PREPARED','HANDOFF_INITIATED','DISPATCHED','PROCESSING','FAILED','CONFIRMED')",
            name="delivery_state",
        ),
        CheckConstraint("length(artifact_sha256) = 64", name="delivery_artifact_sha_length"),
        CheckConstraint(
            "(target = 'ANDROID_SHARE_HANDOFF' AND provider = 'ANDROID_SHARE') OR "
            "(target IN ('TIKTOK_OFFICIAL_DIRECT_POST','TIKTOK_OFFICIAL_UPLOAD_DRAFT') "
            "AND provider = 'TIKTOK_OFFICIAL')",
            name="delivery_provider_matches_target",
        ),
        CheckConstraint(
            "state != 'CONFIRMED' OR confirmed_at IS NOT NULL",
            name="delivery_confirmation_timestamp",
        ),
        Index("ix_delivery_state_updated", "state", "updated_at"),
        Index("ix_delivery_provider_reference", "provider", "provider_reference"),
    )
