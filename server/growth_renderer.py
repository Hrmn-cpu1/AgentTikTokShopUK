"""Procedural short-form video renderer: animated scenes, timed copy, voice and media evidence."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont
from .creative_style import MR_WHO_STYLE
from .growth_quality import evaluate_quality
from .media_storage import hash_file

WIDTH, HEIGHT, FPS = 540, 960, 24
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PALETTES = [
    ("#071827", "#0b5f72", "#75f3d5"),
    ("#17102d", "#4a257f", "#ffbb66"),
    ("#091b29", "#075c58", "#62e3b0"),
    ("#211027", "#702c65", "#ff9cb5"),
    ("#111b2b", "#314b6d", "#9ce5fa"),
]
MOTIFS = ("orbit", "chart", "checklist", "lens", "arrow")


def _wrap(draw, text, font, max_width):
    words, lines, current = str(text).split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _background(index: int, seed: str) -> Image.Image:
    """Create a fresh vector scene plate; no owner photo, downloaded clip or third-party asset."""
    width, height = 650, 1155
    top, bottom, accent = PALETTES[index % len(PALETTES)]
    a = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(bottom[i:i + 2], 16) for i in (1, 3, 5))
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(a[c] * (1 - t) + b[c] * t) for c in range(3))
        for x in range(width):
            pixels[x, y] = color
    draw = ImageDraw.Draw(image, "RGBA")
    accent_rgb = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
    # Large translucent loops and a recognizable, different visual device per beat.
    for radius, alpha in ((280, 22), (220, 28), (145, 35)):
        draw.ellipse((width - 100 - radius, 130 - radius, width - 100 + radius, 130 + radius),
                     outline=(*accent_rgb, alpha), width=4)
    motif = MOTIFS[index % len(MOTIFS)]
    if motif == "orbit":
        for n in range(4):
            r = 65 + n * 42
            draw.arc((95, 320, 95 + r * 2, 320 + r * 2), 200 + n * 20, 520 - n * 18,
                     fill=(*accent_rgb, 100 - n * 14), width=5)
    elif motif == "chart":
        bars = (45, 80, 58, 112, 155)
        for n, bar in enumerate(bars):
            x = 115 + n * 80
            draw.rounded_rectangle((x, 410 - bar, x + 37, 410), radius=16,
                                   fill=(*accent_rgb, 35 + n * 18))
        draw.line([(115, 375), (230, 345), (310, 355), (435, 285), (510, 245)],
                  fill=(*accent_rgb, 230), width=7, joint="curve")
    elif motif == "checklist":
        for n, label in enumerate(("DATA", "FONTE", "CONTEXTO")):
            y = 215 + n * 63
            draw.rounded_rectangle((105, y, 535, y + 48), radius=18,
                                   fill=(255, 255, 255, 18), outline=(*accent_rgb, 110), width=2)
            draw.ellipse((125, y + 11, 151, y + 37), outline=(*accent_rgb, 240), width=3)
            draw.line((131, y + 23, 138, y + 30, 147, y + 17), fill=(*accent_rgb, 255), width=3)
            draw.text((170, y + 12), label, font=ImageFont.truetype(FONT_BOLD, 17), fill=(255, 255, 255, 230))
    elif motif == "lens":
        draw.ellipse((175, 190, 365, 380), outline=(*accent_rgb, 180), width=15)
        draw.line((335, 350, 445, 460), fill=(*accent_rgb, 230), width=20)
        for x, y, r in ((145, 300, 12), (465, 365, 18), (175, 750, 9), (480, 815, 13)):
            draw.ellipse((x-r, y-r, x+r, y+r), fill=(*accent_rgb, 185))
    else:
        draw.rounded_rectangle((105, 230, 535, 365), radius=44,
                               fill=(*accent_rgb, 24), outline=(*accent_rgb, 135), width=4)
        draw.line((165, 295, 435, 295), fill=(*accent_rgb, 235), width=11)
        draw.polygon(((425, 255), (495, 295), (425, 335)), fill=(*accent_rgb, 235))
    digest = hashlib.sha256(seed.encode()).digest()
    for n in range(14):
        x = 40 + digest[n] * 2
        y = 170 + digest[(n + 9) % len(digest)] * 3
        draw.ellipse((x, y, x + 4, y + 4), fill=(*accent_rgb, 75))
    return image


def _speech_tracks(scenes, directory):
    speaker = shutil.which("espeak-ng")
    fallback_durations = [2.0 if scene.get("hook") else 3.0 for scene in scenes]
    if not speaker:
        return None, fallback_durations
    chunks = []
    durations = []
    rate = 22050
    for index, scene in enumerate(scenes):
        path = directory / f"voice-{index:02}.wav"
        result = subprocess.run([speaker, "-v", "pt-br", "-s", "165", "-w", str(path), scene["narration"]],
                                capture_output=True, timeout=20, check=False)
        if result.returncode or not path.is_file():
            return None, fallback_durations
        with wave.open(str(path), "rb") as wav:
            params = wav.getparams()
            samples = wav.readframes(wav.getnframes())
        if params.nchannels != 1 or params.sampwidth != 2:
            return None, fallback_durations
        if params.framerate != rate:
            rate = params.framerate
        duration = len(samples) / (params.framerate * params.nchannels * params.sampwidth)
        durations.append(min(2.0, max(1.55, duration + 0.12)) if scene.get("hook") else max(2.65, duration + 0.5))
        pause = 0.05 if scene.get("hook") else 0.18
        chunks.append(samples + b"\x00\x00" * round(params.framerate * pause))
    voice_path = directory / "narration.pt-BR.wav"
    with wave.open(str(voice_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(chunks))
    return voice_path, durations


def _motion_frame(plate, index, local_frame, frames_in_scene, phrase, label, accent):
    progress = local_frame / max(1, frames_in_scene - 1)
    zoom = 1.0 + 0.075 * progress
    crop_w, crop_h = round(WIDTH / zoom), round(HEIGHT / zoom)
    x = round((plate.width - crop_w) / 2 + math.sin(progress * math.pi * 1.2 + index) * 17)
    y = round((plate.height - crop_h) / 2 + math.cos(progress * math.pi + index) * 20)
    x = max(0, min(plate.width - crop_w, x))
    y = max(0, min(plate.height - crop_h, y))
    frame = plate.crop((x, y, x + crop_w, y + crop_h)).resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(frame, "RGBA")
    accent_rgba = (*accent, 245)
    # A little moving orb supplies actual motion even when every asset is generated locally.
    orb_x = int(75 + 390 * progress)
    orb_y = int(210 + 18 * math.sin(progress * math.pi * 2 + index))
    draw.ellipse((orb_x - 10, orb_y - 10, orb_x + 10, orb_y + 10), fill=accent_rgba)
    slide = max(0.0, min(1.0, local_frame / max(1, round(FPS * 0.32))))
    slide = slide * slide * (3 - 2 * slide)
    panel_top = round(430 + (1 - slide) * 76)
    draw.rounded_rectangle((32, panel_top, WIDTH - 32, panel_top + 292), radius=32,
                           fill=(5, 13, 24, 239), outline=(*accent, 190), width=3)
    small = ImageFont.truetype(FONT_BOLD, 19)
    draw.text((55, panel_top + 25), label.upper(), font=small, fill=accent_rgba)
    main = ImageFont.truetype(FONT_BOLD, 43)
    wrapped = _wrap(draw, phrase, main, WIDTH - 108)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=main, spacing=15, align="left")
    text_height = bbox[3] - bbox[1]
    draw.multiline_text((55, panel_top + 78 + max(0, (152 - text_height) // 2)), wrapped,
                        font=main, spacing=15, fill=(255, 255, 255, 255))
    return frame


def render_growth_plan(plan_json: str, output_dir: str | Path | None = None,
                      should_cancel: Callable[[], bool] | None = None):
    plan = json.loads(plan_json)
    hook = str(plan.get("hook") or "").strip()
    raw_script = plan.get("script")
    script = [str(part).strip() for part in raw_script] if isinstance(raw_script, list) else [str(raw_script or "").strip()]
    caption = str(plan.get("caption") or "").strip()
    if not hook or not any(script):
        raise ValueError("CreativePlan sem hook/script")
    scenes = [item for item in (plan.get("scenePlan") or []) if str(item.get("text", "")).strip()]
    if len(scenes) < 3:
        raise ValueError("CreativePlan precisa de ao menos três cenas distintas")
    directory = Path(output_dir) if output_dir is not None else Path(tempfile.mkdtemp(prefix="growth-render-"))
    directory.mkdir(parents=True, exist_ok=True)
    cleanup = (lambda: None) if output_dir is not None else lambda: shutil.rmtree(directory, ignore_errors=True)
    try:
        for index, scene in enumerate(scenes):
            scene["narration"] = str(scene.get("narration") or scene["text"]).strip()
            scene["visualLabel"] = str(scene.get("visualLabel") or f"Cena {index + 1} · {plan.get('topic', 'Brasil')}")[:52]
        voice_path, durations = _speech_tracks(scenes, directory)
        scenes = [dict(scene, seconds=durations[index]) for index, scene in enumerate(scenes)]
        duration_total = sum(scene["seconds"] for scene in scenes)
        total_frames = round(duration_total * FPS)
        backgrounds = [_background(i, str(plan.get("topic", "")) + str(scene.get("visual", i)))
                      for i, scene in enumerate(scenes)]
        scene_frame_counts = [round(scene["seconds"] * FPS) for scene in scenes]
        output = directory / "growth.mp4"
        command = ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "pipe:0"]
        if voice_path:
            command += ["-i", str(voice_path), "-filter_complex",
                        f"[1:a]apad,atrim=0:{duration_total:.3f},volume=1.0[voice];"
                        f"sine=f=110:r=44100:d={duration_total:.3f},volume=0.028[bed];"
                        "[voice][bed]amix=inputs=2:duration=first:normalize=0[audio]", "-map", "0:v:0", "-map", "[audio]"]
        else:
            command += ["-f", "lavfi", "-i", f"sine=f=110:r=44100:d={duration_total:.3f}",
                        "-map", "0:v:0", "-map", "1:a:0", "-metadata", "comment=Narration unavailable in this runtime; synthetic audio bed"]
        command += ["-frames:v", str(total_frames), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", f"{duration_total:.3f}",
                    "-metadata", f"title={str(plan.get('topic', 'Original experiment'))[:80]}",
                    "-movflags", "+faststart", "-y", str(output)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time_cursor = 0.0
        caption_blocks = []
        previous = None
        for index, (scene, plate, count) in enumerate(zip(scenes, backgrounds, scene_frame_counts)):
            caption_blocks.append(f"{len(caption_blocks) + 1}\n{_srt_time(time_cursor)} --> {_srt_time(time_cursor + scene['seconds'])}\n{scene['text']}\n")
            _, _, accent_hex = PALETTES[index % len(PALETTES)]
            accent = tuple(int(accent_hex[pos:pos + 2], 16) for pos in (1, 3, 5))
            transition = min(round(0.24 * FPS), count // 3) if previous is not None else 0
            for local_frame in range(count):
                if should_cancel is not None and local_frame % FPS == 0 and should_cancel():
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                    process.terminate()
                    process.wait(timeout=5)
                    raise InterruptedError("Growth render cancelled by operator control")
                frame = _motion_frame(plate, index, local_frame, count, str(scene["text"]),
                                      scene["visualLabel"], accent)
                if previous is not None and local_frame < transition:
                    alpha = (local_frame + 1) / transition
                    prior = _motion_frame(previous, index - 1, max(0, scene_frame_counts[index - 1] - 1),
                                          scene_frame_counts[index - 1], "", "", accent)
                    frame = Image.blend(prior, frame, alpha)
                try:
                    process.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    break
            previous = plate
            time_cursor += scene["seconds"]
        if process.stdin:
            process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        return_code = process.wait(timeout=150)
        if return_code != 0 or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f"Falha no render MP4: {stderr.decode(errors='replace')[-900:]}")
        srt_path = directory / "captions.pt-BR.srt"
        srt_path.write_text("\n".join(caption_blocks), encoding="utf-8")
        thumbnail = directory / "thumbnail.jpg"
        backgrounds[0].resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(thumbnail, "JPEG", quality=90)
        digest, _ = hash_file(output)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
            capture_output=True, text=True, timeout=15, check=True)
        streams = json.loads(probe.stdout).get("streams", [])
        video_stream = next(item for item in streams if item.get("codec_type") == "video")
        audio_stream = next(item for item in streams if item.get("codec_type") == "audio")
        av_delta = abs(float(video_stream.get("duration", duration_total)) -
                       float(audio_stream.get("duration", duration_total)))
        blank_scan = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(output),
            "-vf", "blackdetect=d=0.6:pix_th=0.015:pic_th=0.99", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30, check=False)
        black_intervals = re.findall(r"black_start:[0-9.]+ black_end:[0-9.]+ black_duration:([0-9.]+)", blank_scan.stderr)
        blank_check = "FAIL" if blank_scan.returncode != 0 or any(float(item) >= 0.6 for item in black_intervals) else "PASS"
        manifest = {
            "rendererVersion": "2.2.0", "format": "mp4", "videoCodec": "h264", "audioCodec": "aac",
            "audioDescription": "Portuguese narration plus original low-volume tone bed" if voice_path else "synthetic tone bed; narration unavailable in this runtime",
            "narrationGenerated": bool(voice_path), "narrationLanguage": "pt-BR", "width": WIDTH,
            "height": HEIGHT, "aspectRatio": "9:16", "durationSeconds": round(duration_total, 2), "fps": FPS,
            "sceneCount": len(scenes), "sceneTransitions": max(0, len(scenes) - 1), "animatedCropZoom": True,
            "captions": "short synchronized scene phrases", "captionFile": srt_path.name,
            "captionSafeZones": True, "captionBlockCount": len(caption_blocks),
            "hookDurationSeconds": round(scenes[0]["seconds"], 2),
            "captionsBurnedIn": True, "thumbnail": thumbnail.name, "sha256": digest,
            "audioVideoDurationMismatchSeconds": round(av_delta, 3), "blankFrameCheck": blank_check,
            "title": str(plan.get("topic", "Original content")), "sourceEvidence": plan.get("sourceEvidence", {}),
            "assetPlan": plan.get("assetPlan", {}), "humanChosenPhotoUsed": False,
            "purpose": plan.get("purpose", "EXPERIMENT"),
            "creativeStyle": {"styleId": MR_WHO_STYLE["style_id"], "styleVersion": MR_WHO_STYLE["style_version"]},
        }
        manifest["qualityGate"] = evaluate_quality(manifest, plan)
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return output, digest, cleanup
    except Exception:
        if output_dir is None:
            cleanup()
        raise
