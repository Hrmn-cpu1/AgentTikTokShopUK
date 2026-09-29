# Durable Media — baseline audit before behavior changes

**Audited:** 2026-09-29, `main` at `24a11723eb31826feac772527828e23190faf766`.  
**Checkpoint preserved:** `checkpoint/mobile-render-green-e0a49d6` → `e0a49d607e59829c1bd812dcc39191fbd14dc163`.

## Existing render-to-video flow

| Step | Location | Current behavior |
|---|---|---|
| Render start | `server/growth_worker.py::finish_internal_job` | Worker calls `render_growth_plan()` for `RENDER_VIDEO` without an output directory; renderer creates `growth-render-*` under temporary filesystem. |
| MP4 generation | `server/growth_renderer.py::render_growth_plan` | FFmpeg writes `growth.mp4`; captions and thumbnail are temporary siblings. `ffprobe` extracts H.264/AAC metadata, 540×960 dimensions, duration; quality manifest is generated. |
| Hash | `server/growth_renderer.py` | SHA-256 is calculated before the manifest is written. Current implementation reads the entire MP4 into memory for `hashlib.sha256(output.read_bytes())`. |
| Quality | `server/growth_quality.py::evaluate_quality` | Deterministic checks return `QUALITY_PASS`, `QUALITY_REVIEW` or `QUALITY_FAIL`; quality and manifest are separate from storage. |
| Database metadata | `server/growth_worker.py` | Creative row stores `media_ref=local-render://…`, `media_hash`, quality status/JSON; no artifact table/object key/size/readback timestamps. |
| Worker cleanup | `server/growth_worker.py` | `cleanup()` runs in `finally`, including after successful render. The MP4 and its manifest/sidecars are deleted. |
| GET `/v1/growth/creatives/{creative_id}/video` | `server/growth_api.py::render_experiment_video` | Authenticates owner, loads the plan, creates a new temporary directory, rerenders, updates creative hash/quality/state, and returns `FileResponse`; response background task removes the new temporary directory. It does not serve the file previously rendered by the worker. |
| Recovery | `server/growth_queue_models.py`, `growth_worker.py` | Internal jobs use stable creative/type key, Postgres lease and reclaim after expiry. There is no media-storage reconciliation or exact artifact identity. |

## Existing tests

- `server/tests/test_growth_renderer.py`: FFmpeg/ffprobe render, dimensions/codecs/audio/captions/thumbnail/manifest/hash and motion; temporary test directory.
- `server/tests/test_growth_queue.py`: queue idempotency/claim, expired lease reclaim, pause behavior, worker render to READY/ACTION_REQUIRED. This worker test currently expects a rendered creative without durable storage.
- `server/tests/test_growth_quality.py`: quality policy.
- `server/tests/test_api.py`: authenticated API boundaries and NOT_PROVEN capability states; no restart/storage integration proof.

## Proven gap

The worker MP4 and later GET response can be logically equivalent renders but are not guaranteed to be the same physical bytes. The current `READY` and the video URL prove neither durable persistence nor readback integrity. Durable media readiness must be represented separately from render completion and require both an acceptable quality status and a verified persistent artifact.

## Storage decision

Use **Railway Volume filesystem storage** for this single-owner, single-service stage. The application will store private files below the mounted volume and expose only server-authorized, hash-verified reads. No public object URL, new cloud account, or storage secret is required. Railway documents that volumes persist across deployments; current caveats include one volume per service, no replicas with a volume, and deployment downtime while the volume is remounted. The selected architecture therefore assumes the existing single-instance worker and must fail closed when no volume mount is detected.

Cloudflare R2 was evaluated as the object-storage alternative. Its official docs list a 10 GB-month Standard free tier and free egress, but API-token/S3 credentials and an account/bucket setup would be required. That is more external setup than this single-owner volume needs now. No second provider will be implemented.

Official references:
- [Railway Volumes](https://docs.railway.com/volumes)
- [Railway Volume caveats](https://docs.railway.com/volumes/reference)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Cloudflare R2 tokens](https://developers.cloudflare.com/r2/api/tokens/)
