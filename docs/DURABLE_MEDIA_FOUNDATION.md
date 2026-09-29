# Durable Media Foundation

**Implementation status:** local code and CI-equivalent tests only, pending Railway volume configuration and restart proof.  
**Baseline:** `main` at `24a11723eb31826feac772527828e23190faf766` (2026-09-29).  
**TikTok publishing, scopes, Login Kit, APK and Google Play:** out of scope and unchanged.

## Source of truth

- PostgreSQL `growth_media_artifacts` is authoritative for artifact identity, provenance, quality result, and state.
- The Railway Volume is authoritative for the private MP4 bytes.
- `MEDIA_READY` is derived only when `quality_status=QUALITY_PASS`, `storage_state=STORED_VERIFIED`, and a fresh complete SHA-256/size readback succeeds.
- Creative `media_hash` is a display/index field. It is not by itself proof that bytes still exist.
- The video endpoint never renders. It requires operator authentication and returns only the latest passing, verified artifact for that creative.

## Files changed

- `server/growth_models.py` — artifact provenance/state model.
- `server/migrations/versions/0010_durable_media_artifacts.py` — migration from `0009_growth_runtime_quality`.
- `server/media_storage.py` — private Railway volume implementation, safe key resolution, quota checks, streaming SHA-256, atomic immutable promotion, readback and reconciliation.
- `server/growth_renderer.py` — hashes rendered media incrementally rather than reading the entire MP4 into memory.
- `server/growth_worker.py` — volume-backed render, artifact journaling, atomic promotion, readback gate, restart reconciliation and no-volume queue behavior.
- `server/growth_api.py` — verified-only video delivery and storage truth in overview.
- `server/api.py` — storage injection, media status and migration readiness at `0010_durable_media_artifacts`.
- `server/tests/test_media_storage.py`, `server/tests/test_growth_queue.py`, `server/tests/test_api.py` — storage, integrity, retry/recovery and delivery contracts.
- `docs/DURABLE_MEDIA_BASELINE.md` — pre-change audit.

The pre-existing untracked `docs/AGENCYOS_CROSS_STUDY_2026-09-29.md` was not changed.

## Storage provider and rationale

**Selected:** Railway Volume filesystem, rooted at `${RAILWAY_VOLUME_MOUNT_PATH}/agenttiktok-media`.

This is a single-owner, single-service application and does not need public objects. The volume removes external storage accounts, tokens and public URLs. Files remain private to the service and can only be requested through authenticated server routes. No local temporary fallback is permitted in Railway. If a volume is absent or read-only, render jobs remain queued and media reads fail closed.

Railway's current volume documentation says mounted data persists across deployments, while volumes constrain service replication and cause interruption during remount. Cloudflare R2 was evaluated but not selected because it would add a bucket, account token and secret lifecycle for this stage. See official links in the baseline audit.

## Artifact model and state machine

Each artifact binds `experiment → creative → render job → render attempt → output hash → dimensions/codec/duration → quality manifest → object key → storage verification timestamps`. The canonical key is immutable and content-addressed: `media/{creative_id}/{sha256}.mp4`. Staging keys are scoped to render job and attempt under `.staging/`.

Storage states:

`RENDERED_TEMPORARY → STORING → STORED_UNVERIFIED → STORED_VERIFIED`

Exceptional states are `UNKNOWN`, `ARTIFACT_MISSING`, `ARTIFACT_CORRUPT`, `STORAGE_FAILED`, and `ARTIFACT_DISCARDED`. Missing/corrupt state never becomes ready. A hard quality failure retains its hash/manifest provenance row as `ARTIFACT_DISCARDED`, then deletes staged bytes. A replacement render gets a new attempt and physical artifact identity; the failed identity remains in the database.

Quality is a separate axis (`QUALITY_PASS`, `QUALITY_REVIEW`, `QUALITY_FAIL`). Only `QUALITY_PASS + STORED_VERIFIED` can be served as `MEDIA_READY`. Review artifacts may be stored for evidence but are blocked from delivery. A hard quality failure marks the creative/job failed, commits provenance, and removes its staging data.

## Write flow, transaction boundary and idempotency

