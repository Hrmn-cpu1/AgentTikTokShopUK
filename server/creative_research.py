"""Evidence-backed creative research for the Brazil auto-video loop.

Only public official references and the agent's own evidence-gated learnings are used.
No third-party media is downloaded and no reference caption/script is copied.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable


@dataclass(frozen=True)
class CreativeReference:
    reference_id: str
    source: str
    source_ref: str
    market: str
    kind: str
    observed_patterns: dict
    evidence_note: str
    reviewed_at: str


# Current public, official TikTok Creative Center BR references reviewed 2026-09-29.
# We persist only abstract observations/analytics, never the source media or source copy.
PUBLIC_BR_REFERENCES = (
    CreativeReference(
        reference_id="ttcc-br-topad-7635108921376522248",
        source="TIKTOK_CREATIVE_CENTER_PUBLIC",
        source_ref="https://ads.tiktok.com/business/creativecenter/topads/7635108921376522248/pc/pt?countryCode=BR&period=30",
        market="BR",
        kind="TOP_AD",
        observed_patterns={
            "durationSeconds": 24,
            "hookWindowSeconds": [0, 3],
            "pacing": "FAST",
            "captionDensity": "SHORT",
            "cta": "DIRECT_ACTION",
            "narrative": "LOCAL_SPECIFICITY_VALUE_CTA",
            "style": ["vertical", "native-text", "direct"],
            "publicMetrics": {"likes": 752, "comments": 9, "shares": 18, "ctrBand": "TOP_52_PERCENT"},
        },
        evidence_note="Public Creative Center BR Top Ad metadata/analytics; pattern only, media not downloaded.",
        reviewed_at="2026-09-29T00:00:00+00:00",
    ),
    CreativeReference(
        reference_id="ttcc-br-topad-7639114878947639297",
        source="TIKTOK_CREATIVE_CENTER_PUBLIC",
        source_ref="https://ads.tiktok.com/business/creativecenter/topads/7639114878947639297/pc/pt?countryCode=BR&period=30",
        market="BR",
        kind="TOP_AD",
        observed_patterns={
            "durationSeconds": 27,
            "hookWindowSeconds": [0, 2],
            "highlightSeconds": [1, 9, 26],
            "pacing": "FAST",
            "captionDensity": "SHORT",
            "cta": "BENEFIT_CLOSE",
            "narrative": "PROBLEM_SOLUTION_BENEFITS_CLOSE",
            "style": ["vertical", "problem-first", "benefit-sequence"],
            "publicMetrics": {"likes": 281, "comments": 0, "shares": 12, "ctrBand": "TOP_62_PERCENT"},
        },
        evidence_note="Public Creative Center BR Top Ad metadata/analytics; highlight timings abstracted only.",
        reviewed_at="2026-09-29T00:00:00+00:00",
    ),
    CreativeReference(
        reference_id="ttcc-br-topad-7600046360951308304",
        source="TIKTOK_CREATIVE_CENTER_PUBLIC",
        source_ref="https://ads.tiktok.com/business/creativecenter/topads/7600046360951308304/pc/pt?countryCode=BR&period=30",
        market="BR",
        kind="TOP_AD",
        observed_patterns={
            "durationSeconds": 44,
            "hookWindowSeconds": [0, 2],
            "highlightSeconds": [1, 5, 8],
            "pacing": "FAST_OPEN",
            "captionDensity": "SHORT",
            "cta": "MEMORABLE_CLOSE",
            "narrative": "PERSONAL_OPEN_PRODUCT_VALUE_CLOSE",
            "style": ["vertical", "personality-led", "early-payoff"],
            "publicMetrics": {"likes": 222000, "comments": 724, "shares": 177, "ctrBand": "TOP_29_PERCENT"},
        },
        evidence_note="Public Creative Center BR Top Ad metadata/analytics; only timing/structure abstractions retained.",
        reviewed_at="2026-09-29T00:00:00+00:00",
    ),
    CreativeReference(
        reference_id="ttcc-br-guidance-creative-codes",
        source="TIKTOK_FOR_BUSINESS_PUBLIC",
        source_ref="https://ads.tiktok.com/business/pt-BR/blog/creative-best-practices-top-performing-ads",
        market="BR",
        kind="OFFICIAL_GUIDANCE",
        observed_patterns={
            "hookWindowSeconds": [0, 6],
            "preferredDurationSeconds": {"under": 30, "strongerResponseAtOrUnder": 15},
            "pacing": "FAST_SCENE_CHANGES",
            "captionDensity": "ON_SCREEN_TEXT_IMPORTANT",
            "cta": "CLEAR_CLOSE",
            "narrative": "HOOK_BODY_CLOSE",
            "style": ["vertical", "high-resolution", "safe-zone", "sound-led"],
        },
        evidence_note="Official TikTok for Business Brazil creative guidance; abstract production principles only.",
        reviewed_at="2026-09-29T00:00:00+00:00",
    ),
)


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def reference_bundle() -> list[dict]:
    return [asdict(item) for item in PUBLIC_BR_REFERENCES]


def derive_creative_dna(internal_learnings: Iterable[dict] = ()) -> dict:
    """Derive an abstract DNA. Own evidence-backed learning has priority over public priors."""
    learnings = [dict(item) for item in internal_learnings if item]
    own_hypotheses = [item for item in learnings if item.get("verdict") == "HYPOTHESIS_READY"]
    source_priority = "OWN_RESULTS_FIRST" if own_hypotheses else "PUBLIC_REFERENCE_PRIOR"

    hook_family_hint = None
    own_refs = []
    if own_hypotheses:
        latest = own_hypotheses[0]
        mutation = latest.get("nextMutation") if isinstance(latest.get("nextMutation"), dict) else {}
        if mutation.get("variable") == "hookFamily" and mutation.get("to"):
            hook_family_hint = str(mutation["to"])
        own_refs = [str(ref) for ref in mutation.get("evidenceRefs", []) if ref]

    patterns = {
        "hook": {
            "windowSeconds": [0, 2],
            "strategy": "QUESTION_OR_PROBLEM_WITH_IMMEDIATE_VALUE",
            "familyHint": hook_family_hint,
        },
        "duration": {"targetSeconds": 14.5, "maxPreferredSeconds": 30},
        "rhythm": {"sceneSeconds": [1.8, 2.7, 2.8, 3.0, 3.2], "opening": "FAST"},
        "scenes": {
            "count": 5,
            "sequence": ["HOOK", "CONTEXT", "VALUE", "PROOF_OR_METHOD", "CTA"],
        },
        "captions": {"burnedIn": True, "maxWordsPerScene": 12, "style": "SHORT_HIGH_CONTRAST"},
        "cta": {"type": "SAVE_FOLLOW_OR_VERIFY", "placement": "FINAL_SCENE"},
        "narrative": "HOOK_CONTEXT_VALUE_METHOD_CTA",
        "style": ["9:16", "faceless", "original-motion-vector", "high-contrast", "fast-cuts"],
        "audio": {"language": "pt-BR", "voice": "PIPER_FABER_MEDIUM", "musicBed": "ORIGINAL_SYNTHETIC"},
        "copyPolicy": "PATTERN_ONLY_NEVER_CONTENT",
    }
    refs = reference_bundle()
    evidence_material = {
        "sourcePriority": source_priority,
        "publicReferences": [{"id": r["reference_id"], "ref": r["source_ref"]} for r in refs],
        "ownEvidenceRefs": own_refs,
        "patterns": patterns,
    }
    digest = hashlib.sha256(_canonical(evidence_material).encode("utf-8")).hexdigest()
    return {
        "schemaVersion": 1,
        "sourcePriority": source_priority,
        "patterns": patterns,
        "publicReferences": refs,
        "ownLearningEvidenceRefs": own_refs,
        "evidenceDigest": digest,
        "studiedAt": datetime.now(timezone.utc).isoformat(),
        "rules": {
            "sourceMediaDownloaded": False,
            "sourceCopyReused": False,
            "privateTikTokApi": False,
            "googleTrendsAloneSufficient": False,
        },
    }
