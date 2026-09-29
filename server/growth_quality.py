"""Deterministic pre-delivery quality checks. A valid MP4 alone never passes creative QA."""

from __future__ import annotations

import re


def evaluate_quality(manifest: dict, plan: dict) -> dict:
    checks: dict[str, dict] = {}

    def add(name: str, passed: bool, detail: str, severity: str = "hard"):
        checks[name] = {"passed": bool(passed), "detail": detail, "severity": severity}

    add("vertical_format", manifest.get("aspectRatio") == "9:16" and manifest.get("width", 0) * 16 == manifest.get("height", 0) * 9,
        "MP4 precisa ser vertical 9:16")
    add("resolution", manifest.get("width", 0) >= 540 and manifest.get("height", 0) >= 960,
        "Resolução vertical mínima de 540×960")
    duration = float(manifest.get("durationSeconds") or 0)
    add("duration", 6 <= duration <= 60, "Duração entre 6 e 60 segundos")
    hook_duration = float(manifest.get("hookDurationSeconds") or 0)
    add("hook_duration", 0 < hook_duration <= 2.5, f"Hook inicial: {hook_duration:.2f}s")
    add("audio", manifest.get("audioCodec") in {"aac", "mp3", "opus"}, "Faixa de áudio presente")
    scene_count = int(manifest.get("sceneCount") or 0)
    add("scene_count", scene_count >= 3, "Mínimo de três cenas", "hard")
    if scene_count < 4:
        add("short_form_variety", False, "Quatro ou mais cenas são preferíveis", "review")
    else:
        add("short_form_variety", True, "Número de cenas adequado")
    scene_plan = plan.get("scenePlan") if isinstance(plan.get("scenePlan"), list) else []
    labels = {str(s.get("visual") or s.get("visualLabel") or "").strip().casefold()
              for s in scene_plan if isinstance(s, dict)} - {""}
    diversity = len(labels) / max(1, len(scene_plan))
    add("scene_diversity", diversity >= 0.6, f"{len(labels)} visuais distintos em {len(scene_plan)} cenas",
        "hard" if diversity < 0.4 else "review")
    caption_count = int(manifest.get("captionBlockCount") or 0)
    add("caption_timeline", caption_count >= scene_count and manifest.get("captionsBurnedIn") is True,
        "Legendas temporizadas e queimadas no vídeo")
    caption_texts = [str(s.get("text") or "") for s in scene_plan if isinstance(s, dict)]
    longest = max((len(re.findall(r"\S+", t)) for t in caption_texts), default=0)
    add("caption_density", longest <= 18, f"Maior bloco contém {longest} palavras",
        "hard" if longest > 24 else "review")
    add("motion", manifest.get("animatedCropZoom") is True and int(manifest.get("sceneTransitions") or 0) >= scene_count - 1,
        "Movimento e transições são parte do render")
    av_delta = manifest.get("audioVideoDurationMismatchSeconds")
    add("audio_video_sync", isinstance(av_delta, (int, float)) and abs(av_delta) <= 0.25,
        "Duração de áudio e vídeo alinhada")
    add("blank_frames", manifest.get("blankFrameCheck") == "PASS",
        "Verificação não encontrou tela preta persistente")
    add("asset_provenance", bool(manifest.get("assetPlan", {}).get("visuals")) and
        "original" in str(manifest.get("assetPlan", {}).get("visuals", "")).casefold(),
        "Plano deve identificar ativos originais/licenciados", "review")
    add("narration", manifest.get("narrationGenerated") is True,
        "Narração em português confirmada; a trilha sintética não conta como narração", "review")
    tts = manifest.get("tts") if isinstance(manifest.get("tts"), dict) else {}
    add("production_tts", tts.get("provider") == "PIPER_LOCAL_NEURAL" and
        tts.get("voice") == "pt_BR-faber-medium",
        "Voz de produção deve ser Piper neural pt-BR; eSpeak/fallback não é aceito")
    add("render_integrity", len(str(manifest.get("sha256", ""))) == 64 and
        bool(manifest.get("videoCodec")) and bool(manifest.get("thumbnail")),
        "Hash, codec e thumbnail presentes")

    failed_hard = [name for name, check in checks.items() if not check["passed"] and check["severity"] == "hard"]
    review = [name for name, check in checks.items() if not check["passed"] and check["severity"] == "review"]
    status = "QUALITY_FAIL" if failed_hard else "QUALITY_REVIEW" if review else "QUALITY_PASS"
    return {"status": status, "checks": checks, "hardFailures": failed_hard,
            "reviewItems": review, "sceneDiversity": round(diversity, 3),
            "learningEligible": status == "QUALITY_PASS" and manifest.get("purpose") == "EXPERIMENT"}
