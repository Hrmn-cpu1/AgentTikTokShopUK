"""Cost-zero, audio-first ASMR Reels renderer built on the existing FFmpeg/media hash stack.

No cloud providers, downloads, TTS, publishing, or new Python dependencies.
Asset rights are declared by the operator; independent rights and editorial
approval remain mandatory before any client-facing use.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from .media_storage import hash_file

FPS = 24
MAX_CLIPS = 8
RIGHTS_BASES = {"OWNED_ORIGINAL", "CLIENT_AUTHORIZED", "LICENSED_COMMERCIAL"}


def _run(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"media command failed: {result.stderr[-500:]}")
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
    if not (0 <= start <= 3600 and 0 < seconds <= 60):
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
        if not w or not h or not 0.50 <= w / h <= 0.65:
            raise ValueError("footage needs vertical review/crop before ASMR render")
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
    if target.exists() and any(target.iterdir()):
        raise ValueError("output directory must be empty: no overwrites")
    target.mkdir(parents=True, exist_ok=True)
    temp_video = target / ".reel-incomplete.mp4"
    final_video = target / "reel.mp4"
    thumbnail = target / "thumbnail.jpg"
    manifest_file = target / "manifest.json"

    command = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    for path, _, _, _ in clips_checked:
        command.extend(["-i", str(path)])
    command.extend(["-i", str(audio[0])])
    filters = []
    for index, (_, start, seconds, _) in enumerate(clips_checked):
        filters.append(
            f"[{index}:v]trim=start={start:.3f}:duration={seconds:.3f},"
            f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={FPS},format=yuv420p[v{index}]"
        )
    filters.append("".join(f"[v{i}]" for i in range(len(clips_checked))) +
                   f"concat=n={len(clips_checked)}:v=1:a=0[v]")
    filters.append(
        f"[{len(clips_checked)}:a]atrim=start={audio[1]:.3f}:duration={total:.3f},"
        "asetpts=PTS-STARTPTS,aresample=44100:async=1:first_pts=0,"
        "highpass=f=45,alimiter=limit=0.96[a]"
    )
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-y", str(temp_video),
    ])
    try:
        _run(command, timeout=360)
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
            "rendererVersion": "asmr-1.0.0-local", "creativeId": creative_id,
            "format": "mp4", "width": width, "height": height, "aspectRatio": "9:16",
            "fps": FPS, "durationSeconds": round(duration, 3), "sceneCount": len(clips),
            "videoCodec": "h264", "audioCodec": "aac", "audioSource": "REAL_OPERATOR_SUPPLIED",
            "narrationGenerated": False, "cloudProviderUsed": False,
            "costPolicy": "NO_PAID_PROVIDERS", "sha256": digest, "sizeBytes": size,
            "thumbnail": thumbnail.name, "audioPeakDbFS": peak,
            "sourceEvidence": {"clips": [c[3] for c in clips_checked], "audio": audio[3]},
            "qualityGate": {"status": "TECHNICAL_PASS", "checks": checks,
                            "rights": "SELF_DECLARED_PENDING_HUMAN_VERIFICATION",
                            "editorial": "PENDING_HUMAN_REVIEW",
                            "publication": "BLOCKED"},
            "storageState": "LOCAL_DRAFT_NOT_DURABLY_PROMOTED",
        }
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
    finally:
        if temp_video.exists():
            temp_video.unlink()


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
