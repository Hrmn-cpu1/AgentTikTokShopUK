"""Durable lease-based growth queue. Safe across worker restarts and duplicate ticks."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import DateTime, Integer, String, Text, CheckConstraint, ForeignKey, Index, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class GrowthJob(Base):
    __tablename__ = "growth_jobs"
    job_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    creative_id: Mapped[str] = mapped_column(ForeignKey("growth_creatives.creative_id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    lease_attempt_id: Mapped[str | None] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("job_id", "creative_id", name="uq_growth_job_id_creative"),
        CheckConstraint("state IN ('PENDING','RUNNING','SUCCEEDED','RETRY','FAILED','BLOCKED')", name="growth_job_state"),
        CheckConstraint("attempts >= 0", name="growth_job_attempts_nonnegative"),
        Index("ix_growth_jobs_due", "state", "available_at"),
    )

def utcnow():
    return datetime.now(timezone.utc)

def lease_expiry(seconds: int = 120):
    return utcnow() + timedelta(seconds=seconds)
