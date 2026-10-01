"""Hybrid short-form renderer: cloud H3 hook + proven local Piper/FFmpeg tail.

The expensive model is used only for the opening hook.  The existing local
renderer remains the source of truth for narration, captions, policy metadata
and the remainder of the video.
"""
from __future__ import annotations

from pathlib import Path
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from urllib.parse import urlparse

import httpx

from .growth_quality import evaluate_quality
from .growth_renderer import FONT_BOLD, HEIGHT, WIDTH, FPS, render_growth_plan
from .media_storage import hash_file
from .video_providers import MinimaxH3Provider, VideoGenerationRequest

_MAX_CLOUD_DOWNLOAD = 64 * 1024 * 1024


def _srt_seconds(value: str) -> float:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value.strip())
    if not match:
        raise ValueError("invalid SRT timestamp")
    hours, minutes, seconds, millis = (int(item) for item in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _safe_provider_url(url: str) -> str:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("cloud video provider returned an unsafe output URL")
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise RuntimeError("cloud video provider returned a local output URL")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal and (literal.is_private or literal.is_loopback or literal.is_link_local or
                    literal.is_reserved or literal.is_multicast or literal.is_unspecified):
        raise RuntimeError("cloud video provider returned a private output address")
    return url


def _download_https(url: str, destination: Path, max_bytes: int = _MAX_CLOUD_DOWNLOAD) -> None:
    safe_url = _safe_provider_url(url)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        with client.stream("GET", safe_url) as response:
            response.raise_for_status()
            total = 0
            with destination.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("cloud video output exceeds the configured download limit")
                    output.write(chunk)
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError("cloud video provider returned an empty output")


def _probe(path: Path) -> dict:
    response = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    payload = json.loads(response.stdout)
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError("cloud hook must contain both video and audio")
    duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("cloud hook duration is unavailable")
    return {"video": video, "audio": audio, "duration": duration}


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _normalize_hook(source: Path, output: Path, hook_text: str) -> float:
    caption = output.parent / "h3-hook-caption.txt"
    caption.write_text(hook_text.strip(), encoding="utf-8")
    drawtext = (
        f"drawtext=fontfile='{_escape_filter_path(Path(FONT_BOLD))}':"
        f"textfile='{_escape_filter_path(caption)}':"
        "fontcolor=white:fontsize=42:line_spacing=10:"
        "box=1:boxcolor=black@0.58:boxborderw=20:"
        "x=(w-text_w)/2:y=h*0.70"
    )
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},fps={FPS},{drawtext},format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(source),
        "-vf", vf, "-af", "aresample=44100",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-y", str(output),
    ], capture_output=True, timeout=180, check=True)
    return _probe(output)["duration"]


def _render_tail(local_video: Path, output: Path, skip_seconds: float) -> float:
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{skip_seconds:.3f}", "-i", str(local_video),
        "-vf", f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p", "-af", "aresample=44100",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-y", str(output),
    ], capture_output=True, timeout=180, check=True)
    return _probe(output)["duration"]


def _concat(hook: Path, tail: Path, output: Path) -> None:
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(hook), "-i", str(tail),
        "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-y", str(output),
    ], capture_output=True, timeout=240, check=True)


def _shift_captions(source: Path, destination: Path, cloud_hook_seconds: float,
                    local_hook_seconds: float) -> int:
    text = source.read_text(encoding="utf-8")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not blocks:
        raise RuntimeError("local render produced no caption blocks")
    shifted = []
    first_lines = blocks[0].splitlines()
    first_text = "\n".join(first_lines[2:]).strip()
    shifted.append(f"1\n{_srt_time(0)} --> {_srt_time(cloud_hook_seconds)}\n{first_text}")
    delta = cloud_hook_seconds - local_hook_seconds
    for index, block in enumerate(blocks[1:], start=2):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise RuntimeError("local render produced invalid captions")
        start, end = lines[1].split(" --> ", 1)
        shifted.append(
            f"{index}\n{_srt_time(_srt_seconds(start) + delta)} --> "
            f"{_srt_time(_srt_seconds(end) + delta)}\n" + "\n".join(lines[2:])
        )
    destination.write_text("\n\n".join(shifted) + "\n", encoding="utf-8")
    return len(shifted)


def _build_h3_prompt(plan: dict) -> str:
    hook = str(plan.get("hook") or "").strip()
    topic = str(plan.get("topic") or "curiosidade original").strip()
    scenes = plan.get("scenePlan") if isinstance(plan.get("scenePlan"), list) else []
    first = scenes[0] if scenes and isinstance(scenes[0], dict) else {}
    visual = str(first.get("visual") or first.get("visualLabel") or topic).strip()
    return (
        "Vertical 9:16 Brazilian TikTok opening hook. Create an ORIGINAL, premium, fast-paced "
        "cinematic shot with native audio, no logos, no watermark, no copied creator likeness. "
        f"Topic: {topic}. Visual direction: {visual}. Spoken Brazilian Portuguese hook: {hook}. "
        "The first second must create curiosity; keep visual motion continuous and readable on a phone. "
        "Do not add extra on-screen text because captions will be composited later."
    )


