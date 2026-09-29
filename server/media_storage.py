"""Private, durable media artifacts stored on the Railway service volume.

No ephemeral-filesystem fallback exists. On Railway, the injected volume mount
is mandatory; local tests may inject a temporary root explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import uuid

CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 400 * 1024 * 1024
CONTENT_TYPE = "video/mp4"


class MediaStorageError(RuntimeError):
    """Storage could not establish the requested artifact state."""


class MediaStorageNotConfigured(MediaStorageError):
    pass


class MediaArtifactMissing(MediaStorageError):
    pass


class MediaArtifactCorrupt(MediaStorageError):
    pass


class MediaQuotaExceeded(MediaStorageError):
    pass


@dataclass(frozen=True)
class VerifiedMedia:
    path: Path
    size_bytes: int
    sha256: str
    content_type: str = CONTENT_TYPE


def hash_file(path: str | Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def artifact_object_key(creative_id: str, sha256: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", creative_id or ""):
        raise MediaStorageError("invalid creative identity")
    if not re.fullmatch(r"[a-f0-9]{64}", sha256 or ""):
        raise MediaStorageError("invalid sha256 identity")
    return f"media/{creative_id}/{sha256}.mp4"


class RailwayVolumeMediaStore:
    provider = "RAILWAY_VOLUME"

    def __init__(self, root: str | Path, *, max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
                 max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_absolute():
            raise MediaStorageNotConfigured("media volume root must be absolute")
        if type(max_artifact_bytes) is not int or max_artifact_bytes < 1024:
            raise MediaStorageNotConfigured("MEDIA_MAX_ARTIFACT_BYTES must be at least 1024")
        if type(max_total_bytes) is not int or max_total_bytes < max_artifact_bytes:
            raise MediaStorageNotConfigured("MEDIA_MAX_TOTAL_BYTES must be >= MEDIA_MAX_ARTIFACT_BYTES")
        self.max_artifact_bytes = max_artifact_bytes
        self.max_total_bytes = max_total_bytes

    @classmethod
    def from_environment(cls) -> "RailwayVolumeMediaStore":
        mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        # Never interpret an operator-controlled fallback path as durable on Railway.
        on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT_NAME") or os.environ.get("RAILWAY_PROJECT_ID"))
        if on_railway:
            if not mount:
                raise MediaStorageNotConfigured("Railway persistent volume is not attached")
            root = Path(mount) / "agenttiktok-media"
        else:
            root = os.environ.get("MEDIA_STORAGE_ROOT") or mount
            if not root:
                raise MediaStorageNotConfigured("MEDIA_STORAGE_ROOT or a Railway volume mount is required")
        try:
            max_file = int(os.environ.get("MEDIA_MAX_ARTIFACT_BYTES", DEFAULT_MAX_ARTIFACT_BYTES))
            max_total = int(os.environ.get("MEDIA_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL_BYTES))
            return cls(root, max_artifact_bytes=max_file, max_total_bytes=max_total)
        except (TypeError, ValueError) as exc:
            raise MediaStorageNotConfigured("invalid media storage quota configuration") from exc

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / (".write-test-" + uuid.uuid4().hex)
            with probe.open("xb") as stream:
                stream.write(b"ok")
                stream.flush()
                os.fsync(stream.fileno())
            probe.unlink()
        except OSError as exc:
            raise MediaStorageNotConfigured("Railway volume is unavailable or not writable") from exc

    def preflight(self) -> None:
        self._ensure_root()
        usage = self._usage_bytes()
        if usage + self.max_artifact_bytes > self.max_total_bytes:
            raise MediaQuotaExceeded("media volume artifact quota reached")
        try:
            free = shutil.disk_usage(self.root).free
        except OSError as exc:
            raise MediaStorageNotConfigured("could not inspect media volume capacity") from exc
        if free < self.max_artifact_bytes:
            raise MediaQuotaExceeded("not enough free volume space for the maximum configured MP4")

    def _usage_bytes(self) -> int:
        if not self.root.exists():
            return 0
        total = 0
        try:
            seen: set[tuple[int, int]] = set()
            for path in self.root.rglob("*.mp4"):
                if path.is_file() and not path.is_symlink():
                    stat = path.stat()
                    identity = (stat.st_dev, stat.st_ino)
                    if identity not in seen:
                        seen.add(identity)
                        total += stat.st_size
        except OSError as exc:
            raise MediaStorageNotConfigured("could not inspect media volume usage") from exc
        return total

    def _resolve(self, key: str) -> Path:
        if (not isinstance(key, str) or not key or "\\" in key or "\x00" in key
                or key.startswith("/") or re.match(r"^[A-Za-z]:", key)):
            raise MediaStorageError("unsafe media object key")
        parts = PurePosixPath(key).parts
        if not parts or any(part in ("", ".", "..") for part in parts):
            raise MediaStorageError("unsafe media object key")
        if any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in parts):
            raise MediaStorageError("unsafe media object key")
        target = self.root.joinpath(*parts)
        try:
            if not target.resolve(strict=False).is_relative_to(self.root):
                raise MediaStorageError("media object key escapes the mounted volume")
        except OSError as exc:
            raise MediaStorageNotConfigured("could not resolve media object on volume") from exc
        return target

    def staging_key(self, render_job_id: str, render_attempt_id: str) -> str:
        for value in (render_job_id, render_attempt_id):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value or ""):
                raise MediaStorageError("invalid render attempt identity")
        return f".staging/{render_job_id}/{render_attempt_id}"

    def staging_directory(self, staging_key: str) -> Path:
        path = self._resolve(staging_key)
        try:
            path.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                raise MediaStorageError("staging directory cannot be a symlink")
        except OSError as exc:
            raise MediaStorageNotConfigured("could not create staging directory on volume") from exc
        return path

    def staged_attempts(self, render_job_id: str) -> list[str]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", render_job_id or ""):
            raise MediaStorageError("invalid render job identity")
        parent = self._resolve(f".staging/{render_job_id}")
        if not parent.exists():
            return []
        if parent.is_symlink() or not parent.is_dir():
            raise MediaArtifactCorrupt("staging job path is not a private directory")
        try:
            return [f".staging/{render_job_id}/{item.name}" for item in sorted(parent.iterdir())
                    if item.is_dir() and not item.is_symlink()
                    and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", item.name)]
        except OSError as exc:
            raise MediaStorageNotConfigured("could not inspect staged render attempts") from exc

    def object_path(self, object_key: str) -> Path:
        return self._resolve(object_key)

    def verify_object(self, object_key: str, *, expected_sha256: str,
                      expected_size_bytes: int, expected_content_type: str = CONTENT_TYPE) -> VerifiedMedia:
        if expected_content_type != CONTENT_TYPE:
            raise MediaArtifactCorrupt("unsupported stored media content type")
        path = self._resolve(object_key)
        if not path.exists():
            raise MediaArtifactMissing("durable media object is missing")
        if path.is_symlink() or not path.is_file():
            raise MediaArtifactCorrupt("media object is not a regular file")
        try:
            actual_size = path.stat().st_size
            if actual_size <= 0 or actual_size != expected_size_bytes or actual_size > self.max_artifact_bytes:
                raise MediaArtifactCorrupt("stored media size does not match the persisted manifest")
            actual_hash, counted_size = hash_file(path)
        except OSError as exc:
            raise MediaStorageNotConfigured("media volume could not be read") from exc
        if counted_size != expected_size_bytes or actual_hash != expected_sha256:
            raise MediaArtifactCorrupt("stored media SHA-256 does not match the persisted manifest")
        return VerifiedMedia(path, counted_size, actual_hash, expected_content_type)

    def reconcile_and_verify(self, *, object_key: str, staging_key: str,
                             expected_sha256: str, expected_size_bytes: int,
                             expected_content_type: str = CONTENT_TYPE) -> VerifiedMedia:
        """Read first; only promote a complete stage when the final key is absent."""
        try:
            return self.verify_object(object_key, expected_sha256=expected_sha256,
                                      expected_size_bytes=expected_size_bytes,
                                      expected_content_type=expected_content_type)
        except MediaArtifactMissing:
            pass
        self.promote_staging(object_key=object_key, staging_key=staging_key,
                             expected_sha256=expected_sha256,
                             expected_size_bytes=expected_size_bytes)
        return self.verify_object(object_key, expected_sha256=expected_sha256,
                                  expected_size_bytes=expected_size_bytes,
                                  expected_content_type=expected_content_type)

    def promote_staging(self, *, object_key: str, staging_key: str,
                        expected_sha256: str, expected_size_bytes: int) -> Path:
        """Atomically expose a complete immutable object; readback is a separate gate."""
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256 or ""):
            raise MediaStorageError("invalid expected media hash")
        target = self._resolve(object_key)
        try:
            existing = self.verify_object(object_key, expected_sha256=expected_sha256,
                                          expected_size_bytes=expected_size_bytes)
            return existing.path
        except MediaArtifactMissing:
            pass
        except MediaArtifactCorrupt:
            raise
        stage_dir = self._resolve(staging_key)
        staged = stage_dir / "growth.mp4"
        if not staged.exists():
            raise MediaArtifactMissing("neither verified object nor staged render exists")
        if staged.is_symlink() or not staged.is_file():
            raise MediaArtifactCorrupt("staged render is not a regular file")
        try:
            stage_size = staged.stat().st_size
            stage_hash, counted_size = hash_file(staged)
        except OSError as exc:
            raise MediaStorageNotConfigured("staged media could not be read") from exc
        if stage_size != expected_size_bytes or counted_size != expected_size_bytes or stage_hash != expected_sha256:
            raise MediaArtifactCorrupt("staged media does not match the persisted hash/size")
        if stage_size > self.max_artifact_bytes:
            raise MediaQuotaExceeded("MP4 exceeds the configured per-artifact limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._usage_bytes() > self.max_total_bytes:
            raise MediaQuotaExceeded("media volume artifact quota reached")
        try:
            os.link(staged, target)
            self._fsync_directory(target.parent)
        except FileExistsError:
            # A concurrent/recovered writer may have won; verify, never overwrite.
            self.verify_object(object_key, expected_sha256=expected_sha256,
                               expected_size_bytes=expected_size_bytes)
        except OSError as exc:
            raise MediaStorageNotConfigured("could not atomically publish staged media") from exc
        return target

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def cleanup_staging(self, staging_key: str) -> None:
        """Only call after a verified object or a final quality failure."""
        directory = self._resolve(staging_key)
        try:
            shutil.rmtree(directory)
            parent = directory.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise MediaStorageNotConfigured("verified artifact staged files could not be cleaned") from exc
