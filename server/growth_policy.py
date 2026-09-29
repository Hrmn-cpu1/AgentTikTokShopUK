"""Brazil creator-growth policy/originality gate.

This module is deterministic and local. It does not call TikTok, infer platform truth,
or treat a quality-passed render as proof of originality, publication, or virality.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .growth_models import GrowthCreative, GrowthMediaArtifact, GrowthPolicyAssessment


POLICY_PACK_VERSION = "BR_CREATOR_GROWTH_V1"


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _sha(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def creative_dna(plan: dict) -> dict:
    scenes = plan.get("scenePlan") if isinstance(plan.get("scenePlan"), list) else []
    seconds = []
    for scene in scenes:
        try:
            seconds.append(round(float(scene.get("seconds")), 2))
        except (TypeError, ValueError, AttributeError):
            seconds.append(None)
    return {
        "brandStyle": plan.get("creativeStyle"),
        "hookFamily": plan.get("hookFamily"),
        "storyArc": plan.get("storyArc"),
        "sceneCount": len(scenes),
        "pacingSeconds": seconds,
        "visualGrammar": plan.get("visualGrammar"),
        "ctaType": plan.get("ctaType"),
        "niche": plan.get("niche"),
        "language": plan.get("language"),
        "market": plan.get("market"),
    }


def originality_signature(plan: dict) -> str:
    script = plan.get("script") if isinstance(plan.get("script"), list) else []
    idea = plan.get("originalIdea") if isinstance(plan.get("originalIdea"), dict) else {}
    material = {
        "idea": {
            "angle": idea.get("angle"),
            "transformation": idea.get("transformation"),
            "sourcePattern": idea.get("sourcePattern"),
        },
        "dna": creative_dna(plan),
        "script": [" ".join(str(item).split()).casefold() for item in script],
    }
    return _sha(material)


def provenance_manifest(plan: dict, manifest: dict) -> dict:
    source = plan.get("sourceEvidence") if isinstance(plan.get("sourceEvidence"), dict) else {}
    provenance = plan.get("provenance") if isinstance(plan.get("provenance"), dict) else {}
    aigc = plan.get("aigc") if isinstance(plan.get("aigc"), dict) else {}
    return {
        "policyPack": POLICY_PACK_VERSION,
        "market": plan.get("market"),
        "source": source.get("source"),
        "sourceRef": source.get("sourceRef"),
        "sourceMediaCopied": provenance.get("sourceMediaCopied"),
        "thirdPartyMedia": provenance.get("thirdPartyMedia"),
        "copyMode": provenance.get("copyMode"),
        "syntheticVisuals": aigc.get("syntheticVisuals"),
        "syntheticNarration": aigc.get("syntheticNarration"),
        "disclosureRule": aigc.get("disclosureRule"),
        "renderSha256": manifest.get("sha256"),
        "purpose": plan.get("purpose"),
    }


def evaluate_policy(plan: dict, manifest: dict, previous_signatures: set[str] | None = None) -> dict:
    """Return a conservative policy/originality result for one rendered artifact."""
    previous_signatures = previous_signatures or set()
    reasons: list[str] = []
    hard_failures: list[str] = []

    if plan.get("market") != "BR" or plan.get("language") != "pt-BR":
        hard_failures.append("BR_POLICY_PACK_MARKET_LANGUAGE_MISMATCH")
    if plan.get("purpose") != "EXPERIMENT":
        hard_failures.append("NON_EXPERIMENT_CONTENT")
    if plan.get("objective") != "LEGITIMATE_FOLLOWER_GROWTH_AND_INFORMATION_GAIN":
        hard_failures.append("UNSUPPORTED_GROWTH_OBJECTIVE")

    idea = plan.get("originalIdea") if isinstance(plan.get("originalIdea"), dict) else {}
    provenance = plan.get("provenance") if isinstance(plan.get("provenance"), dict) else {}
    aigc = plan.get("aigc") if isinstance(plan.get("aigc"), dict) else {}

    if not idea.get("angle") or not idea.get("transformation"):
        hard_failures.append("ORIGINAL_IDEA_MISSING")
    if idea.get("sourcePattern") != "PUBLIC_SIGNAL_TO_ORIGINAL_INTERPRETATION":
        hard_failures.append("ORIGINAL_IDEA_SOURCE_PATTERN_INVALID")
    if provenance.get("copyMode") != "PATTERN_ONLY_NEVER_CONTENT":
        hard_failures.append("COPY_POLICY_NOT_EXPLICIT")
    if provenance.get("sourceMediaCopied") is not False:
        hard_failures.append("SOURCE_MEDIA_COPY_NOT_PROHIBITED")
    if provenance.get("thirdPartyMedia") is not False:
        hard_failures.append("THIRD_PARTY_MEDIA_NOT_PROHIBITED")
    if provenance.get("engagementManipulation") is not False:
        hard_failures.append("ENGAGEMENT_MANIPULATION_NOT_PROHIBITED")
    if provenance.get("privateApi") is not False:
        hard_failures.append("PRIVATE_API_NOT_PROHIBITED")

    source = plan.get("sourceEvidence") if isinstance(plan.get("sourceEvidence"), dict) else {}
    if not source.get("source") or not source.get("sourceRef"):
        hard_failures.append("SOURCE_PROVENANCE_MISSING")

    dna = creative_dna(plan)
    dna_digest = _sha(dna)
    signature = originality_signature(plan)
    duplicate = signature in previous_signatures
    if duplicate:
        hard_failures.append("EXACT_CREATIVE_SIGNATURE_ALREADY_USED")

    if aigc.get("classification") not in {"AI_GENERATED", "AI_ASSISTED"}:
        hard_failures.append("AIGC_CLASSIFICATION_MISSING")
    disclosure_required = bool(
        aigc.get("syntheticVisuals") or aigc.get("syntheticNarration")
    )
    if disclosure_required and aigc.get("disclosureRule") != "DISCLOSE_WHEN_PLATFORM_FLOW_REQUIRES":
        hard_failures.append("AIGC_DISCLOSURE_RULE_MISSING")

    quality = manifest.get("qualityGate") if isinstance(manifest.get("qualityGate"), dict) else {}
    if quality.get("status") != "QUALITY_PASS":
        reasons.append("QUALITY_NOT_PASS")

    if hard_failures:
        status = "POLICY_FAIL"
        originality = "DUPLICATE" if duplicate else "REVIEW"
    elif quality.get("status") != "QUALITY_PASS":
        status = "POLICY_REVIEW"
        originality = "ORIGINAL"
    else:
        status = "POLICY_PASS"
        originality = "ORIGINAL"
        reasons.append("ORIGINAL_PLAN_AND_PROVENANCE_CHECKS_PASSED")

    provenance = provenance_manifest(plan, manifest)
    return {
        "policyPackVersion": POLICY_PACK_VERSION,
        "policyStatus": status,
        "originalityStatus": originality,
        "creativeDna": dna,
        "creativeDnaDigest": dna_digest,
        "originalitySignature": signature,
        "provenance": provenance,
        "provenanceDigest": _sha(provenance),
        "aigcClassification": str(aigc.get("classification") or "UNKNOWN"),
        "disclosureRequired": disclosure_required,
        "reasons": hard_failures + reasons,
    }


def persist_policy_assessment(session: Session, creative: GrowthCreative,
                              artifact: GrowthMediaArtifact, manifest: dict) -> GrowthPolicyAssessment:
    existing = session.scalar(select(GrowthPolicyAssessment).where(
        GrowthPolicyAssessment.artifact_id == artifact.artifact_id))
    if existing is not None:
        creative.policy_status = existing.policy_status
        return existing

    previous = set(session.scalars(select(GrowthPolicyAssessment.originality_signature).where(
        GrowthPolicyAssessment.creative_id != creative.creative_id,
        GrowthPolicyAssessment.policy_status == "POLICY_PASS")).all())
    plan = json.loads(creative.plan_json)
    result = evaluate_policy(plan, manifest, previous)
    now = datetime.now(timezone.utc)
    assessment = GrowthPolicyAssessment(
        assessment_id=str(uuid4()),
        creative_id=creative.creative_id,
        artifact_id=artifact.artifact_id,
        policy_pack_version=result["policyPackVersion"],
        policy_status=result["policyStatus"],
        originality_status=result["originalityStatus"],
        creative_dna_digest=result["creativeDnaDigest"],
        originality_signature=result["originalitySignature"],
        provenance_digest=result["provenanceDigest"],
        aigc_classification=result["aigcClassification"],
        disclosure_required=result["disclosureRequired"],
        reasons_json=json.dumps(result["reasons"], ensure_ascii=False, sort_keys=True),
        evaluated_at=now,
    )
    session.add(assessment)
    creative.policy_status = result["policyStatus"]
    session.flush()
    return assessment
