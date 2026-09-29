"""Read-only durable-media provenance verification for startup telemetry.

This module never mutates database rows or media bytes and performs no network I/O.
It exists so a deployment can prove the DB-declared artifact digest against the
actual Railway volume bytes without exposing an unauthenticated diagnostic API.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .growth_models import GrowthMediaArtifact
from .media_storage import MediaStorageError, RailwayVolumeMediaStore

logger = logging.getLogger(__name__)


def inspect_media_artifact(artifact: Any, media_store: RailwayVolumeMediaStore) -> dict:
    manifest_sha = None
    try:
        manifest = json.loads(artifact.quality_manifest or "{}")
        candidate = manifest.get("sha256")
        if isinstance(candidate, str):
            manifest_sha = candidate
    except (TypeError, ValueError, json.JSONDecodeError):
        manifest_sha = None

    record = {
        "artifact_id": artifact.artifact_id,
        "creative_id": artifact.creative_id,
        "render_job_id": artifact.render_job_id,
        "source_render_attempt": artifact.source_render_attempt,
        "object_key": artifact.object_key,
        "db_sha256": artifact.sha256,
        "manifest_sha256": manifest_sha,
        "db_size_bytes": artifact.size_bytes,
        "physical_sha256": None,
        "physical_size_bytes": None,
        "quality_status": artifact.quality_status,
        "storage_state": artifact.storage_state,
        "result": "NOT_PROVEN",
        "error_class": None,
    }
    try:
        verified = media_store.verify_object(
            artifact.object_key,
            expected_sha256=artifact.sha256,
            expected_size_bytes=artifact.size_bytes,
            expected_content_type=artifact.content_type,
        )
        record["physical_sha256"] = verified.sha256
        record["physical_size_bytes"] = verified.size_bytes
        record["result"] = "PROVEN" if (
            manifest_sha == artifact.sha256
            and verified.sha256 == artifact.sha256
            and verified.size_bytes == artifact.size_bytes
            and artifact.quality_status == "QUALITY_PASS"
            and artifact.storage_state == "STORED_VERIFIED"
        ) else "NOT_PROVEN"
    except MediaStorageError as exc:
        record["error_class"] = type(exc).__name__
    return record


def audit_durable_media_provenance(engine, media_store: RailwayVolumeMediaStore | None) -> list[dict]:
    """Log exact DB/manifest/volume identity for all currently verified artifacts."""
    if media_store is None:
        logger.warning("MEDIA_PROVENANCE_T2 result=NOT_PROVEN reason=media_store_unavailable")
        return []
    with Session(engine) as session:
        artifacts = session.scalars(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.storage_state == "STORED_VERIFIED",
            GrowthMediaArtifact.quality_status == "QUALITY_PASS",
        ).order_by(GrowthMediaArtifact.created_at)).all()

    records = []
    for artifact in artifacts:
        record = inspect_media_artifact(artifact, media_store)
        records.append(record)
        log = logger.info if record["result"] == "PROVEN" else logger.warning
        log(
            "MEDIA_PROVENANCE_T2 artifact_id=%s creative_id=%s render_job_id=%s "
            "attempt=%s object_key=%s db_sha=%s manifest_sha=%s physical_sha=%s "
            "db_size=%s physical_size=%s quality=%s storage=%s result=%s error=%s",
            record["artifact_id"], record["creative_id"], record["render_job_id"],
            record["source_render_attempt"], record["object_key"], record["db_sha256"],
            record["manifest_sha256"], record["physical_sha256"], record["db_size_bytes"],
            record["physical_size_bytes"], record["quality_status"], record["storage_state"],
            record["result"], record["error_class"],
        )
    return records
