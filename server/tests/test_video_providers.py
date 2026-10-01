import httpx
import pytest

from server.video_providers import (
    MinimaxH3Provider,
    VideoGenerationRequest,
    VideoProviderError,
    video_provider_readiness,
)


def test_minimax_h3_cloud_generation_uses_official_v2_contract(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer server-secret"
        if request.method == "POST":
            payload = __import__("json").loads(request.content)
            assert request.url.path == "/v2/video_generation"
            assert payload == {
                "model": "MiniMax-H3",
                "content": [{"type": "text", "text": "Produto em cena, câmera dinâmica"}],
                "resolution": "768P",
                "duration": 4,
                "ratio": "9:16",
            }
            return httpx.Response(200, json={"task_id": "task-123"})
        assert request.url.path == "/v2/query/video_generation/task-123"
        return httpx.Response(200, json={"task": {
            "id": "task-123", "model": "MiniMax-H3", "status": "succeeded",
            "content": {"url": "https://cdn.example/h3.mp4"},
            "resolution": "768P", "duration": 4, "ratio": "9:16",
        }})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MinimaxH3Provider(api_key="server-secret", client=client, sleep=lambda _: None)
    result = provider.generate(
        VideoGenerationRequest(prompt="Produto em cena, câmera dinâmica", duration=4),
        timeout_seconds=1,
        poll_interval_seconds=0,
    )
    assert result.output_url == "https://cdn.example/h3.mp4"
    assert result.estimated_cost_usd == 0.32
    assert len(calls) == 2


def test_minimax_h3_fails_closed_without_server_key():
    provider = MinimaxH3Provider(api_key="", client=httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(500)
    )))
    with pytest.raises(VideoProviderError, match="MINIMAX_API_KEY"):
        provider.create_task(VideoGenerationRequest(prompt="x", duration=4))


@pytest.mark.parametrize("duration", [0, 3, 16])
def test_minimax_h3_rejects_invalid_duration_before_network(duration):
    provider = MinimaxH3Provider(api_key="secret", client=httpx.Client(transport=httpx.MockTransport(
        lambda _: pytest.fail("network must not be called")
    )))
    with pytest.raises(ValueError):
        provider.create_task(VideoGenerationRequest(prompt="x", duration=duration))


def test_h3_max_has_its_own_resolution_and_duration_contract():
    with pytest.raises(ValueError):
        VideoGenerationRequest(prompt="x", model="MiniMax-H3-Max", duration=4).validate()
    with pytest.raises(ValueError):
        VideoGenerationRequest(prompt="x", model="MiniMax-H3-Max", duration=5, resolution="2K").validate()


def test_readiness_is_phone_first_and_never_leaks_key(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "minimax_h3")
    monkeypatch.setenv("MINIMAX_API_KEY", "do-not-leak-this")
    status = video_provider_readiness()
    assert status["ready"] is True
    assert status["policy"]["androidDoesInference"] is False
    assert status["policy"]["secretsOnAndroid"] is False
    assert status["policy"]["defaultCloudResolution"] == "768P"
    assert "do-not-leak-this" not in repr(status)
    h3 = next(item for item in status["providers"] if item["provider"] == "minimax_h3")
    assert h3["requiresLocalGpu"] is False
    assert h3["phoneFriendly"] is True
