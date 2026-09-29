import json

from server.creative_research import PUBLIC_BR_REFERENCES, derive_creative_dna


def test_public_reference_dna_is_pattern_only_and_not_google_only():
    dna = derive_creative_dna([])
    assert dna["sourcePriority"] == "PUBLIC_REFERENCE_PRIOR"
    assert len(dna["publicReferences"]) >= 4
    assert dna["rules"]["sourceMediaDownloaded"] is False
    assert dna["rules"]["sourceCopyReused"] is False
    assert dna["rules"]["privateTikTokApi"] is False
    assert dna["rules"]["googleTrendsAloneSufficient"] is False
    assert dna["patterns"]["hook"]["windowSeconds"] == [0, 2]
    assert dna["patterns"]["duration"]["maxPreferredSeconds"] == 30
    assert dna["patterns"]["audio"]["voice"] == "PIPER_FABER_MEDIUM"
    assert len(dna["evidenceDigest"]) == 64
    assert all(item.market == "BR" for item in PUBLIC_BR_REFERENCES)


def test_own_evidence_backed_learning_has_priority():
    dna = derive_creative_dna([{
        "verdict": "HYPOTHESIS_READY",
        "nextMutation": {
            "variable": "hookFamily",
            "to": "open_loop",
            "evidenceRefs": ["owner://video/a", "owner://video/b"],
        },
    }])
    assert dna["sourcePriority"] == "OWN_RESULTS_FIRST"
    assert dna["patterns"]["hook"]["familyHint"] == "open_loop"
    assert dna["ownLearningEvidenceRefs"] == ["owner://video/a", "owner://video/b"]
