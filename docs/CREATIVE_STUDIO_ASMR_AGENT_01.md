# AgencyOS Creative Studio — Agent #01 / ASMR Reels (cost-zero pilot)

**Date:** 2026-10-07. **Baseline:** main @ 2d3b5276d3048131150f983d9520a33f8cf61080.
**Scope:** additional free/offline editing capability; **not a production deployment, autonomous marketing agent, publication proof or claims of client footage.**

## Audit and reuse

- Existing growth engine: server/growth_renderer.py (FFmpeg H.264/AAC, captions, hash, thumbnail), growth_quality.py (QA), media_storage.py (SHA-256 and Railway durable volume), growth_worker.py (leased jobs, retries, fenced durable media).
- Existing hybrid mode: server/hybrid_video_renderer.py defaults to VIDEO_PROVIDER=local. MiniMax H3 is an optional external/cloud mode; **must not be selected by this mission**. The ASMR pilot does not invoke this integration at all.
- The legacy growth quality gate requires Piper narration and burned captions and is inappropriate for sound-first ASMR. Reuse the **FFmpeg and media hash infrastructure**, not narration assumptions.
- Existing Android ACTION_SEND supports manual handoff of the existing growth artifact; it does **not** prove publishing or handle ASMR outputs yet.
- Runtime durability and actual approved Paula footage/audio are not established by repository tests. Treat as separate verification gates.

## Prototype implemented in this branch

server/asmr_reels.py is a **review-only offline editing path**. It accepts 1–8 local vertical recordings plus one authentic mic/audio recording, trims scenes to a combined 6–60 seconds, makes 9:16 H.264/AAC at 540×960 (draft) or 1080×1920, preserves natural sound without narration/TTS/music generation, and writes reel.mp4, thumbnail.jpg, and a SHA-256-bound manifest.json.

Technical QA checks: codec, shape, duration, detectable audio, audio peak and prolonged black frames. Footage that needs horizontal-to-vertical crop is rejected instead of silently hiding hands. Every source must have an operator-supplied rights basis and evidence identifier; hashes are recorded. These attestations are **not independent license/consent verification**.

**Output state:** TECHNICAL_PASS + SELF_DECLARED_PENDING_HUMAN_VERIFICATION + PENDING_HUMAN_REVIEW + publication=BLOCKED. No automatic upload/post, no staged-media promotion and no client claims. A successful local MP4 is **not** STORED_VERIFIED.

## Local job example

Use files actually owned by/authorized for the business and accessible on the machine running FFmpeg.

~~~json
{
  "creative_id": "paula-asmr-001",
  "width": 540,
  "clips": [
    {
      "path": "/absolute/path/authorized-shot-1.mp4",
      "start": 0,
      "seconds": 4,
      "rights": {"basis": "CLIENT_AUTHORIZED", "evidence_id": "client-consent-record-001"}
    },
    {
      "path": "/absolute/path/authorized-shot-2.mp4",
      "start": 1,
      "seconds": 4,
      "rights": {"basis": "CLIENT_AUTHORIZED", "evidence_id": "client-consent-record-001"}
    }
  ],
  "audio": {
    "path": "/absolute/path/authentic-asmr-mic.wav",
    "start": 0,
    "rights": {"basis": "CLIENT_AUTHORIZED", "evidence_id": "client-consent-record-001"}
  }
}
~~~

~~~sh
VIDEO_PROVIDER=local python -m server.asmr_reels --job /absolute/path/job.json --out /absolute/path/new-empty-output
~~~

The audio file must contain at least as many usable seconds as the combined scenes. Export has no synthetic music, speech or clickbait overlay. An actual human must check hands, skin, contact, cuts, audio texture, privacy, venue context, truthful service claims, and source rights before publishing.

## Zero-new-spend policy

- Existing FFmpeg/ffprobe and Python standard library; reuse server/media_storage.hash_file.
- No paid APIs, new SaaS subscriptions, Runway video generation, MiniMax H3, CAPTCHA bypass, scraping, watermark removal, external downloaded creator reels, or automatic publication.
- **R$0 additional paid-service/API spend** for this offline code path; existing infrastructure/storage/CPU can still have real operating costs. Do not assume Railway is perpetually free.

## Verified stages vs next gates

1. **Code and deterministic tests:** run pytest -q server/tests/test_asmr_reels.py and PR CI; inspect generated synthetic color/sine fixtures as pipeline-only evidence, never client media.
2. **Real-media pilot:** ingest Paula-authorized original portrait source clips and actual ambient audio; verify that independent use/consent evidence exists. No assets were supplied to this branch.
3. **Editorial gate:** inspect the rendered MP4 on a phone, especially both hands and continuous movement; verify audio quality on headphones. Reject bad crops and unnatural transition points.
4. **Durable media integration:** only after #1–3, wire ASMR output into existing RailwayVolumeMediaStore with readback SHA, idempotency and owner-authorized delivery. Do not infer durability from local files.
5. **Manual handoff and verified observation:** only after owner's approval; publishing/engagement should be verified separately, not inferred from file creation or ACTION_SEND.

**Stop condition:** Do not change growth worker, public endpoints, production env, database schema, subscription settings or deployment as part of this pilot.
