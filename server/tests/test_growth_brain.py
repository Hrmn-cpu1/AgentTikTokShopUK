from datetime import datetime, timezone

from server.growth_brain import TrendCandidate, build_creative_plan, choose_niche, trend_score

def test_trend_score_and_plan_are_evidence_bound():
    candidate = TrendCandidate(topic="curiosidade sobre espaço", source="CI_FAKE",
        source_ref="ci://trend/space-1", evidence="fixture only",
        metrics={"views": 10000, "likes": 900, "comments": 100, "shares": 200, "velocity": 700})
    score = trend_score(candidate.metrics)
    assert 0 < score <= 100
    niche = choose_niche(candidate, {})
    plan = build_creative_plan(candidate, niche)
    assert plan["market"] == "BR"
    assert plan["language"] == "pt-BR"
    assert plan["objective"] == "LEGITIMATE_FOLLOWER_GROWTH_AND_INFORMATION_GAIN"
    assert plan["sourceEvidence"]["sourceRef"] == "ci://trend/space-1"
    assert plan["truth"] == "EVIDENCE_BACKED_INPUT"
    assert plan["voice"]["faceless"] is True

def test_niche_selection_explores_least_tested_family():
    candidate = TrendCandidate(topic="x", source="CI_FAKE", source_ref="ci://trend/x",
        evidence="fixture", metrics={})
    counts = {"storytelling": 5, "curiosidades": 5, "humor": 5, "pets": 5,
        "motivacao": 5, "tecnologia": 5, "misterio": 5, "cultura": 5,
        "educacional": 5, "visual": 0}
    assert choose_niche(candidate, counts) == "visual"
