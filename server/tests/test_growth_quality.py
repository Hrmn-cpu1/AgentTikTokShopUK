from server.growth_quality import evaluate_quality


def manifest(**overrides):
    value = {
        "aspectRatio": "9:16", "width": 540, "height": 960, "durationSeconds": 18,
        "audioCodec": "aac", "videoCodec": "h264", "sceneCount": 5,
        "sceneTransitions": 4, "animatedCropZoom": True, "captionBlockCount": 5,
        "captionsBurnedIn": True, "hookDurationSeconds": 2.0,
        "audioVideoDurationMismatchSeconds": 0.02, "blankFrameCheck": "PASS",
        "assetPlan": {"visuals": "original vector scenes"}, "narrationGenerated": True,
        "sha256": "a" * 64, "thumbnail": "thumbnail.jpg", "purpose": "EXPERIMENT",
    }
    value.update(overrides)
    return value


def plan():
    return {"scenePlan": [{"visual": f"visual-{i}", "text": "frase curta"} for i in range(5)]}


def test_quality_gate_passes_only_when_integrity_and_creative_checks_pass():
    result = evaluate_quality(manifest(), plan())
    assert result["status"] == "QUALITY_PASS"
    assert result["learningEligible"] is True


def test_quality_gate_rejects_slideshow_with_one_repeated_composition():
    repeated = {"scenePlan": [{"visual": "same", "text": "frase curta"} for _ in range(5)]}
    result = evaluate_quality(manifest(), repeated)
    assert result["status"] == "QUALITY_FAIL"
    assert "scene_diversity" in result["hardFailures"]


def test_quality_gate_requires_review_for_missing_narration_and_short_scene_count():
    result = evaluate_quality(manifest(sceneCount=3, sceneTransitions=2, captionBlockCount=3,
        narrationGenerated=False), {"scenePlan": [{"visual":str(i),"text":"ok"} for i in range(3)]})
    assert result["status"] == "QUALITY_REVIEW"
    assert {"narration", "short_form_variety"}.issubset(result["reviewItems"])


def test_quality_gate_does_not_allow_invalid_duration_or_missing_blank_scan_to_learning():
    result = evaluate_quality(manifest(durationSeconds=0, blankFrameCheck="UNKNOWN"), plan())
    assert result["status"] == "QUALITY_FAIL"
    assert result["learningEligible"] is False
