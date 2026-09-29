import hashlib
import json
from types import SimpleNamespace

from server.media_provenance import inspect_media_artifact
from server.media_storage import RailwayVolumeMediaStore, artifact_object_key


def _artifact(tmp_path, payload=b"durable-media-provenance"):
    digest = hashlib.sha256(payload).hexdigest()
    store = RailwayVolumeMediaStore(tmp_path / "media", max_artifact_bytes=1024 * 1024,
                                    max_total_bytes=4 * 1024 * 1024)
    store.preflight()
    object_key = artifact_object_key("creative-proof", digest)
    path = store.object_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    artifact = SimpleNamespace(
        artifact_id="artifact-proof", creative_id="creative-proof", render_job_id="job-proof",
        source_render_attempt="try-1-proof", object_key=object_key, sha256=digest,
        size_bytes=len(payload), content_type="video/mp4", quality_status="QUALITY_PASS",
        storage_state="STORED_VERIFIED", quality_manifest=json.dumps({"sha256": digest}),
    )
    return store, artifact, digest


def test_media_provenance_matches_db_manifest_and_physical_bytes(tmp_path):
    store, artifact, digest = _artifact(tmp_path)
    result = inspect_media_artifact(artifact, store)
    assert result["result"] == "PROVEN"
    assert result["db_sha256"] == result["manifest_sha256"] == result["physical_sha256"] == digest
    assert result["db_size_bytes"] == result["physical_size_bytes"]


def test_media_provenance_refuses_manifest_mismatch(tmp_path):
    store, artifact, _ = _artifact(tmp_path)
    artifact.quality_manifest = json.dumps({"sha256": "0" * 64})
    result = inspect_media_artifact(artifact, store)
    assert result["result"] == "NOT_PROVEN"
    assert result["physical_sha256"] == result["db_sha256"]
