"""Create an original short MP4 from a creator-provided photo and approved copy."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

WIDTH, HEIGHT = 540, 960
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def _lines(draw: ImageDraw.ImageDraw, value: str, font: ImageFont.FreeTypeFont, width: int):
    words = value.split()
    lines: list[str] = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if draw.textlength(candidate, font=font) > width:
            if not current:
                raise ValueError('Uma palavra é longa demais para o vídeo')
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 5:
        raise ValueError('Encurte o texto para caber no vídeo')
    return '\n'.join(lines)


def render_creator_video(photo: bytes, headline: str, message: str, call_to_action: str):
    fields = [headline.strip(), message.strip(), call_to_action.strip()]
    if any(not field or len(field) > 95 or any(ord(c) < 32 for c in field) for field in fields):
        raise ValueError('Preencha três frases de até 95 caracteres, sem quebra de linha')
    try:
        picture = Image.open(BytesIO(photo))
        if picture.width * picture.height > 20_000_000 or picture.format not in {'PNG', 'JPEG', 'WEBP'}:
            raise ValueError('Use uma foto JPEG, PNG ou WebP de até 20 megapixels')
        picture = ImageOps.exif_transpose(picture).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('A imagem enviada não é válida') from exc

    directory = Path(tempfile.mkdtemp(prefix='creator-video-'))
    try:
        font = ImageFont.truetype(FONT_BOLD, 31)
        body = ImageFont.truetype(FONT, 25)
        for index, phrase in enumerate(fields):
            background = ImageOps.fit(picture, (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(35))
            dark = Image.new('RGB', (WIDTH, HEIGHT), '#070c20')
            canvas = Image.blend(background, dark, 0.63)
            foreground = ImageOps.contain(picture, (WIDTH - 64, 500))
            x = (WIDTH - foreground.width) // 2
            canvas.paste(foreground, (x, 270 + (480 - foreground.height) // 2))
            draw = ImageDraw.Draw(canvas)
            draw.rounded_rectangle((30, 40, WIDTH - 30, 260), radius=20, fill='#111c36')
            draw.multiline_text((50, 62), _lines(draw, phrase, font, WIDTH - 100), font=font,
                                fill='white', spacing=8)
            draw.rounded_rectangle((30, 772, WIDTH - 30, 893), radius=20, fill='#111c36')
            draw.text((50, 790), ('1 · DESCUBRA', '2 · ENTENDA', '3 · ACOMPANHE')[index],
                      font=body, fill='#81e4cf')
            draw.text((50, 832), 'Conteúdo original · Brasil', font=body, fill='white')
            canvas.save(directory / f'{index}.png')
        playlist = directory / 'slides.txt'
        playlist.write_text(''.join(f"file '{directory / f'{i}.png'}'\nduration 4\n" for i in range(3)) +
                            f"file '{directory / '2.png'}'\n", encoding='utf-8')
        output = directory / 'video.mp4'
        try:
            result = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                                     '-i', str(playlist), '-vf', 'fps=24,format=yuv420p', '-t', '12',
                                     '-c:v', 'libx264', '-preset', 'ultrafast', '-movflags', '+faststart',
                                     '-y', str(output)], capture_output=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError('Vídeo excedeu o tempo limite') from exc
        if result.returncode != 0 or not output.is_file():
            raise RuntimeError('Falha no codificador de vídeo')
        return output, lambda: shutil.rmtree(directory, ignore_errors=True)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
