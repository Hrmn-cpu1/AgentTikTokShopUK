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
    assert manifest["rendererVersion"] == "asmr-1.2.0-r128-frame-verified"
    assert manifest["decodedFrameCount"] == 144
    assert manifest["audioVideoDurationMismatchSeconds"] <= 0.25
    assert manifest["audioAnalysis"]["truePeakDbFS"] <= -1.0
    assert manifest["qualityGate"]["checks"]["decoded_frame_count"] is True
    assert manifest["qualityGate"]["checks"]["audio_video_sync"] is True
    assert manifest["qualityGate"]["checks"]["true_peak_headroom"] is True
    assert manifest["pipeline"] == "SEQUENTIAL_H264_ENCODE_CONCAT_STREAM_COPY"
    assert [x["outputFrames"] for x in manifest["editDecisionList"]] == [72, 72]
    assert manifest["creativeIntent"] == "UNSPECIFIED_REQUIRES_EDITORIAL_REVIEW"
    assert not list(target.glob("segment_*.mp4"))
    assert not (target / "combined_video.mp4").exists()
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
    with pytest.raises(ValueError, match="must not exist"):
        render_asmr_reel(asmr_assets, output)
    assert (output / "keep.txt").read_text() == "do not erase"

def test_rejects_nonfinite_timestamps_and_playlist(tmp_path, asmr_assets):
    asmr_assets["clips"][0]["start"] = float("nan")
    with pytest.raises(ValueError, match="safe limits"):
        render_asmr_reel(asmr_assets, tmp_path / "invalid")
    asmr_assets["clips"][0]["start"] = 0
    asmr_assets["clips"][0]["path"] = str(tmp_path / "playlist.m3u8")
    (tmp_path / "playlist.m3u8").write_text("#EXTM3U\n")
    with pytest.raises(ValueError, match="unsupported local media"):
        render_asmr_reel(asmr_assets, tmp_path / "invalid")


def test_failed_encode_cleans_partial_directory(tmp_path, asmr_assets, monkeypatch):
    import server.asmr_reels as module
    actual_run = module._run

    def fail_encoding(cmd, timeout=240):
        if "-filter_complex" in cmd:
            raise RuntimeError("synthetic encoder interruption")
        return actual_run(cmd, timeout)

    monkeypatch.setattr(module, "_run", fail_encoding)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="interruption"):
        render_asmr_reel(asmr_assets, output)
    assert not output.exists(), "Failed drafts must not leave plausible artifacts"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_mutating_media_during_render_fails_closed(tmp_path, asmr_assets, monkeypatch):
    import server.asmr_reels as module
    actual_run = module._run
    changed = False

    def mutate_after_encode(cmd, timeout=240):
        nonlocal changed
        result = actual_run(cmd, timeout)
        if not changed and "-filter_complex" in cmd:
            changed = True
            with open(asmr_assets["clips"][0]["path"], "ab") as stream:
                stream.write(b"source-was-changed")
        return result

    monkeypatch.setattr(module, "_run", mutate_after_encode)
    output = tmp_path / "changed-source"
    with pytest.raises(RuntimeError, match="source changed"):
        render_asmr_reel(asmr_assets, output)
    assert not output.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_concurrent_same_destination_has_exactly_one_winner(tmp_path, asmr_assets):
    from concurrent.futures import ThreadPoolExecutor
    output = tmp_path / "exclusive"

    def run_attempt():
        try:
            return render_asmr_reel(asmr_assets, output)
        except (ValueError, FileExistsError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: run_attempt(), range(2)))
    assert sum(item is not None for item in outcomes) == 1
    assert json.loads((output / "manifest.json").read_text())["qualityGate"]["publication"] == "BLOCKED"
    assert (output / "reel.mp4").is_file()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required")
def test_frame_count_mismatch_blocks_export_and_cleans_directory(tmp_path, asmr_assets, monkeypatch):
    import server.asmr_reels as module
    monkeypatch.setattr(module, "_decode_frame_count", lambda _: 5)
    output = tmp_path / "bad-frames"
    with pytest.raises(ValueError, match="decoded_frame_count"):
        render_asmr_reel(asmr_assets, output)
    assert not output.exists()
