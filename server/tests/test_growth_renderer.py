import json
import subprocess
from server.growth_renderer import render_growth_plan

def test_growth_plan_renders_vertical_mp4_audio_captions_manifest_and_thumbnail(tmp_path):
    plan = json.dumps({"topic":"tema original", "hook":"Você sabia disso?","script":["Um teste original de conteúdo para crescimento legítimo."],"caption":"Siga para mais.",
        "scenePlan":[{"seconds":2,"text":"Você sabia disso?"},{"seconds":2,"text":"Sinal público; TikTok UNKNOWN."}],
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
        assert "00:00:02,000" in (tmp_path / "captions.pt-BR.srt").read_text()
        assert (tmp_path / "thumbnail.jpg").is_file()
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["aspectRatio"] == "9:16" and manifest["sha256"] == digest
        assert manifest["sourceEvidence"]["source"] == "PUBLIC_FIXTURE"
    finally:
        cleanup()

def test_growth_plan_fails_closed_without_script():
    try:
        render_growth_plan(json.dumps({"hook":"x"}))
        assert False
    except ValueError:
        pass
