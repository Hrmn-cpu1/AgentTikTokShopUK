"""Deterministic Brazil growth brain: evidence in, bounded creative hypothesis out.

This module creates no external effect and never claims that a trend is real unless a
caller supplies a source reference and observation evidence.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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

def build_creative_plan(candidate: TrendCandidate, niche: str) -> dict[str, Any]:
    topic = " ".join(candidate.topic.strip().split())[:180]
    if not topic or niche not in NICHE_FAMILIES:
        raise ValueError("valid topic and supported niche are required")
    hook = f"O que está por trás de “{topic}”?"
    script = [
        f"“{topic}” aparece entre as buscas em alta no Brasil.",
        "Isso é um sinal de interesse em buscas — não é uma métrica do TikTok nem confirma uma notícia.",
        "Antes de compartilhar: confira a fonte original, a data e o contexto.",
    ]
    return {
        "schemaVersion": 1,
        "market": "BR",
        "language": "pt-BR",
        "objective": "LEGITIMATE_FOLLOWER_GROWTH_AND_INFORMATION_GAIN",
        "niche": niche,
        "topic": topic,
        "hook": hook,
        "script": script,
        "scenePlan": [
            {"seconds": 3.5, "text": hook, "visual": "original typography card"},
            {"seconds": 3.5, "text": script[0], "visual": "topic card with Brazil signal label"},
            {"seconds": 3.5, "text": script[1] + " " + script[2], "visual": "source-check checklist"},
            {"seconds": 3.5, "text": "Salve este checklist e confira antes de compartilhar.", "visual": "original CTA card"},
        ],
        "assetPlan": {"visuals": "original generated typography; no third-party video/audio", "audio": "synthetic low-volume tone bed", "captions": "burned-in Portuguese captions plus SRT"},
        "hypothesis": "Um hook em forma de pergunta e um checklist verificável podem reter melhor do que uma afirmação genérica.",
        "nextExperimentMutation": {"variable": "hook", "next": "compare a direct checklist hook against this question hook after real observations"},
        "visualGrammar": ["9:16", "faceless", "fast-cuts", "burned-captions"],
        "voice": {"generated": False, "language": "pt-BR", "faceless": True, "reason": "no local speech synthesis in this zero-cost render"},
        "caption": f"{topic} — teste original do AgentTikTok.",
        "hashtags": ["#brasil", "#paravoce", "#conteudooriginal"],
        "durationSeconds": 14,
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
