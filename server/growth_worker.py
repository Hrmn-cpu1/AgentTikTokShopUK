"""Durable queue operations for the growth engine."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from .growth_models import GrowthCreative
from .growth_queue_models import GrowthJob, utcnow

def enqueue_job(session: Session, creative_id: str, job_type: str):
    key = creative_id + ":" + job_type
    old = session.scalar(select(GrowthJob).where(GrowthJob.idempotency_key == key))
    if old:
        return old
    now = utcnow()
    job = GrowthJob(job_id=str(uuid4()), creative_id=creative_id, job_type=job_type,
        idempotency_key=key, state="PENDING", attempts=0, available_at=now,
        created_at=now, updated_at=now)
    session.add(job)
    session.flush()
    return job

def seed_scripted_creatives(session: Session):
    rows = session.scalars(select(GrowthCreative).where(GrowthCreative.state == "SCRIPTED")).all()
    for creative in rows:
        enqueue_job(session, creative.creative_id, "PREPARE_ASSETS")
    session.commit()
    return len(rows)

def claim_due_job(session: Session, worker_id: str):
    now = utcnow()
    job = session.scalar(select(GrowthJob).where(
        GrowthJob.state.in_(("PENDING", "RETRY")), GrowthJob.available_at <= now)
        .order_by(GrowthJob.available_at).limit(1))
    if not job:
        return None
    job.state = "RUNNING"
    job.lease_owner = worker_id
    job.lease_until = now + timedelta(seconds=120)
    job.attempts += 1
    job.updated_at = now
    session.commit()
    session.refresh(job)
    return job

def finish_internal_job(session: Session, job: GrowthJob):
    creative = session.get(GrowthCreative, job.creative_id)
    if not creative:
        job.state = "FAILED"
        job.last_error = "creative_missing"
    elif job.job_type == "PREPARE_ASSETS":
        creative.state = "ASSETS_PENDING"
        enqueue_job(session, creative.creative_id, "RENDER_VIDEO")
        job.state = "SUCCEEDED"
        job.last_error = None
    else:
        job.state = "BLOCKED"
        job.last_error = "provider_not_configured"
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = utcnow()
    session.commit()
    return job.state
