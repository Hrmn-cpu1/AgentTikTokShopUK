import json
import shutil
import subprocess

from server.hybrid_video_renderer import render_growth_plan_with_selected_provider
from server.video_providers import VideoGenerationResult


def _plan():
    return json.dumps({
        "topic": "curiosidade original",
        "hook": "Olha isso aqui!",
        "script": ["Um teste original para crescimento legítimo."],
        "caption": "Siga para mais.",
        "scenePlan": [
            {"seconds": 2, "text": "Olha isso aqui!", "narration": "Olha isso aqui!", "visual": "objeto em movimento"},
            {"seconds": 2, "text": "Agora vem o contexto.", "narration": "Agora vem o contexto.", "visual": "detalhe do objeto"},
            {"seconds": 2, "text": "Confira a fonte.", "narration": "Confira a fonte.", "visual": "cartão de fonte"},
        ],
        "sourceEvidence": {"source": "PUBLIC_FIXTURE"},
        "assetPlan": {"visuals": "original generated assets"},
        "purpose": "EXPERIMENT",
    })


class FakeProvider:
    def __init__(self, url):
        self.url = url
        self.requests = []

    def generate(self, request):
        request.validate()
        self.requests.append(request)
        return VideoGenerationResult(
            provider="minimax_h3", model=request.model, task_id="fake-task",
            status="succeeded", output_url=self.url, duration=request.duration,
            ratio=request.ratio, resolution=request.resolution, estimated_cost_usd=0.32,
        )


def _fake_cloud_clip(path):
    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=540x960:r=24:d=4",
        "-f", "lavfi", "-i", "sine=f=440:r=44100:d=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        "-y", str(path),
    ], check=True)


def test_hybrid_provider_uses_cloud_only_for_hook_and_preserves_quality_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "minimax_h3")
    monkeypatch.setenv("MINIMAX_H3_HOOK_SECONDS", "4")
    cloud = tmp_path / "fake-cloud.mp4"
    _fake_cloud_clip(cloud)
    provider = FakeProvider("https://cdn.example/hook.mp4")

    def fetcher(_url, destination, _max_bytes):
        shutil.copyfile(cloud, destination)

    output_dir = tmp_path / "render"
    output, digest, cleanup = render_growth_plan_with_selected_provider(
        _plan(), output_dir=output_dir, cloud_provider=provider, remote_fetcher=fetcher
    )
    cleanup()
    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert output.is_file() and len(digest) == 64
    assert provider.requests[0].ratio == "9:16"
    assert provider.requests[0].resolution == "768P"
    assert manifest["rendererVersion"] == "2.4.0-hybrid-h3"
    assert manifest["videoProvider"]["strategy"] == "HYBRID_CLOUD_HOOK_LOCAL_TAIL"
    assert manifest["videoProvider"]["taskId"] == "fake-task"
    assert manifest["videoProvider"]["estimatedCostUsd"] == 0.32
    assert manifest["assetProvenance"]["thirdPartyClipReuse"] is False
    assert manifest["tts"]["provider"] == "PIPER_LOCAL_NEURAL"
    assert manifest["qualityGate"]["checks"]["production_tts"]["passed"] is True
    assert manifest["durationSeconds"] > 4
    assert (output_dir / "captions.pt-BR.srt").is_file()
    assert (output_dir / "thumbnail.jpg").is_file()


def test_local_provider_keeps_existing_renderer(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_PROVIDER", "local")
    output, digest, cleanup = render_growth_plan_with_selected_provider(_plan(), output_dir=tmp_path)
    cleanup()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert output.is_file() and len(digest) == 64
    assert manifest["rendererVersion"] == "2.3.0"
    assert "videoProvider" not in manifest
