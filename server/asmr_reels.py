"""Cost-zero, audio-first ASMR Reels renderer built on the existing FFmpeg/media hash stack.

No cloud providers, downloads, TTS, publishing, or new Python dependencies.
Asset rights are declared by the operator; independent rights and editorial
approval remain mandatory before any client-facing use.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import shutil
import subprocess
from pathlib import Path

from .media_storage import hash_file

FPS = 24
MAX_CLIPS = 8
RIGHTS_BASES = {"OWNED_ORIGINAL", "CLIENT_AUTHORIZED", "LICENSED_COMMERCIAL"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
AUDIO_SUFFIXES = {".wav", ".m4a", ".aac", ".flac", ".mp3", ".ogg", ".opus"}
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_SOURCE_PIXELS = 2160 * 3840
logger = logging.getLogger(__name__)


def _run(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    """Run bounded commands without a shell; subprocess.run reaps processes on timeout."""
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"media command timed out after {timeout}s: {command[0]}") from exc
    except OSError as exc:
        raise RuntimeError(f"media executable unavailable or could not start: {command[0]}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"media command failed ({result.returncode}): {result.stderr[-800:]}")
    return result


def _probe(path: Path) -> dict:
    payload = json.loads(_run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ], timeout=30).stdout)
    if not payload.get("format", {}).get("duration"):
        raise ValueError(f"media duration unavailable: {path.name}")
    return payload


def _asset(raw: dict, media_type: str) -> tuple[Path, float, float, dict]:
    if not isinstance(raw, dict):
        raise ValueError("each media asset must be an object")
    path = Path(str(raw.get("path") or "")).expanduser()
    if not path.is_file() or path.is_symlink():
        raise ValueError("asset must be an existing regular local file (not a symlink)")
    extensions = VIDEO_SUFFIXES if media_type == "video" else AUDIO_SUFFIXES
    if path.suffix.lower() not in extensions:
        raise ValueError("unsupported local media format (playlists and remote protocols forbidden)")
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source media exceeds size policy")
    rights = raw.get("rights") or {}
    if (not isinstance(rights, dict) or rights.get("basis") not in RIGHTS_BASES
            or not isinstance(rights.get("evidence_id"), str)
            or not 5 <= len(rights["evidence_id"].strip()) <= 200):
        raise ValueError("asset rights basis and evidence_id are required")
    try:
        start = float(raw.get("start", 0))
        seconds = float(raw["seconds"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("asset start/seconds must be numeric") from exc
    if not (math.isfinite(start) and math.isfinite(seconds)
            and 0 <= start <= 3600 and 0 < seconds <= 60):
        raise ValueError("asset start/seconds outside safe limits")
    path = path.resolve()
    probe = _probe(path)
    stream = next((s for s in probe["streams"] if s.get("codec_type") == media_type), None)
    if stream is None:
        raise ValueError(f"{media_type} stream missing from {path.name}")
    if start + seconds > float(probe["format"]["duration"]) + 0.035:
        raise ValueError(f"{media_type} asset is too short: {path.name}")
    if media_type == "video":
        w, h = int(stream.get("width") or 0), int(stream.get("height") or 0)
        if (not w or not h or w * h > MAX_SOURCE_PIXELS
                or not 0.50 <= w / h <= 0.65):
            raise ValueError("footage needs vertical review/crop or exceeds resolution policy")
    sha, size = hash_file(path)
    evidence = {"sha256": sha, "sizeBytes": size, "fileName": path.name,
                "rightsBasis": rights["basis"], "evidenceId": rights["evidence_id"].strip(),
                "independentlyVerified": False}
    return path, start, seconds, evidence


def _scan_black(path: Path) -> bool:
    result = _run([
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
        "-vf", "blackdetect=d=0.5:pix_th=0.025:pic_th=0.98",
        "-an", "-f", "null", "-"
    ], timeout=90)
    return bool(re.search(r"black_start:", result.stderr))


def _audio_peak(path: Path) -> float | None:
    result = _run([
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
        "-vn", "-af", "volumedetect", "-f", "null", "-"
    ], timeout=90)
    values = re.findall(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", result.stderr)
    if not values:
        return None
    return float(values[-1])


def render_asmr_reel(spec: dict, output_dir: str | Path) -> dict:
    """Render a review-only draft. Never promotes or publishes the artifact."""
    if not isinstance(spec, dict):
        raise ValueError("job must be a JSON object")
    creative_id = spec.get("creative_id")
    if not isinstance(creative_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{5,80}", creative_id):
        raise ValueError("creative_id must be a safe stable identifier")
    clips = spec.get("clips")
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ValueError("provide 1-8 source video clips")
    clips_checked = [_asset(c, "video") for c in clips]
    total = sum(c[2] for c in clips_checked)
    if not 6 <= total <= 60:
        raise ValueError("reel must last 6-60 seconds")
    audio_spec = spec.get("audio")
    if not isinstance(audio_spec, dict):
        raise ValueError("authentic ambient audio with explicit rights is mandatory")
    audio = _asset(dict(audio_spec, seconds=total), "audio")
    requested_width = spec.get("width", 540)
    if type(requested_width) is not int or requested_width not in (540, 1080):
        raise ValueError("supported widths: 540 (draft), 1080 (export)")
    width, height = requested_width, round(requested_width * 16 / 9)
    target = Path(output_dir)
    # Exclusive mkdir is a job claim: no other render may write to this path.
    # Reject even empty existing directories; never overwrite unrelated artifacts.
    if target.exists():
        raise ValueError("output directory must not exist: no overwrites")
    temp_video = target / ".reel-incomplete.mp4"
    final_video = target / "reel.mp4"
    thumbnail = target / "thumbnail.jpg"
    manifest_file = target / "manifest.json"

    # Sequential clip transcodes bound decoder/filter memory even for 8 UHD sources.
    # Normalized H.264 segments are then stream-copied; no second video encode.
    target.mkdir(parents=True, exist_ok=False)  # Atomic exclusive job claim.
    logger.info("asmr_render_start creative=%s clips=%d width=%d", creative_id, len(clips), width)
    segments: list[Path] = []
    frame_total = 0
    edit_decisions: list[dict[str, object]] = []
    try:
        for index, (source, start, seconds, _) in enumerate(clips_checked):
            count = round(seconds * FPS)
            if count < 1:
                raise ValueError("scene duration is shorter than a single output frame")
            segment = target / f"segment_{index:02}.mp4"
            scene_filter = (
                f"trim=start={start:.6f}:duration={seconds:.6f},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={FPS},format=yuv420p"
            )
            _run([
                "ffmpeg", "-nostdin", "-loglevel", "error",
                "-i", str(source), "-map", "0:v:0", "-vf", scene_filter,
                "-an", "-frames:v", str(count), "-map_metadata", "-1", "-map_chapters", "-1",
                "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                "-crf", "23", "-pix_fmt", "yuv420p", "-video_track_timescale", "12288",
                "-movflags", "+faststart", "-n", str(segment),
            ], timeout=240)
            segment_probe = _probe(segment)
            segment_stream = next((st for st in segment_probe["streams"]
                                   if st.get("codec_type") == "video"), {})
            if (segment_stream.get("codec_name") != "h264"
                    or int(segment_stream.get("nb_frames") or 0) != count
                    or int(segment_stream.get("width") or 0) != width
                    or int(segment_stream.get("height") or 0) != height):
                raise ValueError(f"segment frame or format mismatch at index {index}")
            frame_total += count
            segments.append(segment)
            edit_decisions.append({
                "sourceSha256": clips_checked[index][3]["sha256"],
                "inSeconds": start, "requestedSeconds": seconds,
                "outputFrames": count, "outputSeconds": count / FPS,
            })

        target_duration = frame_total / FPS
        if not 6 <= target_duration <= 60.01:
            raise ValueError("frame-quantized reel duration outside 6-60s")
        # The frame boundary may exceed the requested fractional duration.
        if audio[1] + target_duration > float(_probe(audio[0])["format"]["duration"]) + 0.005:
            raise ValueError("audio too short after frame-quantized edit")
        list_file = target / "segments.ffconcat"
        list_file.write_text(
            "\n".join(f"file '{path.name}'" for path in segments) + "\n", encoding="utf-8"
        )
        combined_video = target / "combined_video.mp4"
        _run([
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-f", "concat", "-safe", "1", "-i", str(list_file),
            "-map", "0:v:0", "-c:v", "copy", "-an",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-movflags", "+faststart", "-n", str(combined_video),
        ], timeout=90)
        audio_filter = (
            f"[1:a]atrim=start={audio[1]:.6f}:duration={target_duration:.6f},"
            "asetpts=PTS-STARTPTS,aresample=44100:async=1:first_pts=0,"
            "highpass=f=45,alimiter=limit=0.96[a]"
        )
        _run([
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-i", str(combined_video), "-i", str(audio[0]),
            "-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[a]",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-t", f"{target_duration:.6f}", "-movflags", "+faststart",
            "-n", str(temp_video),
        ], timeout=150)
        # Detect source substitution/modification between preflight and render.
        all_sources = [*clips_checked, audio]
        for original, _, _, evidence in all_sources:
            digest_after, size_after = hash_file(original)
            if (digest_after != evidence["sha256"] or size_after != evidence["sizeBytes"]):
                raise RuntimeError(f"media source changed during render: {original.name}")
        probe = _probe(temp_video)
        streams = probe["streams"]
        video = next((s for s in streams if s["codec_type"] == "video"), {})
        sound = next((s for s in streams if s["codec_type"] == "audio"), {})
        duration = float(probe["format"]["duration"])
        peak = _audio_peak(temp_video)
        has_black = _scan_black(temp_video)
        checks = {
            "vertical_h264": video.get("codec_name") == "h264" and
                (video.get("width"), video.get("height")) == (width, height),
            "real_audio_aac": sound.get("codec_name") == "aac" and peak is not None and peak > -55,
            "duration": 6 <= duration <= 60.25 and abs(duration - total) <= 0.25,
            "no_prolonged_black": not has_black,
            "non_clipping_audio": peak is not None and peak <= -0.5,
        }
        technical_pass = all(checks.values())
        if not technical_pass:
            raise ValueError(f"ASMR technical QA failed: {[k for k,v in checks.items() if not v]}")
        temp_video.replace(final_video)
        digest, size = hash_file(final_video)
        _run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-ss", "0.3", "-i",
            str(final_video), "-frames:v", "1", "-q:v", "2", "-y", str(thumbnail)
        ], timeout=40)
        manifest = {
            "rendererVersion": "asmr-1.1.0-sequential", "creativeId": creative_id,
            "format": "mp4", "width": width, "height": height, "aspectRatio": "9:16",
            "fps": FPS, "durationSeconds": round(duration, 3), "sceneCount": len(clips),
            "videoCodec": "h264", "audioCodec": "aac", "audioSource": "REAL_OPERATOR_SUPPLIED",
            "narrationGenerated": False, "cloudProviderUsed": False,
            "costPolicy": "NO_PAID_PROVIDERS", "sha256": digest, "sizeBytes": size,
            "thumbnail": thumbnail.name, "audioPeakDbFS": peak,
            "pipeline": "SEQUENTIAL_H264_ENCODE_CONCAT_STREAM_COPY",
            "editDecisionList": edit_decisions,
            "audioInSeconds": audio[1],
            "creativeIntent": spec.get("intent", "UNSPECIFIED_REQUIRES_EDITORIAL_REVIEW"),
            "sourceEvidence": {"clips": [c[3] for c in clips_checked], "audio": audio[3]},
            "qualityGate": {"status": "TECHNICAL_PASS", "checks": checks,
                            "rights": "SELF_DECLARED_PENDING_HUMAN_VERIFICATION",
                            "editorial": "PENDING_HUMAN_REVIEW",
                            "publication": "BLOCKED"},
            "storageState": "LOCAL_DRAFT_NOT_DURABLY_PROMOTED",
        }
        manifest_temp = target / ".manifest-incomplete.json"
        manifest_temp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest_temp.replace(manifest_file)
        for intermediate in (*segments, list_file, combined_video):
            intermediate.unlink()
        logger.info("asmr_render_verified creative=%s bytes=%d sha256=%s", creative_id, size, digest)
        return manifest
    except BaseException:
        # A crash or QA failure must never leave a valid-looking public artifact.
        try:
            shutil.rmtree(target)
        except OSError:
            logger.exception("ASMR draft cleanup failed: %s", target)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline ASMR Reels factory: review-only output")
    parser.add_argument("--job", required=True, help="local JSON job describing video/audio rights")
    parser.add_argument("--out", required=True, help="new/empty output directory")
    args = parser.parse_args()
    spec = json.loads(Path(args.job).read_text(encoding="utf-8"))
    manifest = render_asmr_reel(spec, args.out)
    print(json.dumps({"output": str(Path(args.out) / "reel.mp4"),
                      "sha256": manifest["sha256"],
                      "qualityGate": manifest["qualityGate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