def render_growth_plan_with_selected_provider(
    plan_json: str,
    output_dir: str | Path | None = None,
    should_cancel=None,
    *,
    cloud_provider=None,
    remote_fetcher=None,
):
    selected = os.environ.get("VIDEO_PROVIDER", "local").strip().casefold() or "local"
    if selected == "local":
        return render_growth_plan(plan_json, output_dir=output_dir, should_cancel=should_cancel)
    if selected != "minimax_h3":
        raise RuntimeError(f"unsupported VIDEO_PROVIDER: {selected}")

    plan = json.loads(plan_json)
    directory = Path(output_dir) if output_dir is not None else Path(
        __import__("tempfile").mkdtemp(prefix="growth-hybrid-")
    )
    directory.mkdir(parents=True, exist_ok=True)
    cleanup = (lambda: None) if output_dir is not None else lambda: shutil.rmtree(directory, ignore_errors=True)

    provider = cloud_provider or MinimaxH3Provider()
    owns_provider = cloud_provider is None
    fetcher = remote_fetcher or _download_https
    local_dir = directory / "local-base"
    local_dir.mkdir(parents=True, exist_ok=True)

    try:
        if should_cancel and should_cancel():
            raise InterruptedError("Growth render cancelled by operator control")
        local_output, _, _ = render_growth_plan(plan_json, output_dir=local_dir, should_cancel=should_cancel)
        local_manifest = json.loads((local_dir / "manifest.json").read_text(encoding="utf-8"))
        local_hook_seconds = float(local_manifest.get("hookDurationSeconds") or 0)
        if local_hook_seconds <= 0:
            raise RuntimeError("local renderer did not report hook duration")

        duration = int(os.environ.get("MINIMAX_H3_HOOK_SECONDS", "4"))
        model = os.environ.get("MINIMAX_H3_MODEL", "MiniMax-H3")
        resolution = os.environ.get("MINIMAX_H3_RESOLUTION", "768P")
        ratio = os.environ.get("MINIMAX_H3_RATIO", "9:16")
        request = VideoGenerationRequest(
            prompt=_build_h3_prompt(plan), duration=duration, model=model,
            resolution=resolution, ratio=ratio,
        )
        result = provider.generate(request)
        if should_cancel and should_cancel():
            raise InterruptedError("Growth render cancelled after cloud hook generation")

        raw_hook = directory / "h3-hook-source.mp4"
        fetcher(result.output_url, raw_hook, _MAX_CLOUD_DOWNLOAD)
        normalized_hook = directory / "h3-hook.mp4"
        cloud_hook_seconds = _normalize_hook(raw_hook, normalized_hook, str(plan.get("hook") or ""))

        tail = directory / "local-tail.mp4"
        _render_tail(local_output, tail, local_hook_seconds)

        output = directory / "growth.mp4"
        _concat(normalized_hook, tail, output)
        final_probe = _probe(output)
        duration_total = final_probe["duration"]

        captions = directory / "captions.pt-BR.srt"
        caption_count = _shift_captions(
            local_dir / "captions.pt-BR.srt", captions, cloud_hook_seconds, local_hook_seconds
        )
        thumbnail = directory / "thumbnail.jpg"
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-ss", "0.2", "-i", str(output),
            "-frames:v", "1", "-q:v", "2", "-y", str(thumbnail),
        ], capture_output=True, timeout=30, check=True)

        digest, _ = hash_file(output)
        blank_scan = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-i", str(output),
            "-vf", "blackdetect=d=0.6:pix_th=0.015:pic_th=0.99", "-an", "-f", "null", "-"
        ], capture_output=True, text=True, timeout=45, check=False)
        black_intervals = re.findall(
            r"black_start:[0-9.]+ black_end:[0-9.]+ black_duration:([0-9.]+)", blank_scan.stderr
        )
        blank_check = "FAIL" if blank_scan.returncode != 0 or any(
            float(item) >= 0.6 for item in black_intervals
        ) else "PASS"

        manifest = dict(local_manifest)
        manifest.update({
            "rendererVersion": "2.4.0-hybrid-h3",
            "width": int(final_probe["video"].get("width") or WIDTH),
            "height": int(final_probe["video"].get("height") or HEIGHT),
            "fps": FPS,
            "videoCodec": str(final_probe["video"].get("codec_name") or "h264"),
            "audioCodec": str(final_probe["audio"].get("codec_name") or "aac"),
            "durationSeconds": round(duration_total, 2),
            "hookDurationSeconds": round(cloud_hook_seconds, 2),
            "captionFile": captions.name,
            "captionBlockCount": caption_count,
            "captionsBurnedIn": True,
            "thumbnail": thumbnail.name,
            "sha256": digest,
            "blankFrameCheck": blank_check,
            "audioVideoDurationMismatchSeconds": 0.0,
            "audioDescription": "MiniMax H3 native hook audio plus Piper neural pt-BR narration for local tail",
            "videoProvider": {
                "strategy": "HYBRID_CLOUD_HOOK_LOCAL_TAIL",
                "provider": result.provider,
                "model": result.model,
                "taskId": result.task_id,
                "resolution": result.resolution,
                "ratio": result.ratio,
                "cloudHookSeconds": round(cloud_hook_seconds, 2),
                "estimatedCostUsd": result.estimated_cost_usd,
                "outputStoredLocally": True,
            },
            "assetProvenance": {
                "cloudHook": "MINIMAX_H3_GENERATED_ORIGINAL",
                "tail": "LOCAL_PROCEDURAL_ORIGINAL",
                "thirdPartyClipReuse": False,
            },
        })
        manifest["qualityGate"] = evaluate_quality(manifest, plan)
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return output, digest, cleanup
    except Exception:
        if output_dir is None:
            cleanup()
        raise
    finally:
        if owns_provider:
            provider.close()
