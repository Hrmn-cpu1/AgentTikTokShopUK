"""Deterministic Brazil growth brain: evidence in, bounded creative hypothesis out.

This module creates no external effect and never claims that a trend is real unless a
caller supplies a source reference and observation evidence.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from .creative_style import HOOK_FAMILIES, MR_WHO_STYLE

NICHE_FAMILIES = (
    "storytelling", "curiosidades", "humor", "pets", "motivacao",
    "tecnologia", "misterio", "cultura", "educacional", "visual",
)

@dataclass(frozen=True)
class TrendCandidate:
    topic: str
    source: str
    source_ref: str
    evidence: str
    metrics: dict[str, Any]

def _metric(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    if value is None:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0

def trend_score(metrics: dict[str, Any]) -> float:
    """Comparable evidence score, not a claim of TikTok virality."""
    views = _metric(metrics, "views")
    likes = _metric(metrics, "likes")
    comments = _metric(metrics, "comments")
    shares = _metric(metrics, "shares")
    velocity = _metric(metrics, "velocity")
    engagement = (likes + 2 * comments + 3 * shares) / max(views, 1.0)
    return round(min(100.0, 45.0 * min(engagement / 0.12, 1.0) + 55.0 * min(velocity / 1000.0, 1.0)), 2)

def choose_niche(candidate: TrendCandidate, existing_counts: dict[str, int] | None = None) -> str:
    """Exploration first: deterministic, cheap and restart-safe."""
    counts = existing_counts or {}
    minimum = min((counts.get(n, 0) for n in NICHE_FAMILIES), default=0)
    underexplored = [n for n in NICHE_FAMILIES if counts.get(n, 0) == minimum]
    seed = hashlib.sha256((candidate.topic + "|" + candidate.source_ref).encode()).digest()[0]
    return underexplored[seed % len(underexplored)]

def choose_hook_family(candidate: TrendCandidate, existing_counts: dict[str, int] | None = None) -> str:
    counts = existing_counts or {}
    minimum = min((counts.get(name, 0) for name in HOOK_FAMILIES), default=0)
    choices = [name for name in HOOK_FAMILIES if counts.get(name, 0) == minimum]
    seed = hashlib.sha256((candidate.topic + "|" + candidate.source_ref + "|hook-v1").encode()).digest()[1]
    return choices[seed % len(choices)]


def _hook_text(topic: str, family: str) -> str:
    short = topic if len(topic) <= 32 else topic[:29].rsplit(" ", 1)[0] + "…"
    templates = {
        "curiosity": f"O detalhe por trás de {short}?",
        "unexpected_fact": f"Uma pergunta sobre {short}.",
        "challenge": f"Explique {short} em 10 segundos.",
        "comparison": f"{short}: busca alta ou fato?",
        "visual_surprise": f"Olhe {short} por outro ângulo.",
        "question": f"Por que {short} está em alta?",
        "contrarian_angle": f"Busca alta não prova {short}.",
        "before_after": f"Antes de compartilhar {short}, pare.",
        "mini_story": f"Uma busca trouxe esta pergunta: {short}.",
        "open_loop": f"A resposta sobre {short} depende de um detalhe.",
    }
    return templates[family]


def build_creative_plan(candidate: TrendCandidate, niche: str, hook_family: str | None = None) -> dict[str, Any]:
    topic = " ".join(candidate.topic.strip().split())[:180]
    if not topic or niche not in NICHE_FAMILIES:
        raise ValueError("valid topic and supported niche are required")
    hook_family = hook_family or choose_hook_family(candidate)
    if hook_family not in HOOK_FAMILIES:
        raise ValueError("unsupported Mr.Who? hook family")
    hook = _hook_text(topic, hook_family)
    short_topic = topic if len(topic) <= 34 else topic[:31].rsplit(" ", 1)[0] + "…"
    script = [
        f"“{short_topic}” surgiu nas buscas do Brasil.",
        "Busca alta não prova que algo é verdade.",
        "Confira a data, a fonte e o contexto.",
        "Salve o método. Verifique antes de compartilhar.",
    ]
    return {
        "schemaVersion": 1,
        "purpose": "EXPERIMENT",
        "creativeStyle": {"styleId": MR_WHO_STYLE["style_id"], "styleVersion": MR_WHO_STYLE["style_version"]},
        "hookFamily": hook_family,
        "hookVersion": "1",
        "market": "BR",
        "language": "pt-BR",
        "objective": "LEGITIMATE_FOLLOWER_GROWTH_AND_INFORMATION_GAIN",
        "niche": niche,
        "topic": topic,
        "hook": hook,
        "script": script,
        "scenePlan": [
            {"seconds": 2.0, "hook": True, "text": hook, "narration": hook, "visual": "orbiting original vector animation", "visualLabel": "GANCHO · PERGUNTA"},
            {"seconds": 3.1, "text": script[0], "narration": f"O assunto {short_topic} apareceu nas buscas em alta no Brasil.", "visual": "animated rising search signal", "visualLabel": "SINAL DE BUSCA · BR"},
            {"seconds": 2.8, "text": script[1], "narration": script[1], "visual": "original animated comparison graphic", "visualLabel": "LEITURA CRÍTICA"},
            {"seconds": 3.0, "text": script[2], "narration": "Antes de compartilhar, confira a data, a fonte original e o contexto.", "visual": "animated source-check checklist", "visualLabel": "TRÊS CHECAGENS"},
            {"seconds": 3.0, "text": script[3], "narration": script[3], "visual": "original animated call to action", "visualLabel": "CTA · COMPARTILHE COM CUIDADO"},
        ],
        "assetPlan": {"visuals": "original programmatic vector scenes; no owner-supplied or third-party media", "audio": "espeak-ng pt-BR narration when installed plus original low-volume audio bed", "captions": "short scene-synchronized Portuguese copy burned in plus SRT"},
        "originalIdea": {
            "sourcePattern": "PUBLIC_SIGNAL_TO_ORIGINAL_INTERPRETATION",
            "angle": f"Transformar o sinal público sobre {short_topic} em uma pergunta original + checklist de verificação.",
            "transformation": "Use only the abstract topic/pattern; script, scenes, visuals, narration and pacing are generated as a new work.",
            "copyPolicy": "PATTERN_ONLY_NEVER_CONTENT",
        },
        "storyArc": "QUESTION_SIGNAL_CONTEXT_CHECKLIST_CTA",
        "ctaType": "SAVE_AND_VERIFY",
        "creativeDNA": {
            "brandStyle": {"styleId": MR_WHO_STYLE["style_id"], "styleVersion": MR_WHO_STYLE["style_version"]},
            "hookFamily": hook_family,
            "storyArc": "QUESTION_SIGNAL_CONTEXT_CHECKLIST_CTA",
            "sceneCount": 5,
            "pacingSeconds": [2.0, 3.1, 2.8, 3.0, 3.0],
            "visualGrammar": ["9:16", "faceless", "motion-vector", "short-copy", "crossfades"],
            "ctaType": "SAVE_AND_VERIFY",
        },
        "provenance": {
            "thirdPartyMedia": False,
            "sourceMediaCopied": False,
            "copyMode": "PATTERN_ONLY_NEVER_CONTENT",
            "engagementManipulation": False,
            "privateApi": False,
            "publicSignalOnly": True,
        },
        "aigc": {
            "classification": "AI_GENERATED",
            "syntheticVisuals": True,
            "syntheticNarration": True,
            "disclosureRule": "DISCLOSE_WHEN_PLATFORM_FLOW_REQUIRES",
        },
        "hypothesis": "Um hook em forma de pergunta e um checklist verificável podem reter melhor do que uma afirmação genérica.",
        "nextExperimentMutation": {"variable": "hook", "next": "compare a direct checklist hook against this question hook after real observations"},
        "visualGrammar": ["9:16", "faceless", "five-scene motion sequence", "animated crop and camera drift", "short timed copy", "crossfades"],
        "voice": {"generated": "runtime-dependent", "language": "pt-BR", "faceless": True, "provider": "espeak-ng local OSS"},
        "caption": f"{topic} — teste original do AgentTikTok.",
        "hashtags": ["#brasil", "#paravoce", "#conteudooriginal"],
        "sourceEvidence": {
            "source": candidate.source,
            "sourceRef": candidate.source_ref,
            "evidence": candidate.evidence,
            "metrics": candidate.metrics,
            "trendScore": None if candidate.source == "GOOGLE_TRENDS_RSS" else trend_score(candidate.metrics),
        },
        "truth": "EVIDENCE_BACKED_INPUT",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

def canonical_plan(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
