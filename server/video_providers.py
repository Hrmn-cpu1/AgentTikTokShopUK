"""Cloud video-provider layer inspired by AgentTube, designed for a phone-first operator.

MiniMax H3 inference is never run on the Android device or Railway container.  The
backend submits an asynchronous job to MiniMax, polls the task and returns the
remote output URL.  Secrets stay server-side.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import time
from typing import Callable

import httpx


class VideoProviderError(RuntimeError):
    """A provider request failed without exposing credentials."""


@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    duration: int = 5
    ratio: str = "9:16"
    resolution: str = "768P"
    model: str = "MiniMax-H3"

    def validate(self) -> None:
        if not self.prompt.strip():
            raise ValueError("video prompt is required")
        if self.model not in {"MiniMax-H3", "MiniMax-H3-Max"}:
            raise ValueError("unsupported MiniMax H3 model")
        minimum = 5 if self.model == "MiniMax-H3-Max" else 4
        if not minimum <= int(self.duration) <= 15:
            raise ValueError(f"{self.model} duration must be between {minimum} and 15 seconds")
        valid_resolution = {"480P", "768P"} if self.model == "MiniMax-H3-Max" else {"768P", "2K"}
        if self.resolution not in valid_resolution:
            raise ValueError(f"{self.resolution} is not supported by {self.model}")
        if self.ratio not in {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}:
            raise ValueError("unsupported video aspect ratio")


@dataclass(frozen=True)
class VideoGenerationResult:
    provider: str
    model: str
    task_id: str
    status: str
    output_url: str
    duration: int
    ratio: str
    resolution: str
    estimated_cost_usd: float | None

    def public_dict(self) -> dict:
        return asdict(self)


class MinimaxH3Provider:
    provider_id = "minimax_h3"
    _PRICE_PER_SECOND = {"768P": 0.08, "2K": 0.13}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = (api_key if api_key is not None else os.environ.get("MINIMAX_API_KEY", "")).strip()
        self.base_url = (base_url or os.environ.get("MINIMAX_API_BASE", "https://api.minimax.io")).rstrip("/")
        self.client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self.sleep = sleep

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_id,
            "configured": self.configured,
            "execution": "CLOUD_API",
            "requiresLocalGpu": False,
            "phoneFriendly": True,
            "models": ["MiniMax-H3", "MiniMax-H3-Max"],
            "ratios": ["9:16", "16:9", "1:1", "3:4", "4:3", "21:9"],
            "durationSeconds": {"MiniMax-H3": [4, 15], "MiniMax-H3-Max": [5, 15]},
            "resolutions": {"MiniMax-H3": ["768P", "2K"], "MiniMax-H3-Max": ["480P", "768P"]},
            "defaultResolution": os.environ.get("MINIMAX_H3_RESOLUTION", "768P"),
            "estimatedPriceUsdPerSecond": dict(self._PRICE_PER_SECOND),
            "secretLocation": "SERVER_ONLY",
        }

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise VideoProviderError("MiniMax H3 is not configured: set MINIMAX_API_KEY on the server")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _provider_error(response: httpx.Response) -> VideoProviderError:
        try:
            body = response.json()
            detail = body.get("error", {}).get("message") or body.get("message")
        except Exception:
            detail = None
        label = detail or f"HTTP {response.status_code}"
        return VideoProviderError(f"MiniMax H3 request failed: {label}")

    def create_task(self, request: VideoGenerationRequest) -> str:
        request.validate()
        payload = {
            "model": request.model,
            "content": [{"type": "text", "text": request.prompt.strip()}],
            "resolution": request.resolution,
            "duration": int(request.duration),
            "ratio": request.ratio,
        }
        response = self.client.post(
            f"{self.base_url}/v2/video_generation",
            headers=self._headers(),
            json=payload,
        )
        if response.status_code >= 400:
            raise self._provider_error(response)
        task_id = str(response.json().get("task_id") or "").strip()
        if not task_id:
            raise VideoProviderError("MiniMax H3 returned no task_id")
        return task_id

    def query_task(self, task_id: str) -> dict:
        task_id = str(task_id).strip()
        if not task_id:
            raise ValueError("task_id is required")
        response = self.client.get(
            f"{self.base_url}/v2/query/video_generation/{task_id}",
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise self._provider_error(response)
        task = response.json().get("task")
        if not isinstance(task, dict):
            raise VideoProviderError("MiniMax H3 returned an invalid task payload")
        return task

    def wait(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 600,
        poll_interval_seconds: float = 5,
    ) -> dict:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while True:
            task = self.query_task(task_id)
            status = str(task.get("status") or "").casefold()
            if status == "succeeded":
                url = str((task.get("content") or {}).get("url") or "").strip()
                if not url.startswith("https://"):
                    raise VideoProviderError("MiniMax H3 succeeded without a usable HTTPS output URL")
                return task
            if status in {"failed", "cancelled", "canceled"}:
                raise VideoProviderError(f"MiniMax H3 task ended with status {status}")
            if time.monotonic() >= deadline:
                raise TimeoutError("MiniMax H3 generation timed out")
            self.sleep(max(0.0, float(poll_interval_seconds)))

    @classmethod
    def estimate_cost_usd(cls, duration: int, resolution: str) -> float | None:
        rate = cls._PRICE_PER_SECOND.get(resolution)
        return None if rate is None else round(int(duration) * rate, 2)

    def generate(
        self,
        request: VideoGenerationRequest,
        *,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
    ) -> VideoGenerationResult:
        task_id = self.create_task(request)
        task = self.wait(
            task_id,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else float(
                os.environ.get("MINIMAX_H3_TIMEOUT_SECONDS", "600")
            ),
            poll_interval_seconds=poll_interval_seconds if poll_interval_seconds is not None else float(
                os.environ.get("MINIMAX_H3_POLL_INTERVAL_SECONDS", "5")
            ),
        )
        return VideoGenerationResult(
            provider=self.provider_id,
            model=str(task.get("model") or request.model),
            task_id=task_id,
            status="succeeded",
            output_url=str((task.get("content") or {}).get("url")),
            duration=int(task.get("duration") or request.duration),
            ratio=str(task.get("ratio") or request.ratio),
            resolution=str(task.get("resolution") or request.resolution),
            estimated_cost_usd=self.estimate_cost_usd(
                int(task.get("duration") or request.duration),
                str(task.get("resolution") or request.resolution),
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()


def video_provider_readiness() -> dict:
    """Return operator-safe capability metadata; never return an API key."""
    requested = os.environ.get("VIDEO_PROVIDER", "local").strip().casefold() or "local"
    minimax = MinimaxH3Provider()
    try:
        minimax_caps = minimax.capabilities()
    finally:
        minimax.close()
    local = {
        "provider": "local_procedural",
        "configured": True,
        "execution": "SERVER_CPU",
        "requiresLocalGpu": False,
        "phoneFriendly": True,
        "cost": "INFRASTRUCTURE_ONLY",
    }
    selected_ready = requested == "local" or (requested == "minimax_h3" and minimax_caps["configured"])
    return {
        "selected": requested,
        "ready": selected_ready,
        "policy": {
            "androidDoesInference": False,
            "secretsOnAndroid": False,
            "defaultCloudResolution": "768P",
            "upgrade2KOnlyForApprovedKeeper": True,
            "fallback": "local_procedural",
        },
        "providers": [local, minimax_caps],
    }
