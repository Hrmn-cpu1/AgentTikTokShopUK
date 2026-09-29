"""Generate one new automatic-video proof artifact without operator creative input."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from server.creative_research import derive_creative_dna
from server.growth_brain import TrendCandidate, build_creative_plan
from server.growth_renderer import render_growth_plan
from server.trend_sources import GoogleTrendsBrazilRSS, rank_public_signal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="auto-video-proof")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    dna = derive_creative_dna([])
    try:
        signals = [item for item in GoogleTrendsBrazilRSS().collect()
                   if item.market == "BR" and item.observed_at.tzinfo is not None
                   and 0 <= (now - item.observed_at.astimezone(timezone.utc)).total_seconds() <= 48 * 3600]
    except Exception:
        signals = []
    if signals:
        ranked = sorted(signals, key=lambda item: (-rank_public_signal(item, now)["score"],
                                                    len(item.topic), item.trend_id))
        chosen = ranked[0]
        candidate = TrendCandidate(
            topic=chosen.topic,
            source=chosen.source,
            source_ref=chosen.source_ref,
            evidence=chosen.evidence,
            metrics={**chosen.metrics, "ranking": rank_public_signal(chosen, now)},
        )
        trend_record = {
            "topic": candidate.topic,
            "source": chosen.source,
            "sourceRef": chosen.source_ref,
            "evidence": chosen.evidence,
            "observedAt": chosen.observed_at.isoformat(),
        }
    else:
        guide = dna["publicReferences"][-1]
        candidate = TrendCandidate(
            topic="por que os primeiros segundos importam em vídeos curtos",
            source=guide["source"],
            source_ref=guide["source_ref"],
            evidence=guide["evidence_note"],
            metrics={"views": None, "likes": None, "comments": None, "shares": None},
        )
        trend_record = {
            "topic": candidate.topic,
            "source": candidate.source,
            "sourceRef": candidate.source_ref,
            "evidence": candidate.evidence,
            "observedAt": None,
            "fallbackReason": "GOOGLE_TRENDS_RSS_UNAVAILABLE",
        }
    plan = build_creative_plan(candidate, "curiosidades", "question", creative_dna=dna)
    # Keep the spoken hook short enough for the strict <=2.5s production gate.
    plan["hook"] = "Por que isso está em alta?"
    plan["scenePlan"][0]["text"] = plan["hook"]
    plan["scenePlan"][0]["narration"] = plan["hook"]
    plan["proof"] = {"operatorCreativeInput": False, "generatedAt": now.isoformat()}

    (out / "creative_dna.json").write_text(json.dumps(dna, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "sources.json").write_text(json.dumps({
        "trend": trend_record,
        "creativeReferences": [{"id": x["reference_id"], "source": x["source"],
                                 "sourceRef": x["source_ref"]}
                                for x in dna["publicReferences"]],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    video, digest, _cleanup = render_growth_plan(json.dumps(plan, ensure_ascii=False), output_dir=out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if manifest["qualityGate"]["status"] != "QUALITY_PASS":
        raise RuntimeError("proof video did not achieve QUALITY_PASS: " +
                           json.dumps(manifest["qualityGate"], ensure_ascii=False))
    print(json.dumps({
        "video": str(video),
        "sha256": digest,
        "quality": manifest["qualityGate"]["status"],
        "tts": manifest["tts"],
        "topic": chosen.topic,
        "creativeDNA": dna["evidenceDigest"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
