from datetime import datetime, timezone

from server.growth_brain import TrendCandidate, build_creative_plan
from server.growth_policy import evaluate_policy, originality_signature


def manifest(status="QUALITY_PASS"):
    return {
        "sha256": "a" * 64,
        "qualityGate": {"status": status},
        "width": 540,
        "height": 960,
        "durationSeconds": 14.0,
    }


def plan():
    candidate = TrendCandidate(
        topic="curiosidade verificável",
        source="CI_PUBLIC_SIGNAL",
        source_ref="ci://signal/1",
        evidence="fixture",
        metrics={},
    )
    return build_creative_plan(candidate, "curiosidades", "question")


def test_original_plan_passes_brazil_policy_and_aigc_provenance_gate():
    value = plan()
    result = evaluate_policy(value, manifest(), set())
    assert result["policyStatus"] == "POLICY_PASS"
    assert result["originalityStatus"] == "ORIGINAL"
    assert result["aigcClassification"] == "AI_GENERATED"
    assert result["disclosureRequired"] is True
    assert len(result["creativeDnaDigest"]) == 64
    assert len(result["provenanceDigest"]) == 64


def test_exact_creative_signature_is_blocked_even_when_quality_passes():
    value = plan()
    signature = originality_signature(value)
    result = evaluate_policy(value, manifest(), {signature})
    assert result["policyStatus"] == "POLICY_FAIL"
    assert result["originalityStatus"] == "DUPLICATE"
    assert "EXACT_CREATIVE_SIGNATURE_ALREADY_USED" in result["reasons"]


def test_policy_refuses_third_party_copy_or_private_api_semantics():
    value = plan()
    value["provenance"]["thirdPartyMedia"] = True
    value["provenance"]["privateApi"] = True
    result = evaluate_policy(value, manifest(), set())
    assert result["policyStatus"] == "POLICY_FAIL"
    assert "THIRD_PARTY_MEDIA_NOT_PROHIBITED" in result["reasons"]
    assert "PRIVATE_API_NOT_PROHIBITED" in result["reasons"]


def test_quality_review_never_becomes_policy_pass():
    result = evaluate_policy(plan(), manifest("QUALITY_REVIEW"), set())
    assert result["policyStatus"] == "POLICY_REVIEW"
    assert "QUALITY_NOT_PASS" in result["reasons"]
