from datetime import datetime, timedelta, timezone

from server.growth_learning import eligible_for_comparison, compare_hook_families


def test_fourteen_views_can_be_recorded_but_are_not_learning_eligible():
    eligible, reason = eligible_for_comparison(quality_status="QUALITY_PASS", purpose="EXPERIMENT",
        source="OWNER_TIKTOK_UI", truth_classification="OWNER_REPORTED", publication_identity="https://vt.tiktok.com/x1",
        evidence_ref="operator-screenshot:obs-1", views=14,
        observed_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc)-timedelta(days=2))
    assert not eligible and reason == "INSUFFICIENT_SAMPLE_VIEWS"


def test_failed_quality_and_unconfirmed_publication_never_enter_learning():
    observed = datetime.now(timezone.utc)
    base = dict(purpose="EXPERIMENT", source="OWNER_TIKTOK_UI", truth_classification="OWNER_REPORTED",
        publication_identity="https://vt.tiktok.com/x1", evidence_ref="screenshot:1", views=500,
        observed_at=observed, created_at=observed-timedelta(days=2))
    assert eligible_for_comparison(quality_status="QUALITY_FAIL", **base) == (False, "QUALITY_GATE_NOT_PASSED")
    assert eligible_for_comparison(quality_status="QUALITY_PASS", publication_identity=None,
        **{k:v for k,v in base.items() if k!="publication_identity"}) == (False,"PUBLICATION_OR_EVIDENCE_REFERENCE_MISSING")


def test_repeatable_mutation_needs_three_distinct_videos_in_each_hook_family():
    rows=[]
    for family, rate in (("question",.05), ("curiosity",.08)):
        for i in range(3):
            rows.append({"eligible":True,"topic":"same-topic","hookFamily":family,
                "engagementRate":rate,"creativeId":f"{family}-{i}",
                "experimentId":f"exp-{family}-{i}","evidenceRef":f"screen-{family}-{i}"})
    result=compare_hook_families(rows)
    assert result["verdict"]=="HYPOTHESIS_READY"
    assert result["nextMutation"]["variable"]=="hookFamily"
    assert result["nextMutation"]["from"]=="question"
    assert result["nextMutation"]["to"]=="curiosity"
    assert len(result["nextMutation"]["evidenceRefs"])==6


def test_small_or_nonreplicated_samples_return_insufficient_evidence():
    rows=[{"eligible":True,"topic":"same-topic","hookFamily":"question","engagementRate":.2,
        "creativeId":"one","experimentId":"exp-one","evidenceRef":"screen-one"}]
    assert compare_hook_families(rows)["verdict"]=="INSUFFICIENT_EVIDENCE"
