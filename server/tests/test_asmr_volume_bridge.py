"""Opt-in ASMR-to-volume promotion: durable hash, replay, corruption and quota."""
import json
import shutil
import subprocess

import pytest

from server.asmr_reels import render_asmr_reel
from server.asmr_volume_bridge import promote_verified_asmr_draft
from server.media_storage import (
    MediaArtifactCorrupt, MediaQuotaExceeded, RailwayVolumeMediaStore,
)


@pytest.fixture
def draft(tmp_path):
    clips = []
    for index, color in enumerate(("red", "green")):
        clip = tmp_path / f"source-{index}.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=270x480:r=24:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-y", str(clip),
        ], check=True, capture_output=True, timeout=30)
        clips.append(clip)
    audio = tmp_path / "room.wav"
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=f=220:r=44100:d=6.2",
        "-c:a", "pcm_s16le", "-y", str(audio),
    ], check=True, capture_output=True, timeout=30)
    rights = {"basis": "OWNED_ORIGINAL", "evidence_id": "synthetic-noncommercial-test"}
    target = tmp_path / "draft"
    manifest = render_asmr_reel({
        "creative_id": "test-asmr-client-a",
        "clips": [
            {"path": str(c), "seconds": 3, "rights": rights} for c in clips
        ],
        "audio": {"path": str(audio), "rights": rights},
    }, target)
    return target, manifest


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_promote_verifies_durable_object_and_replay(tmp_path, draft):
    target, manifest = draft
    store = RailwayVolumeMediaStore(
        tmp_path / "volume", max_artifact_bytes=12_000_000,
        max_total_bytes=30_000_000,
    )
    params = dict(
        draft_dir=target, store=store,
        creative_id="test-asmr-client-a",
        render_job_id="render001", render_attempt_id="attempt001",
    )
    first = promote_verified_asmr_draft(**params)
    assert first.sha256 == manifest["sha256"]
    assert first.storage_state == "VOLUME_READBACK_VERIFIED_PENDING_REVIEW"
    assert first.publication == "BLOCKED"
    assert store.verify_object(
        first.object_key,
        expected_sha256=first.sha256,
        expected_size_bytes=first.size_bytes,
    ).path.is_file()
    assert promote_verified_asmr_draft(**params) == first
    assert json.loads((target / "manifest.json").read_text())["qualityGate"]["publication"] == "BLOCKED"
    assert not store.staged_attempts("render001")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_promote_rejects_corrupt_staging_without_replacing_it(tmp_path, draft):
    target, _ = draft
    store = RailwayVolumeMediaStore(
        tmp_path / "volume", max_artifact_bytes=12_000_000,
        max_total_bytes=30_000_000,
    )
    stage = store.staging_directory(store.staging_key("render002", "attempt002"))
    (stage / "growth.mp4").write_bytes(b"untrusted-stage")
    with pytest.raises(MediaArtifactCorrupt, match="staged render failed"):
        promote_verified_asmr_draft(
            draft_dir=target, store=store,
            creative_id="test-asmr-client-a",
            render_job_id="render002", render_attempt_id="attempt002",
        )
    assert (stage / "growth.mp4").read_bytes() == b"untrusted-stage"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_promote_rejects_wrong_creative_identity_and_small_quota(tmp_path, draft):
    target, _ = draft
    store = RailwayVolumeMediaStore(
        tmp_path / "volume", max_artifact_bytes=1024,
        max_total_bytes=2048,
    )
    params = dict(
        draft_dir=target, store=store,
        creative_id="test-asmr-client-b",
        render_job_id="render003", render_attempt_id="attempt003",
    )
    with pytest.raises(MediaArtifactCorrupt, match="creative identity"):
        promote_verified_asmr_draft(**params)
    params["creative_id"] = "test-asmr-client-a"
    with pytest.raises(MediaQuotaExceeded, match="artifact quota"):
        promote_verified_asmr_draft(**params)



@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_distinct_concurrent_attempts_converge_to_same_object(tmp_path, draft):
    from concurrent.futures import ThreadPoolExecutor
    target, _ = draft
    store = RailwayVolumeMediaStore(
        tmp_path / "volume", max_artifact_bytes=12_000_000,
        max_total_bytes=30_000_000,
    )

    def run(attempt: int):
        return promote_verified_asmr_draft(
            draft_dir=target, store=store, creative_id="test-asmr-client-a",
            render_job_id="render004", render_attempt_id=f"attempt{attempt:03}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(run, (1, 2)))
    assert receipts[0] == receipts[1]
    assert receipts[0].publication == "BLOCKED"
    assert store.verify_object(
        receipts[0].object_key,
        expected_sha256=receipts[0].sha256,
        expected_size_bytes=receipts[0].size_bytes,
    ).path.is_file()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_corrupted_copy_cannot_be_promoted(tmp_path, draft, monkeypatch):
    import server.asmr_volume_bridge as bridge
    target, _ = draft
    store = RailwayVolumeMediaStore(
        tmp_path / "volume", max_artifact_bytes=12_000_000,
        max_total_bytes=30_000_000,
    )
    original = bridge.shutil.copyfileobj

    def corrupt_copy(source, target_file, length=0):
        original(source, target_file, length)
        target_file.write(b"corrupted-during-stage")

    monkeypatch.setattr(bridge.shutil, "copyfileobj", corrupt_copy)
    with pytest.raises(MediaArtifactCorrupt, match="source changed"):
        promote_verified_asmr_draft(
            draft_dir=target, store=store, creative_id="test-asmr-client-a",
            render_job_id="render005", render_attempt_id="attempt005",
        )
    assert not store.staged_attempts("render005") or all(
        not store.object_path(key).joinpath("growth.mp4").exists()
        for key in store.staged_attempts("render005")
    )
