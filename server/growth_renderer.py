"""Render a CreativePlan into a real original vertical MP4 without pretending external providers exist."""
from io import BytesIO
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
            lines.append(current); current = word
        else:
            current = candidate
    if current: lines.append(current)
    return "\n".join(lines[:7])

def render_growth_plan(plan_json: str):
    plan = json.loads(plan_json)
    hook = str(plan.get("hook") or "").strip()
    script = str(plan.get("script") or "").strip()
    caption = str(plan.get("caption") or "").strip()
    if not hook or not script:
        raise ValueError("CreativePlan sem hook/script")
    directory = Path(tempfile.mkdtemp(prefix="growth-render-"))
    try:
        bold = ImageFont.truetype(FONT_BOLD, 38)
        body = ImageFont.truetype(FONT, 27)
        phrases = [hook, script, caption or "Siga para acompanhar o próximo teste."]
        for index, phrase in enumerate(phrases):
            canvas = Image.new("RGB", (WIDTH, HEIGHT), "#08111f")
            draw = ImageDraw.Draw(canvas)
            draw.rounded_rectangle((28, 42, WIDTH-28, 250), radius=24, fill="#13243c")
            draw.multiline_text((50, 68), _wrap(draw, phrase, bold if index == 0 else body, WIDTH-100),
                                font=bold if index == 0 else body, fill="white", spacing=10)
            draw.text((50, 820), "Conteúdo original · Brasil", font=body, fill="white")
            draw.text((50, 870), "Experimento de crescimento", font=body, fill="white")
            canvas.save(directory / f"{index}.png")
        playlist = directory / "slides.txt"
        playlist.write_text("".join(f"file '{directory / f'{i}.png'}'\nduration 4\n" for i in range(3))
                            + f"file '{directory / '2.png'}'\n", encoding="utf-8")
        output = directory / "growth.mp4"
        result = subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-f","concat","-safe","0",
            "-i",str(playlist),"-vf","fps=24,format=yuv420p","-t","12","-c:v","libx264",
            "-preset","ultrafast","-movflags","+faststart","-y",str(output)],
            capture_output=True, timeout=45, check=False)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Falha no render MP4")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        return output, digest, lambda: shutil.rmtree(directory, ignore_errors=True)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