1. Worker claims a database job using the existing PostgreSQL lease. If the volume is absent, it will not claim `RENDER_VIDEO` jobs.
2. FFmpeg renders inside a unique persistent-volume staging directory. The renderer writes MP4, manifest and sidecars; hashes are calculated incrementally.
3. Worker checks that renderer hash, manifest hash, measured size, and media metadata agree, then inserts the artifact row and commits `RENDERED_TEMPORARY`.
4. Worker commits `STORING`, atomically hard-links the staged MP4 to its content-addressed final key without overwriting, then commits `STORED_UNVERIFIED`.
5. Worker opens the canonical file and recomputes its full byte count and SHA-256. Only on exact equality does it commit `STORED_VERIFIED`, creative state and the final job state.
6. Staging is removed only after the database confirms verification. If cleanup fails, the verified final object remains authoritative and staging is safe to reconcile later.

PostgreSQL transactions do not include filesystem writes. The durable artifact row is the recovery journal; each filesystem side effect has a preceding state commit and is idempotent by immutable object key and expected digest. `os.link` gives create-if-absent semantics on the same volume. Existing content is verified and never overwritten.

## Crash recovery and reconciliation

- Crash after FFmpeg but before artifact-row commit: the next lease holder enumerates that job's staging attempts, checks manifest/hash consistency, and journals/promotes the same staged bytes.
- Crash after artifact-row commit but before promotion: the row points at its staging key; a retry verifies and promotes it.
- Crash after promotion but before the `STORED_UNVERIFIED` commit: retry finds the content-addressed object and checks its exact digest.
- Crash after promotion/state commit but before readback: retry performs the readback gate.
- Crash after verified commit but before staging cleanup: verified object remains usable; staging cleanup is best effort.
- Missing canonical bytes mark that artifact missing; corrupted bytes block the creative and are never silently replaced at the same key.
- Expired PostgreSQL leases permit a new worker process to perform reconciliation. The integration test simulates restart state and asserts same artifact id/hash with renderer disabled.

## Access control, retention and cost

- Artifact objects are not exposed through a public bucket or public static route.
- Download route uses existing operator authentication and re-verifies the entire file immediately before returning it.
- Object keys reject traversal, absolute paths, backslashes, invalid identity characters and symlinked object files.
- Current conservative defaults: 64 MiB maximum MP4 and 400 MiB managed media budget. `MEDIA_MAX_ARTIFACT_BYTES` and `MEDIA_MAX_TOTAL_BYTES` may tune those limits; the total limit must be at least the per-artifact limit. Free Railway plan limits may be lower than the default managed quota, so configure the actual volume size before enabling render jobs.
- No automated retention deletion is enabled. Deleting artifacts without an explicit lifecycle policy would break provenance; volume exhaustion safely stops new render claims.
- Local staging is placed on the volume so it survives process restarts. It is private but consumes persistent capacity until verified cleanup/reconciliation.

## Test evidence and current status

- `python -m compileall -q server` — passed.
- `python -m pytest -q server/tests` — **58 passed, 1 skipped** (2026-09-29 local).
- The local filesystem integration test uses actual directories, files, hard links, hash reads and a simulated worker restart. It proves local code behavior, not Railway's physical mount.
- API test asserts a video GET cannot render on demand. The endpoint verifies the object and reports `MEDIA_READY` only for an eligible persisted artifact.
- `git diff --check` — passed.
- Workflow/GitHub GREEN for this new patch — **NOT PROVEN**.
- Railway deploy at this new source hash — **NOT PROVEN**.
- Railway persistent volume attached — **NOT PROVEN**.
- Railway restart proof of same `artifact_id` + SHA-256 — **NOT PROVEN**.
- Android playback from Railway after restart — **NOT PROVEN**.
- First TikTok real video delivery — **NOT PART OF THIS CHANGE**.

## Required next dependency

An owner must attach a Railway Volume to service `tiktok-shop-profit-agent-uk`, choose a mount path so Railway injects `RAILWAY_VOLUME_MOUNT_PATH`, and allow the service to redeploy/restart. No media-storage secret is required. After that, deploy this change, render a real creative, record artifact id/hash, restart the Railway service, read the same artifact again and compare id/hash and playback. Until those actions are complete, durable media must remain **NOT PROVEN** in production.
