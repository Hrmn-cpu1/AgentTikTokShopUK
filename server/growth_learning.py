"""Evidence gates for learning; observations are not conclusions."""

from datetime import datetime, timedelta

MIN_VIEWS_FOR_COMPARISON = 100
MIN_OBSERVATION_AGE = timedelta(hours=24)
MIN_REPLICATES_PER_HOOK = 3


def eligible_for_comparison(*, quality_status: str, policy_status: str, purpose: str, source: str,
                            truth_classification: str, publication_identity: str | None,
                            evidence_ref: str, views: int | None, observed_at: datetime,
                            created_at: datetime) -> tuple[bool, str]:
    if quality_status != "QUALITY_PASS":
        return False, "QUALITY_GATE_NOT_PASSED"
    if policy_status != "POLICY_PASS":
        return False, "POLICY_OR_ORIGINALITY_GATE_NOT_PASSED"
    if purpose != "EXPERIMENT":
        return False, "NOT_AN_EXPERIMENT"
    if source != "OWNER_TIKTOK_UI" or truth_classification != "OWNER_REPORTED":
        return False, "OBSERVATION_SOURCE_NOT_OWNER_CONFIRMED"
    if not publication_identity or not evidence_ref:
        return False, "PUBLICATION_OR_EVIDENCE_REFERENCE_MISSING"
    if views is None or views < MIN_VIEWS_FOR_COMPARISON:
        return False, "INSUFFICIENT_SAMPLE_VIEWS"
    if observed_at - created_at < MIN_OBSERVATION_AGE:
        return False, "OBSERVATION_WINDOW_LESS_THAN_24_HOURS"
    return True, "ELIGIBLE_FOR_COMPARISON_ONLY"


def compare_hook_families(samples: list[dict]) -> dict:
    """Suggest one controlled hook mutation only after replicated, comparable evidence."""
    grouped: dict[str, list[dict]] = {}
    for sample in samples:
        if sample.get("eligible") and sample.get("topic") and sample.get("hookFamily") and \
           sample.get("engagementRate") is not None:
            grouped.setdefault(sample["hookFamily"], []).append(sample)
    qualified = {family: rows for family, rows in grouped.items()
                 if len({r["creativeId"] for r in rows}) >= MIN_REPLICATES_PER_HOOK}
    if len(qualified) < 2:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "nextMutation": {},
                "rationale": "Need three distinct quality-passed experiments for each of two hook families, with at least 100 observed views per experiment."}
    means = {family: sum(float(r["engagementRate"]) for r in rows) / len(rows)
             for family, rows in qualified.items()}
    ordered = sorted(means.items(), key=lambda item: (-item[1], item[0]))
    best, worst = ordered[0], ordered[-1]
    if best[1] <= worst[1]:
        return {"verdict": "NO_CLEAR_DIFFERENCE", "nextMutation": {},
                "rationale": "Replicated engagement evidence does not distinguish the compared hook families."}
    used = qualified[best[0]] + qualified[worst[0]]
    return {"verdict": "HYPOTHESIS_READY", "nextMutation": {
                "variable": "hookFamily", "from": worst[0], "to": best[0],
                "expectedEffect": "test whether the higher observed engagement rate repeats; not a proven winner",
                "evidenceRefs": sorted({str(row["evidenceRef"]) for row in used}),
                "experimentIds": sorted({str(row["experimentId"]) for row in used})},
            "rationale": "Replicated sample comparison suggests a testable hook hypothesis; it is not a final style baseline."}
