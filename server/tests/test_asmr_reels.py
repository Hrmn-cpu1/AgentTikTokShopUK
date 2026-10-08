"""Local-only ASMR rendering contract: licensed inputs, actual audio, review-only export."""
import json
import shutil
import subprocess

import pytest

from server.asmr_reels import render_asmr_reel
from server.media_storage import hash_file


@pytest.fixture
def asmr_assets(tmp_path):
    a = tmp_path / "hands-a.mp4"
    b = tmp_path / "hands-b.mp4"
    audio = tmp_path / "room-mic.wav"
    for color, path in (("red", a), ("green", b)):
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=270x480:r=24:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path),
        ], capture_output=True, check=True, timeout=30)
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=f=220:r=44100:d=6.2",
        "-c:a", "pcm_s16le", "-y", str(audio),
    ], capture_output=True, check=True, timeout=30)
    rights = {"basis": "OWNED_ORIGINAL", "evidence_id": "operator-fixture-not-for-publication"}
    return {
        "creative_id": "ana-paula-asmr-001",
        "clips": [
            {"path": str(a), "start": 0, "seconds": 3, "rights": rights},
            {"path": str(b), "start": 0, "seconds": 3, "rights": rights},
        ],
        "audio": {"path": str(audio), "start": 0, "rights": rights},
    }


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_renders_real_audio_vertical_mp4_with_hash_and_nonpublication_gate(tmp_path, asmr_assets):
    target = tmp_path / "output"
    manifest = render_asmr_reel(asmr_assets, target)
    video = target / "reel.mp4"
    assert video.is_file() and video.stat().st_size > 1024
    assert (target / "thumbnail.jpg").is_file()
    assert json.loads((target / "manifest.json").read_text()) == manifest
    assert hash_file(video) == (manifest["sha256"], manifest["sizeBytes"])
    assert (manifest["width"], manifest["height"], manifest["aspectRatio"]) == (540, 960, "9:16")
    assert manifest["sceneCount"] == 2
    assert manifest["durationSeconds"] >= 6
    assert manifest["videoCodec"] == "h264" and manifest["audioCodec"] == "aac"
    assert manifest["cloudProviderUsed"] is False
    assert manifest["narrationGenerated"] is False
    assert manifest["qualityGate"]["status"] == "TECHNICAL_PASS"
    assert manifest["qualityGate"]["publication"] == "BLOCKED"
    assert manifest["qualityGate"]["rights"] == "SELF_DECLARED_PENDING_HUMAN_VERIFICATION"
    assert manifest["storageState"] == "LOCAL_DRAFT_NOT_DURABLY_PROMOTED"
    assert manifest["sourceEvidence"]["clips"][0]["independentlyVerified"] is False


def test_fails_closed_without_originality_rights(tmp_path, asmr_assets):
    asmr_assets["clips"][0]["rights"] = {"basis": "DOWNLOADED_FROM_INSTAGRAM", "evidence_id": "unknown"}
    with pytest.raises(ValueError, match="asset rights"):
        render_asmr_reel(asmr_assets, tmp_path / "output")
    assert not (tmp_path / "output" / "reel.mp4").exists()


def test_fails_closed_without_audio(tmp_path, asmr_assets):
    del asmr_assets["audio"]
    with pytest.raises(ValueError, match="authentic ambient audio"):
        render_asmr_reel(asmr_assets, tmp_path / "output")


def test_fails_closed_when_clip_has_no_valid_start(tmp_path, asmr_assets):
    asmr_assets["clips"][0]["start"] = -3
    with pytest.raises(ValueError, match="safe limits"):
        render_asmr_reel(asmr_assets, tmp_path / "output")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_fails_closed_for_short_audio_or_overwrite(tmp_path, asmr_assets):
    asmr_assets["audio"]["start"] = 1.0
    with pytest.raises(ValueError, match="too short"):
        render_asmr_reel(asmr_assets, tmp_path / "output")
    asmr_assets["audio"]["start"] = 0
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep.txt").write_text("do not erase")
    with pytest.raises(ValueError, match="must be empty"):
        render_asmr_reel(asmr_assets, output)
    assert (output / "keep.txt").read_text() == "do not erase"
