import hashlib

import pytest

from server.media_storage import (MediaArtifactCorrupt, MediaArtifactMissing,
    MediaStorageError, RailwayVolumeMediaStore, artifact_object_key, hash_file)


def test_stage_promote_and_readback_preserve_physical_identity(tmp_path):
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=4096,
                                    max_total_bytes=8192)
    stage_key = store.staging_key("render-job-1", "try-1")
    stage_dir = store.staging_directory(stage_key)
    payload = b"reproducible mp4 test bytes" * 17
    staged = stage_dir / "growth.mp4"
    staged.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    key = artifact_object_key("creative_1", digest)

    promoted = store.promote_staging(object_key=key, staging_key=stage_key,
                                     expected_sha256=digest, expected_size_bytes=len(payload))
    verified = store.verify_object(key, expected_sha256=digest, expected_size_bytes=len(payload))
    assert promoted == verified.path
    assert verified.sha256 == digest
    assert verified.size_bytes == len(payload)
    assert verified.path.read_bytes() == payload


def test_promotion_is_idempotent_and_never_overwrites_different_bytes(tmp_path):
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=4096,
                                    max_total_bytes=8192)
    first = b"first artifact"
    first_hash = hashlib.sha256(first).hexdigest()
    key = artifact_object_key("creative", first_hash)
    stage1 = store.staging_key("job", "try-1")
    (store.staging_directory(stage1) / "growth.mp4").write_bytes(first)
    store.promote_staging(object_key=key, staging_key=stage1,
                          expected_sha256=first_hash, expected_size_bytes=len(first))

    stage2 = store.staging_key("job", "try-2")
    (store.staging_directory(stage2) / "growth.mp4").write_bytes(b"different")
    same = store.promote_staging(object_key=key, staging_key=stage2,
                                 expected_sha256=first_hash, expected_size_bytes=len(first))
    assert same.read_bytes() == first
    with pytest.raises(MediaArtifactCorrupt):
        store.verify_object(key, expected_sha256=hashlib.sha256(b"different").hexdigest(),
                            expected_size_bytes=len(b"different"))


def test_missing_corrupt_and_unsafe_paths_fail_closed(tmp_path):
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=4096,
                                    max_total_bytes=8192)
    with pytest.raises(MediaArtifactMissing):
        store.verify_object("media/c/nope.mp4", expected_sha256="0" * 64, expected_size_bytes=10)
    with pytest.raises(MediaStorageError):
        store.object_path("../../outside.mp4")
    key = "media/corrupt/file.mp4"
    path = store.object_path(key)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"tampered")
    with pytest.raises(MediaArtifactCorrupt):
        store.verify_object(key, expected_sha256=hashlib.sha256(b"expected").hexdigest(),
                            expected_size_bytes=8)


def test_hash_file_streams_content_without_changing_identity(tmp_path):
    payload = b"x" * (2 * 1024 * 1024 + 19)
    path = tmp_path / "large.bin"
    path.write_bytes(payload)
    digest, size = hash_file(path)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
