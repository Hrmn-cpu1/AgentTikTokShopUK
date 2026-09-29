"""Durable queue operations for the growth engine."""
from datetime import timedelta
import json
import logging
import os
import threading
import time
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from .growth_models import GrowthControl, GrowthCreative, GrowthStateTransition
from .growth_queue_models import GrowthJob, utcnow
from .growth_renderer import render_growth_plan

logger = logging.getLogger(__name__)

def record_transition(session: Session, source: str, target: str, reason: str,
                      experiment_id: str | None = None, job_id: str | None = None):
    session.add(GrowthStateTransition(transition_id=str(uuid4()), experiment_id=experiment_id,
        job_id=job_id, source_state=source, target_state=target, reason=reason, transitioned_at=utcnow()))

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
    control = session.get(GrowthControl, "default")
    if control is not None and control.mode not in {"READY", "RUNNING"}:
        return None
    now = utcnow()
    job = session.scalar(select(GrowthJob).where(
        ((GrowthJob.state.in_(("PENDING", "RETRY"))) | ((GrowthJob.state == "RUNNING") & (GrowthJob.lease_until < now))), GrowthJob.available_at <= now)
        .order_by(GrowthJob.available_at).with_for_update(skip_locked=True).limit(1))
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
    control = session.get(GrowthControl, "default")
    if control is not None and control.mode not in {"READY", "RUNNING"}:
        job.state = "BLOCKED" if control.mode == "STOPPED" else "PENDING"
        job.available_at = utcnow()
        job.last_error = "Cancelled at safe checkpoint: " + control.mode
        job.lease_owner = None
        job.lease_until = None
        job.updated_at = utcnow()
        session.commit()
        return job.state
    creative = session.get(GrowthCreative, job.creative_id)
    if not creative:
        job.state = "FAILED"
        job.last_error = "creative_missing"
    elif job.job_type == "PREPARE_ASSETS":
        source_state = creative.state
        creative.state = "ASSETS_PENDING"
        record_transition(session, source_state, creative.state, "original asset plan accepted for render",
                          creative.experiment_id, job.job_id)
        enqueue_job(session, creative.creative_id, "RENDER_VIDEO")
        job.state = "SUCCEEDED"
        job.last_error = None
    elif job.job_type == "RENDER_VIDEO" and creative.state in {"ASSETS_PENDING", "RENDERING"}:
        if creative.state != "RENDERING":
            source_state = creative.state
            creative.state = "RENDERING"
            record_transition(session, source_state, creative.state, "worker began FFmpeg render",
                              creative.experiment_id, job.job_id)
            session.commit()
        def cancelled():
            session.expire_all()
            current = session.get(GrowthControl, "default")
            return current is not None and current.mode not in {"READY", "RUNNING"}
        output, digest, cleanup = render_growth_plan(creative.plan_json, should_cancel=cancelled)
        try:
            manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
            quality = manifest.get("qualityGate", {})
            creative.media_ref = "local-render://" + creative.creative_id + "/" + output.name
            creative.media_hash = digest
            creative.quality_json = json.dumps(quality, ensure_ascii=False, sort_keys=True)
            creative.quality_status = quality.get("status", "QUALITY_REVIEW")
            creative.creative_learning_eligible = False
            creative.style_baseline_eligible = False
            creative.exclusion_reason = "AWAITING_VERIFIED_PUBLICATION_AND_OBSERVATION"
            if creative.quality_status == "QUALITY_FAIL":
                source_state = creative.state
                creative.state = "FAILED"
                control = session.get(GrowthControl, "default")
                if control:
                    old = control.mode
                    control.mode = "BLOCKED"
                    control.updated_at = utcnow()
                    record_transition(session, old, "BLOCKED", "creative quality gate failed",
                                      creative.experiment_id, job.job_id)
                job.state = "FAILED"
                job.last_error = "quality_gate_failed"
                record_transition(session, source_state, creative.state, "quality gate hard failure",
                                  creative.experiment_id, job.job_id)
            else:
                source_state = creative.state
                creative.state = "READY"
                job.state = "SUCCEEDED"
                job.last_error = None
                control = session.get(GrowthControl, "default")
                if control and control.mode in {"READY", "RUNNING"}:
                    old = control.mode
                    control.mode = "ACTION_REQUIRED"
                    control.updated_at = utcnow()
                    record_transition(session, old, "ACTION_REQUIRED",
                                      "render complete; TikTok import/publication require owner confirmation",
                                      creative.experiment_id, job.job_id)
                record_transition(session, source_state, creative.state,
                                  f"render finished with {creative.quality_status}",
                                  creative.experiment_id, job.job_id)
                # The creative/control state is the durable human gate. Do not leave a
                # delivery job pretending there is an automated provider to run.
        finally:
            cleanup()
    elif job.job_type == "DELIVERY_ACTION_REQUIRED":
        job.state = "BLOCKED"
        job.last_error = "owner_confirmation_required"
    else:
        job.state = "BLOCKED"
        job.last_error = "provider_not_configured"
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = utcnow()
    session.commit()
    return job.state


def run_growth_worker(engine, stop: threading.Event, poll_seconds: float = 1.0):
    """Single-process Railway poller; work and leases remain in PostgreSQL."""
    from sqlalchemy.orm import Session
    worker_id = f"railway-worker-{os.getpid()}"
    while not stop.is_set():
        try:
            with Session(engine) as session:
                job = claim_due_job(session, worker_id)
                job_id = job.job_id if job else None
            if job_id:
                with Session(engine) as session:
                    current = session.get(GrowthJob, job_id)
                    try:
                        if current is not None and current.state == "RUNNING":
                            finish_internal_job(session, current)
                    except InterruptedError:
                        session.rollback()
                        current = session.get(GrowthJob, job_id)
                        control = session.get(GrowthControl, "default")
                        if current is not None:
                            old = current.state
                            current.state = "BLOCKED" if control and control.mode == "STOPPED" else "PENDING"
                            current.last_error = "cancelled_at_safe_checkpoint"
                            current.lease_owner = None
                            current.lease_until = None
                            current.updated_at = utcnow()
                            record_transition(session, old, current.state, current.last_error,
                                              job_id=current.job_id)
                            session.commit()
                    except Exception as exc:
                        session.rollback()
                        current = session.get(GrowthJob, job_id)
                        if current is not None and current.state == "RUNNING":
                            retry_or_fail_job(session, current, type(exc).__name__)
                        logger.exception("Growth job %s failed", job_id)
                continue
        except InterruptedError:
            logger.info("Growth rendering paused or stopped at checkpoint")
        except Exception:
            logger.exception("Growth worker iteration failed")
        stop.wait(poll_seconds)


def retry_or_fail_job(session: Session, job: GrowthJob, error: str, max_attempts: int = 3):
    old = job.state
    now = utcnow()
    if job.attempts < max_attempts:
        job.state = "RETRY"
        job.available_at = now + timedelta(seconds=min(300, 2 ** max(1, job.attempts)))
    else:
        job.state = "FAILED"
        creative = session.get(GrowthCreative, job.creative_id)
        if creative:
            creative.state = "FAILED"
        control = session.get(GrowthControl, "default")
        if control and control.mode in {"READY", "RUNNING"}:
            control.mode = "FAILED"
            control.updated_at = now
    job.last_error = error[:500]
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = now
    record_transition(session, old, job.state, "bounded retry after internal worker failure",
                      job_id=job.job_id, experiment_id=None)
    session.commit()
