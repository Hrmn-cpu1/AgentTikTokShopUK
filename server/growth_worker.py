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
from .growth_models import GrowthControl, GrowthCreative, GrowthMediaArtifact, GrowthStateTransition
from .growth_queue_models import GrowthJob, utcnow
from .growth_renderer import render_growth_plan
from .media_storage import (MediaArtifactCorrupt, MediaArtifactMissing, MediaQuotaExceeded,
    MediaStorageError, MediaStorageNotConfigured, RailwayVolumeMediaStore, artifact_object_key, hash_file)

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

def claim_due_job(session: Session, worker_id: str, *, media_storage_available: bool = True):
    control = session.get(GrowthControl, "default")
    mode = control.mode if control is not None else "READY"
    if mode not in {"READY", "RUNNING", "ACTION_REQUIRED"}:
        return None
    now = utcnow()
    query = select(GrowthJob).where(
        ((GrowthJob.state.in_(("PENDING", "RETRY"))) | ((GrowthJob.state == "RUNNING") & (GrowthJob.lease_until < now))), GrowthJob.available_at <= now)
    # ACTION_REQUIRED remains latched for the earlier delivery. Only the explicit,
    # no-publication media materialization job may run through that gate.
    if mode == "ACTION_REQUIRED":
        query = query.where(GrowthJob.job_type == "MATERIALIZE_DURABLE_MEDIA")
    else:
        query = query.where(GrowthJob.job_type != "MATERIALIZE_DURABLE_MEDIA")
    if not media_storage_available:
        query = query.where(GrowthJob.job_type.notin_(("RENDER_VIDEO", "MATERIALIZE_DURABLE_MEDIA")))
    job = session.scalar(query
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

def _clear_job_lease(job: GrowthJob):
    job.lease_owner = None
    job.lease_until = None
    job.updated_at = utcnow()


def _retry_storage_job(session: Session, job: GrowthJob, creative: GrowthCreative,
                       artifact: GrowthMediaArtifact | None, reason: str):
    old_state = job.state
    now = utcnow()
    job.state = "RETRY"
    job.available_at = now + timedelta(seconds=min(3600, 2 ** min(10, max(1, job.attempts))))
    job.last_error = reason[:200]
    if artifact is not None:
        artifact.storage_state = "UNKNOWN"
        artifact.failure_reason = reason[:200]
    _clear_job_lease(job)
    record_transition(session, old_state, job.state, "durable media storage will be reconciled before another render",
                      creative.experiment_id, job.job_id)
    session.commit()
    return job.state


def _block_corrupt_artifact(session: Session, job: GrowthJob, creative: GrowthCreative,
                            artifact: GrowthMediaArtifact, reason: str):
    old_state = job.state
    artifact.storage_state = "ARTIFACT_CORRUPT"
    artifact.failure_reason = reason[:200]
    creative.state = "BLOCKED"
    job.state = "BLOCKED"
    job.last_error = reason[:200]
    _clear_job_lease(job)
    record_transition(session, old_state, "BLOCKED", "media integrity conflict; artifact preserved for review",
                      creative.experiment_id, job.job_id)
    session.commit()
    return job.state


def _finish_verified_artifact(session: Session, job: GrowthJob, creative: GrowthCreative,
                              artifact: GrowthMediaArtifact, storage: RailwayVolumeMediaStore):
    now = utcnow()
    old_state = creative.state
    artifact.storage_state = "STORED_VERIFIED"
    artifact.stored_at = artifact.stored_at or now
    artifact.verified_at = now
    artifact.failure_reason = None
    creative.media_ref = f"media-artifact://{artifact.artifact_id}"
    creative.media_hash = artifact.sha256
    creative.quality_status = artifact.quality_status
    creative.quality_json = json.dumps(json.loads(artifact.quality_manifest).get("qualityGate", {}),
                                       ensure_ascii=False, sort_keys=True)
    creative.creative_learning_eligible = False
    creative.style_baseline_eligible = False
    creative.exclusion_reason = "AWAITING_VERIFIED_PUBLICATION_AND_OBSERVATION"
    if artifact.quality_status == "QUALITY_PASS":
        creative.state = "READY"
    else:
        # Stored media under QUALITY_REVIEW is durable evidence, not ready for delivery.
        creative.state = "BLOCKED"
    job.state = "SUCCEEDED"
    job.last_error = None
    _clear_job_lease(job)
    control = session.get(GrowthControl, "default")
    if control and control.mode in {"READY", "RUNNING"}:
        previous = control.mode
        control.mode = "ACTION_REQUIRED"
        control.updated_at = now
        reason = ("MEDIA_READY: quality passed and durable SHA-256 readback verified"
                  if artifact.quality_status == "QUALITY_PASS"
                  else "Media is durable but quality requires owner review")
        record_transition(session, previous, "ACTION_REQUIRED", reason,
                          creative.experiment_id, job.job_id)
    record_transition(session, old_state, creative.state,
                      f"durable artifact {artifact.storage_state}; quality={artifact.quality_status}",
                      creative.experiment_id, job.job_id)
    session.commit()
    # The original render remains until the row confirms STORED_VERIFIED.
    try:
        storage.cleanup_staging(artifact.staging_key)
    except MediaStorageError:
        logger.warning("Verified media artifact %s left render staging for later cleanup", artifact.artifact_id)
    return job.state


def _persist_render_artifact(session: Session, job: GrowthJob, creative: GrowthCreative,
                             storage: RailwayVolumeMediaStore, staging_key: str,
                             output: str, digest: str, manifest: dict):
    quality = manifest.get("qualityGate", {})
    quality_status = quality.get("status", "QUALITY_REVIEW")
    size_bytes = __import__("pathlib").Path(output).stat().st_size
    actual_digest, actual_size = hash_file(output)
    if actual_digest != digest or actual_size != size_bytes or manifest.get("sha256") != digest:
        raise MediaArtifactCorrupt("render file, renderer hash, and manifest hash disagree")
    if size_bytes <= 0 or size_bytes > storage.max_artifact_bytes:
        raise MediaQuotaExceeded("rendered MP4 exceeds configured artifact size")
    duration_ms = round(float(manifest.get("durationSeconds") or 0) * 1000)
    width, height = int(manifest.get("width") or 0), int(manifest.get("height") or 0)
    codec = str(manifest.get("videoCodec") or "").lower()
    if not duration_ms or width < 1 or height < 1 or codec != "h264":
        raise MediaArtifactCorrupt("render metadata is incomplete or not an H.264 MP4")
    attempt = staging_key.rsplit("/", 1)[-1]
    artifact = GrowthMediaArtifact(
        artifact_id=str(uuid4()), creative_id=creative.creative_id,
        experiment_id=creative.experiment_id, render_job_id=job.job_id,
        source_render_attempt=attempt, storage_provider=storage.provider,
        object_key=artifact_object_key(creative.creative_id, digest), staging_key=staging_key,
        content_type="video/mp4", size_bytes=size_bytes, sha256=digest,
        duration_ms=duration_ms, width=width, height=height, codec=codec,
        quality_status=quality_status,
        quality_manifest=json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        storage_state="RENDERED_TEMPORARY", created_at=utcnow(), version=1)
    session.add(artifact)
    session.commit()
    return artifact


def finish_internal_job(session: Session, job: GrowthJob, *, media_store: RailwayVolumeMediaStore | None = None):
    control = session.get(GrowthControl, "default")
    is_action_required_materialization = (job.job_type == "MATERIALIZE_DURABLE_MEDIA"
        and control is not None and control.mode == "ACTION_REQUIRED")
    if control is not None and control.mode not in {"READY", "RUNNING"} and not is_action_required_materialization:
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
    elif ((job.job_type == "RENDER_VIDEO" and
            creative.state in {"ASSETS_PENDING", "RENDERING", "BLOCKED"}) or
          (job.job_type == "MATERIALIZE_DURABLE_MEDIA" and creative.state in {"READY", "RENDERING"})):
        if media_store is None:
            job.state = "PENDING"
            job.available_at = utcnow() + timedelta(minutes=5)
            job.last_error = "media_storage_not_configured"
            _clear_job_lease(job)
            session.commit()
            return job.state
        try:
            media_store.preflight()
        except MediaStorageError as exc:
            return _retry_storage_job(session, job, creative, None, type(exc).__name__)

        # First reconcile artifacts from a prior crash. This lookup is read-only;
        # only a complete staging file or already-canonical object may be promoted.
        artifacts = session.scalars(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.render_job_id == job.job_id,
            GrowthMediaArtifact.storage_state.notin_(("ARTIFACT_MISSING", "ARTIFACT_CORRUPT", "STORAGE_FAILED"))
        ).order_by(GrowthMediaArtifact.created_at.desc())).all()
        for artifact in artifacts:
            try:
                if artifact.storage_state == "STORED_VERIFIED":
                    verified = media_store.verify_object(artifact.object_key,
                        expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes,
                        expected_content_type=artifact.content_type)
                else:
                    artifact.storage_state = "STORING"
                    session.commit()
                    media_store.promote_staging(object_key=artifact.object_key,
                        staging_key=artifact.staging_key, expected_sha256=artifact.sha256,
                        expected_size_bytes=artifact.size_bytes)
                    artifact.storage_state = "STORED_UNVERIFIED"
                    artifact.stored_at = utcnow()
                    session.commit()
                    verified = media_store.verify_object(artifact.object_key,
                        expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes,
                        expected_content_type=artifact.content_type)
                if verified.sha256 != artifact.sha256 or verified.size_bytes != artifact.size_bytes:
                    raise MediaArtifactCorrupt("storage readback does not match artifact identity")
                return _finish_verified_artifact(session, job, creative, artifact, media_store)
            except MediaArtifactMissing:
                artifact.storage_state = "ARTIFACT_MISSING"
                artifact.failure_reason = "authoritative volume read found no canonical object or complete stage"
                session.commit()
                # A new render is a new physical artifact; preserve the missing row.
                continue
            except MediaArtifactCorrupt as exc:
                return _block_corrupt_artifact(session, job, creative, artifact, str(exc))
            except MediaStorageError as exc:
                return _retry_storage_job(session, job, creative, artifact, type(exc).__name__)

        # A process can die after FFmpeg finishes but before its artifact row commits.
        # Recover completed staged attempts before rendering another physical file.
        try:
            for recovered_key in media_store.staged_attempts(job.job_id):
                recovered_dir = media_store.staging_directory(recovered_key)
                output = recovered_dir / "growth.mp4"
                manifest_path = recovered_dir / "manifest.json"
                if not output.is_file() or not manifest_path.is_file():
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                digest, _ = hash_file(output)
                if manifest.get("sha256") != digest:
                    job.state = "BLOCKED"
                    job.last_error = "orphaned_render_manifest_hash_mismatch"
                    creative.state = "BLOCKED"
                    _clear_job_lease(job)
                    record_transition(session, "RENDERING", "BLOCKED",
                        "orphan staging file failed manifest hash verification", creative.experiment_id, job.job_id)
                    session.commit()
                    return job.state
                artifact = _persist_render_artifact(session, job, creative, media_store,
                    recovered_key, str(output), digest, manifest)
                artifact.storage_state = "STORING"
                session.commit()
                media_store.promote_staging(object_key=artifact.object_key,
                    staging_key=artifact.staging_key, expected_sha256=artifact.sha256,
                    expected_size_bytes=artifact.size_bytes)
                artifact.storage_state = "STORED_UNVERIFIED"
                artifact.stored_at = utcnow()
                session.commit()
                verified = media_store.verify_object(artifact.object_key,
                    expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes)
                if verified.sha256 != artifact.sha256:
                    raise MediaArtifactCorrupt("recovered artifact failed readback verification")
                return _finish_verified_artifact(session, job, creative, artifact, media_store)
        except MediaArtifactCorrupt as exc:
            job.state = "BLOCKED"
            job.last_error = str(exc)[:200]
            creative.state = "BLOCKED"
            _clear_job_lease(job)
            record_transition(session, "RENDERING", "BLOCKED", "recovered render is corrupt and preserved",
                              creative.experiment_id, job.job_id)
            session.commit()
            return job.state
        except MediaStorageError as exc:
            return _retry_storage_job(session, job, creative, None, type(exc).__name__)

        if creative.state != "RENDERING":
            source_state = creative.state
            creative.state = "RENDERING"
            record_transition(session, source_state, creative.state, "worker began FFmpeg render",
                              creative.experiment_id, job.job_id)
            session.commit()
        try:
            media_store.preflight()
        except MediaStorageError as exc:
            return _retry_storage_job(session, job, creative, None, type(exc).__name__)
        render_attempt_id = f"try-{job.attempts}-{uuid4().hex[:20]}"
        staging_key = media_store.staging_key(job.job_id, render_attempt_id)
        try:
            output_dir = media_store.staging_directory(staging_key)
        except MediaStorageError as exc:
            return _retry_storage_job(session, job, creative, None, type(exc).__name__)
        def cancelled():
            session.expire_all()
            current = session.get(GrowthControl, "default")
            return current is not None and current.mode not in {"READY", "RUNNING"} and not (
                job.job_type == "MATERIALIZE_DURABLE_MEDIA" and current.mode == "ACTION_REQUIRED")
        try:
            output, digest, _cleanup = render_growth_plan(creative.plan_json, output_dir=output_dir,
                                                          should_cancel=cancelled)
        except InterruptedError:
            # Cancellation is a terminal render decision; the partial, invalid render is disposable.
            media_store.cleanup_staging(staging_key)
            raise
        except Exception as exc:
            media_store.cleanup_staging(staging_key)
            raise exc
        try:
            manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
            quality = manifest.get("qualityGate", {})
            creative.media_ref = None
            creative.media_hash = digest
            creative.quality_json = json.dumps(quality, ensure_ascii=False, sort_keys=True)
            creative.quality_status = quality.get("status", "QUALITY_REVIEW")
            creative.creative_learning_eligible = False
            creative.style_baseline_eligible = False
            creative.exclusion_reason = "AWAITING_VERIFIED_PUBLICATION_AND_OBSERVATION"
            if creative.quality_status == "QUALITY_FAIL":
                artifact = _persist_render_artifact(session, job, creative, media_store,
                    staging_key, str(output), digest, manifest)
                artifact.storage_state = "ARTIFACT_DISCARDED"
                artifact.failure_reason = "quality_gate_failed; rendered bytes intentionally not retained"
                source_state = creative.state
                creative.state = "FAILED"
                control = session.get(GrowthControl, "default")
                if control and control.mode in {"READY", "RUNNING"}:
                    old = control.mode
                    control.mode = "BLOCKED"
                    control.updated_at = utcnow()
                    record_transition(session, old, "BLOCKED", "creative quality gate failed",
                                      creative.experiment_id, job.job_id)
                job.state = "FAILED"
                job.last_error = "quality_gate_failed"
                record_transition(session, source_state, creative.state, "quality gate hard failure",
                                  creative.experiment_id, job.job_id)
                _clear_job_lease(job)
                session.commit()
                media_store.cleanup_staging(staging_key)
                return job.state
            else:
                artifact = _persist_render_artifact(session, job, creative, media_store,
                    staging_key, str(output), digest, manifest)
                artifact.storage_state = "STORING"
                session.commit()
                media_store.promote_staging(object_key=artifact.object_key,
                    staging_key=artifact.staging_key, expected_sha256=artifact.sha256,
                    expected_size_bytes=artifact.size_bytes)
                artifact.storage_state = "STORED_UNVERIFIED"
                artifact.stored_at = utcnow()
                session.commit()
                verified = media_store.verify_object(artifact.object_key,
                    expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes,
                    expected_content_type=artifact.content_type)
                if verified.sha256 != digest or verified.size_bytes != artifact.size_bytes:
                    raise MediaArtifactCorrupt("durable media readback failed identity verification")
                return _finish_verified_artifact(session, job, creative, artifact, media_store)
        except MediaArtifactCorrupt as exc:
            artifact = locals().get("artifact")
            if artifact is not None:
                return _block_corrupt_artifact(session, job, creative, artifact, str(exc))
            raise
        except MediaStorageError as exc:
            artifact = locals().get("artifact")
            return _retry_storage_job(session, job, creative, artifact, type(exc).__name__)
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
    try:
        media_store = RailwayVolumeMediaStore.from_environment()
        media_store.preflight()
    except MediaStorageError as exc:
        media_store = None
        logger.warning("Durable media storage unavailable; render jobs will remain queued: %s", type(exc).__name__)
    while not stop.is_set():
        try:
            with Session(engine) as session:
                job = claim_due_job(session, worker_id, media_storage_available=media_store is not None)
                job_id = job.job_id if job else None
            if job_id:
                with Session(engine) as session:
                    current = session.get(GrowthJob, job_id)
                    try:
                        if current is not None and current.state == "RUNNING":
                            finish_internal_job(session, current, media_store=media_store)
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
