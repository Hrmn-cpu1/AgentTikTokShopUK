"""Reproducible original vertical MP4 renderer with captions and media sidecars."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 540, 960
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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
    return "\n".join(lines[:9])


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def render_growth_plan(plan_json: str, output_dir: str | Path | None = None):
    plan = json.loads(plan_json)
    hook = str(plan.get("hook") or "").strip()
    raw_script = plan.get("script")
    script = [str(part).strip() for part in raw_script] if isinstance(raw_script, list) else [str(raw_script or "").strip()]
    caption = str(plan.get("caption") or "").strip()
    if not hook or not any(script):
        raise ValueError("CreativePlan sem hook/script")
    keep = output_dir is not None
    directory = Path(output_dir) if keep else Path(tempfile.mkdtemp(prefix="growth-render-"))
    directory.mkdir(parents=True, exist_ok=True)
    cleanup = (lambda: None) if keep else lambda: shutil.rmtree(directory, ignore_errors=True)
    try:
        scenes = plan.get("scenePlan") or [
            {"seconds": 4, "text": hook},
            {"seconds": 4, "text": script[0]},
            {"seconds": 4, "text": caption or "Conteúdo original · Brasil"},
        ]
        bold = ImageFont.truetype(FONT_BOLD, 38)
        body = ImageFont.truetype(FONT, 27)
        playlist = []
        captions = []
        time_cursor = 0.0
        for index, scene in enumerate(scenes):
            duration = max(1.0, float(scene.get("seconds", 3.5)))
            phrase = str(scene.get("text", "")).strip()
            if not phrase:
                continue
            canvas = Image.new("RGB", (WIDTH, HEIGHT), "#08111f")
            draw = ImageDraw.Draw(canvas)
            draw.rounded_rectangle((25, 42, WIDTH - 25, 144), radius=20, fill="#162b48")
            draw.text((47, 78), f"BR · SINAL DE BUSCA · {index + 1:02}", font=body, fill="#91e8d0")
            draw.rounded_rectangle((28, 205, WIDTH - 28, 715), radius=28, fill="#13243c")
            active_font = bold if index == 0 else body
            wrapped = _wrap(draw, phrase, active_font, WIDTH - 92)
            box = draw.multiline_textbbox((0, 0), wrapped, font=active_font, spacing=14)
            text_height = box[3] - box[1]
            draw.multiline_text((48, max(250, 460 - text_height // 2)), wrapped,
                                font=active_font, fill="white", spacing=14)
            draw.text((45, 792), "Busca em alta ≠ métrica do TikTok", font=body, fill="#d4deed")
            draw.text((45, 850), "Conteúdo original · Brasil · pt-BR", font=body, fill="#91e8d0")
            frame = directory / f"scene-{index:02}.png"
            canvas.save(frame)
            playlist.append((frame, duration))
            captions.append(f"{len(captions) + 1}\n{_srt_time(time_cursor)} --> {_srt_time(time_cursor + duration)}\n{phrase}\n")
            time_cursor += duration
        if not playlist:
            raise ValueError("CreativePlan sem cenas")
        playlist_file = directory / "slides.txt"
        playlist_file.write_text("".join(f"file '{path.resolve()}'\nduration {duration}\n" for path, duration in playlist)
                                 + f"file '{playlist[-1][0].resolve()}'\n", encoding="utf-8")
        duration_total = sum(duration for _, duration in playlist)
        output = directory / "growth.mp4"
        command = ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(playlist_file),
            "-f", "lavfi", "-i", f"aevalsrc=0.025*sin(2*PI*220*t):s=44100:d={duration_total:.2f}",
            "-vf", "fps=24,format=yuv420p", "-t", f"{duration_total:.2f}", "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "96k", "-shortest", "-metadata", f"title={str(plan.get('topic','Original experiment'))[:80]}",
            "-metadata", "comment=Original content; public search trend signal; no TikTok metrics asserted",
            "-movflags", "+faststart", "-y", str(output)]
        result = subprocess.run(command, capture_output=True, timeout=60, check=False)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Falha no render MP4")
        srt_path = directory / "captions.pt-BR.srt"
        srt_path.write_text("\n".join(captions), encoding="utf-8")
        thumbnail = directory / "thumbnail.jpg"
        Image.open(playlist[0][0]).save(thumbnail, "JPEG", quality=88)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        manifest = {
            "format": "mp4", "videoCodec": "h264", "audioCodec": "aac", "audioDescription": "synthetic non-verbal tone bed",
            "width": WIDTH, "height": HEIGHT, "aspectRatio": "9:16", "durationSeconds": round(duration_total, 2),
            "fps": 24, "captionFile": srt_path.name, "captionsBurnedIn": True, "thumbnail": thumbnail.name,
            "sha256": digest, "title": str(plan.get("topic", "Original experiment")),
            "sourceEvidence": plan.get("sourceEvidence", {}), "assetPlan": plan.get("assetPlan", {}),
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return output, digest, cleanup
    except Exception:
        if not keep:
            cleanup()
        raise
