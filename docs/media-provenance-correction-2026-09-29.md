# Durable media provenance correction — 2026-09-29

## Status

- `CURRENT_BASELINE_DOCUMENTATION_ERROR = PROVEN`
- `HISTORICAL_MEDIA_CONTINUITY = UNKNOWN` remains unchanged.
- No production row, manifest, media byte, object key, or filesystem object was modified by this correction.
- No render, rematerialization, replacement, or TikTok side effect was invoked.

## Superseded current-baseline statement

The current-baseline SHA-256/object-key value written in
`docs/media-provenance-reconciliation-2026-09-29.md` as:

`a3c063b9c4de316b9c7ebffb4fbee6e63f3c471a86dad93f8bdc3981898246ea`

is:

`SUPERSEDED_BY_VERIFIED_EVIDENCE`

for the current durable artifact baseline.

The verified current physical object name is:

`a3c063b9c4de316b9c7ebffbf4bee6e63f3c471a86dad93f8bdc3981898246ea.mp4`

under:

`/data/media/agenttiktok-media/media/creative-gtr-br-81eee0606898b025f741fb5d/`

Size: `3,075,632 bytes`.

Filesystem modification time reported by the live Railway volume:
`2026-09-29T07:16:30Z`.

Therefore the corrected current-baseline SHA-256 is:

`a3c063b9c4de316b9c7ebffbf4bee6e63f3c471a86dad93f8bdc3981898246ea`

and the corrected current-baseline object key is:

`media/creative-gtr-br-81eee0606898b025f741fb5d/a3c063b9c4de316b9c7ebffbf4bee6e63f3c471a86dad93f8bdc3981898246ea.mp4`.

## Evidence

1. The live Railway volume listed exactly one canonical MP4 in the current creative directory with the corrected filename, size `3,075,632`, and original render-time mtime `2026-09-29T07:16:30Z`.
2. `server/growth_worker.py::_persist_render_artifact` independently hashes the rendered bytes, requires `manifest.sha256 == digest`, persists `GrowthMediaArtifact.sha256 = digest`, and constructs `object_key = artifact_object_key(creative_id, digest)`. The SHA and object-key filename are therefore born from the same computed digest.
3. The durable-media worker never overwrites a canonical object. `RailwayVolumeMediaStore.promote_staging` uses `os.link`; an existing target is verified rather than replaced.
4. `GET /v1/growth/creatives/creative-gtr-br-81eee0606898b025f741fb5d/video` returned HTTP 200 on the live deployment at `2026-09-29T13:06:15Z`. Before returning `FileResponse`, the route calls `verify_object`, which recalculates SHA-256 and size directly from the physical volume file and compares both with the persisted artifact row. A missing or mismatched object would return 503 and mark it missing/corrupt instead.
5. No normal worker/API code path rewrites an existing artifact's `sha256` or `object_key`; later transitions update storage/error state while retaining the frozen identity.

Together these establish the corrected current baseline without changing production data.

## Historical continuity boundary

This correction does **not** prove that every older chat/checkpoint value was correct or incorrect at the time it was written. There is still no historical database row-version trail or independently retained old physical byte set for the pre-baseline period.

Therefore:

`HISTORICAL_MEDIA_CONTINUITY = UNKNOWN`

remains the conservative historical verdict.

The current durable-media invariant is separately established by live readback verification and the post-deploy HTTP 200 integrity gate.
