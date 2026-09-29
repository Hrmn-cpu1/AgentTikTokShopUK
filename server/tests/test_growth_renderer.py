import json
import io
import subprocess
from PIL import Image, ImageChops
from server.growth_renderer import render_growth_plan

def test_growth_plan_renders_vertical_mp4_audio_captions_manifest_and_thumbnail(tmp_path):
    plan = json.dumps({"topic":"tema original", "hook":"Você sabia disso?","script":["Um teste original de conteúdo para crescimento legítimo."],"caption":"Siga para mais.",
        "scenePlan":[{"seconds":2,"text":"Você sabia disso?","narration":"Você sabia disso?"},{"seconds":2,"text":"Sinal público; TikTok UNKNOWN.","narration":"Sinal público; TikTok desconhecido."},{"seconds":2,"text":"Confira a fonte e o contexto.","narration":"Confira a fonte e o contexto."}],
        "sourceEvidence":{"source":"PUBLIC_FIXTURE"}, "assetPlan":{"visuals":"original"}})
    output, digest, cleanup = render_growth_plan(plan, output_dir=tmp_path)
    try:
        assert len(digest) == 64
        probe = subprocess.run(["ffprobe","-v","error","-of","json","-show_streams",str(output)],
                               capture_output=True,text=True,check=True)
        streams = json.loads(probe.stdout)["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        audio = next(stream for stream in streams if stream["codec_type"] == "audio")
        assert (video["width"], video["height"]) == (540, 960)
        assert video["codec_name"] == "h264"
        assert audio["codec_name"] == "aac"
        assert output.stat().st_size > 0
        assert (tmp_path / "captions.pt-BR.srt").is_file()
        assert "Você sabia disso?" in (tmp_path / "captions.pt-BR.srt").read_text()
        assert (tmp_path / "thumbnail.jpg").is_file()
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["aspectRatio"] == "9:16" and manifest["sha256"] == digest
        assert manifest["sourceEvidence"]["source"] == "PUBLIC_FIXTURE"
        assert manifest["rendererVersion"] == "2.2.0"
        assert manifest["sceneCount"] == 3 and manifest["sceneTransitions"] == 2
        assert manifest["animatedCropZoom"] and manifest["humanChosenPhotoUsed"] is False
        assert manifest["narrationGenerated"] == bool(__import__("shutil").which("espeak-ng"))
        captions = (tmp_path / "captions.pt-BR.srt").read_text()
        assert captions.count(" --> ") == 3
        assert "\n\n" in captions and "Sinal público; TikTok UNKNOWN." in captions
        frames = []
        for when in (0.5, 1.5):
            frame = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", str(when),
                "-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                capture_output=True, check=True).stdout
            frames.append(Image.open(io.BytesIO(frame)).convert("RGB"))
        assert ImageChops.difference(*frames).getbbox() is not None
    finally:
        cleanup()

def test_growth_plan_fails_closed_without_script():
    try:
        render_growth_plan(json.dumps({"hook":"x"}))
        assert False
    except ValueError:
        pass

def test_growth_plan_honors_emergency_cancel_checkpoint(tmp_path):
    plan = json.dumps({"topic":"cancel check", "hook":"Stop safely", "script":["one", "two", "three"],
        "scenePlan":[{"seconds":2,"text":"One"},{"seconds":2,"text":"Two"},{"seconds":2,"text":"Three"}]})
    try:
        render_growth_plan(plan, output_dir=tmp_path, should_cancel=lambda: True)
        assert False, "expected active render to be cancelled"
    except InterruptedError as error:
        assert "cancelled" in str(error)
