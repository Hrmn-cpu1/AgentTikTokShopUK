"""Explicit, review-only ASMR draft promotion into the existing durable volume.

Never invoked by an API/worker automatically. Does not publish, approve rights,
edit the draft manifest, create infrastructure, or call paid media providers.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import uuid

from .asmr_reels import verify_asmr_draft
from .media_storage import (
    MediaArtifactCorrupt,
    MediaArtifactMissing,
    MediaQuotaExceeded,
    RailwayVolumeMediaStore,
    artifact_object_key,
    hash_file,
)


@dataclass(frozen=True)
class AsmrVolumeReceipt:
    object_key: str
    sha256: str
    size_bytes: int
    storage_state: str = "VOLUME_READBACK_VERIFIED_PENDING_REVIEW"
    publication: str = "BLOCKED"


def _verified_receipt(
    store: RailwayVolumeMediaStore, key: str, sha: str, size: int
) -> AsmrVolumeReceipt:
    object_info = store.verify_object(
        key, expected_sha256=sha, expected_size_bytes=size
    )
    if object_info.sha256 != sha or object_info.size_bytes != size:
        raise MediaArtifactCorrupt("durable readback disagrees with the draft")
    return AsmrVolumeReceipt(object_key=key, sha256=sha, size_bytes=size)


def promote_verified_asmr_draft(
    *,
    draft_dir: str | Path,
    store: RailwayVolumeMediaStore,
    creative_id: str,
    render_job_id: str,
    render_attempt_id: str,
) -> AsmrVolumeReceipt:
    """Copy verified MP4 to a staged attempt and atomically expose/read it back.

    Requires unique job/attempt IDs from an external lease/fence manager. Repeat
    calls are idempotent only for the same trusted creative ID and file SHA.
    Do not use this to claim human review, production readiness or publication.
    """
    if not isinstance(store, RailwayVolumeMediaStore):
        raise TypeError("store must be an explicitly configured RailwayVolumeMediaStore")
    checked = verify_asmr_draft(draft_dir)
    if checked["creativeId"] != creative_id:
        raise MediaArtifactCorrupt("creative identity differs from the reviewed draft")
    sha = str(checked["videoSha256"])
    source = Path(draft_dir) / "reel.mp4"
    size = source.stat().st_size
    key = artifact_object_key(creative_id, sha)
    staging = store.staging_key(render_job_id, render_attempt_id)

    # Replayed promotion: readback already-persisted content, do not copy again.
    try:
        return _verified_receipt(store, key, sha, size)
    except MediaArtifactMissing:
        pass

    if size > store.max_artifact_bytes:
        raise MediaQuotaExceeded("verified ASMR draft exceeds durable artifact quota")
    store.preflight()
    directory = store.staging_directory(staging)
    staged = directory / "growth.mp4"  # Storage API's existing immutable stage name.
    if staged.is_symlink():
        raise MediaArtifactCorrupt("ASMR staged media cannot be a symlink")

    if not staged.exists():
        temp = directory / (".upload-tmp-" + uuid.uuid4().hex + ".mp4")
        try:
            with source.open("rb") as src, temp.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            copied_sha, copied_size = hash_file(temp)
            if copied_sha != sha or copied_size != size:
                raise MediaArtifactCorrupt("ASMR source changed during staged copy")
            try:
                os.link(temp, staged)  # Exclusive, immutable stage claim.
                fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except FileExistsError:
                pass  # Another attempt won: verify the existing stage below.
        finally:
            temp.unlink(missing_ok=True)

    if staged.is_symlink() or not staged.is_file():
        raise MediaArtifactCorrupt("ASMR staged render is not a regular file")
    stage_sha, stage_bytes = hash_file(staged)
    if stage_sha != sha or stage_bytes != size:
        raise MediaArtifactCorrupt("ASMR staged render failed SHA-256 readback")

    store.promote_staging(
        object_key=key, staging_key=staging,
        expected_sha256=sha, expected_size_bytes=size,
    )
    receipt = _verified_receipt(store, key, sha, size)
    # Cleanup is only allowed after a durable hash readback.
    store.cleanup_staging(staging)
    return receipt
