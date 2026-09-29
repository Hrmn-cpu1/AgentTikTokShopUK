# Mobile render freeze and visual inventory

Audit date: 29 September 2026. This checkpoint freezes the known-good mobile render path before the next visual prompt. No presentation redesign, Mr.Who? implementation, runtime change, storage change, scheduler, or publishing change is included.

## Source of truth

| Item | Verified value |
| --- | --- |
| Repository / working branch | `Hrmn-cpu1/AgentTikTokShopUK` / `main` |
| Main HEAD at audit start | `e0a49d607e59829c1bd812dcc39191fbd14dc163` — `fix(db): declare growth transition index` |
| GitHub Actions for that SHA | Frontend #240, Backend #52, E2E API #43, Android Debug APK #47 — all completed successfully |
| Railway check for that SHA | `acceptable-delight - tiktok-shop-profit-agent-uk` — success |
| Production readiness | `/ready` 200: database reachable, migration `0009_growth_runtime_quality`, TikTok authorization configured; `/health` 200 |
| Growth API presence | `/v1/growth/control`, `/overview`, `/run`, `/creatives/{creative_id}/video`, `/state`, `/observations`, `/observation-capabilities` appear in production OpenAPI |
| Physical-device proof | Owner report in `Texto colado(9).txt`: installed APK `e0a49d6`, operator session and `START` succeeded, experiment `vento` reached `READY` / `QUALITY_PASS`, video endpoint returned HTTP 200 and the ~19-second MP4 played on Android. This is separate from CI; the API credential and device logs were not independently inspected in this audit. |

The user-reported deployment SHA is `e0a49d607e59829c1bd812bd93bbc1ffaec89f7a` as provided in the attached checkpoint. GitHub's Railway status is green for the same source commit and production `/ready` reports migration 0009. The readiness route does not expose a deployment SHA, so the exact running image SHA is corroborated by the provider check rather than returned by `/ready` itself.

## Protected baseline

Created `checkpoint/mobile-render-green-e0a49d6` at exactly `e0a49d607e59829c1bd812bd93bbc1ffaec89f7a`. Read-back with `git ls-remote` confirmed both that checkpoint ref and `main` pointed to this SHA at creation. The checkpoint branch is a frozen reference; development remains on `main`. Do not move or reuse this ref for later work.

## Proven mobile render contract

```text
Android GrowthWorkspace
  → authenticated apiJson / operator session
  → POST /v1/growth/control {action: START}
  → run_first_experiment: collect fresh BR public signal, rank, select, save original plan
  → growth_jobs PREPARE_ASSETS (idempotency key: creative_id:job_type)
  → Railway worker claims lease
  → SCRIPTED/queued → ASSETS_PENDING
  → enqueue RENDER_VIDEO → RENDERING
  → FFmpeg + local narration/audio + captions + transitions + quality manifest
  → persist quality result and media hash; creative READY unless QUALITY_FAIL
  → GET /v1/growth/overview exposes media item and its videoUrl
  → GET /v1/growth/creatives/{creative_id}/video returns MP4
  → Android inline player plays the response
```

The transition ledger records state changes in `growth_state_transitions`; the work queue is in `growth_jobs`; creative, evidence, quality and media hash are in `growth_creatives`; source evidence is in `growth_trends`; control mode is in `growth_control`. The Android test package is `com.tiktokshopprofitagent.app`.

### Files and endpoints in that contract

| Stage | Source of behavior |
| --- | --- |
| Android UI, polling, Start control, MP4 fetch/player | `src/GrowthWorkspace.tsx` |
| Same-origin API, cookies, CSRF and operator identity | `src/apiClient.ts`, `server/api.py`, `server/connection_api.py` |
| Start, discovery, ranking, create-plan, overview and MP4 response | `server/growth_api.py` |
| Deterministic trend selection and original script/scene plan | `server/trend_sources.py`, `server/growth_brain.py`, `server/creative_style.py` |
| Durable jobs, leases, transitions, retries, pause/stop checkpoints | `server/growth_queue_models.py`, `server/growth_worker.py` |
| Video frames, motion, captions, audio, MP4, manifest and hash | `server/growth_renderer.py`, `server/growth_quality.py` |
| Relational state | `server/growth_models.py`, `server/migrations/versions/0006_growth_engine.py` through `0009_growth_runtime_quality.py` |
| Worker startup | `server/api.py`, `Dockerfile` (`GROWTH_WORKER_ENABLED=1`) |

## Regression shield coverage

The mobile path has both owner-reported device proof and automated coverage. `test_mobile_start_worker_ready_media_and_video_contract` was added as a minimal regression test because older coverage tested Start/queue, worker rendering, and the video endpoint in separate tests rather than one connected path. It does not change production code.

| Contract | Current automated protection |
| --- | --- |
| A. START control | `server/tests/test_api.py::test_growth_workspace_reads_server_truth_and_controls`; new mobile contract test |
| B. Experiment created from a fresh BR trend | `test_growth_workspace_reads_server_truth_and_controls`; `test_public_trend_to_original_mp4_is_idempotent_and_does_not_claim_delivery` |
| C. Idempotent queued job | control test; `server/tests/test_growth_queue.py::test_queue_idempotency_and_claim` |
| D. Transition into RENDERING | new mobile contract test checks `ASSETS_PENDING → RENDERING` |
| E. Real FFmpeg MP4 bytes | new mobile contract test; `test_growth_plan_renders_vertical_mp4_audio_captions_manifest_and_thumbnail` |
| F. Quality gate | `server/tests/test_growth_quality.py`; worker integration allows `QUALITY_PASS` or `QUALITY_REVIEW` according to runtime review checks. Device `QUALITY_PASS` is owner-reported evidence, not a fixed CI assertion. |
| G. RENDERING → READY | new mobile contract test; `server/tests/test_growth_queue.py::test_worker_advances_real_render_and_stops_at_action_required` |
| H. Media item in server overview | new mobile contract test checks the hash-backed media entry |
| I. Authenticated MP4 endpoint | new mobile contract test; `test_public_trend_to_original_mp4_is_idempotent_and_does_not_claim_delivery` |
| J. Overview server state | `test_growth_workspace_reads_server_truth_and_controls`; new mobile contract test |
| K. Operator session / CSRF | `server/tests/test_api.py::test_operator_browser_session_reads_server_truth_and_requires_csrf_for_writes`; `server/tests/test_tiktok_connection.py` session tests |
| L. TikTok identity / connection | `server/tests/test_tiktok_connection.py`; `server/tests/test_e2e.py::test_private_apk_web_login_returns_connected_identity_without_browser_session`. These use test providers; they do not replace the owner's real Login Kit/device proof. |
| M. UNKNOWN / NOT_PROVEN | observation and learning tests, including `test_observation_keeps_fourteen_views_out_of_learning_and_public_feed`; new mobile contract test asserts publication, observe, learn and repeat remain `NOT_PROVEN` without evidence |

Truth rules remain: `UNKNOWN ≠ ZERO`; a rendered file is not a delivery; delivery is not publication; publication needs external evidence. No follower, TikTok metric, learning conclusion, scheduler, or repeat cycle is synthesized from absence.

## MP4 durability debt

The limitation is still present:

1. `server/growth_worker.py` calls `render_growth_plan` without a durable output directory, records `media_ref`, SHA-256 and quality in PostgreSQL, then calls the renderer's `cleanup()` in `finally`.
2. `server/growth_renderer.py` uses a temporary render directory by default; it creates the MP4, SRT, thumbnail and manifest there.
3. `server/growth_api.py::render_experiment_video` creates another temporary directory, renders again on each GET, returns `FileResponse`, then removes the directory in its response background task.
4. PostgreSQL stores metadata/hash, not MP4 bytes. The hash is not proof that a retrievable binary is durably stored.

For a later prompt, make a dedicated artifact-store component responsible for atomic MP4 + manifest persistence, SHA-256 verification before READY, retrieval and retention. Evaluate a mounted persistent volume or object store against cost, backup, access control and deploy behavior. Do not fold that storage change into this visual freeze.

## Current visual inventory (no redesign performed)

### Header

- Gradient square logo containing **A** (`.gw-logo`).
- Main brand **AGENT TIKTOK**; subtitle **CONTENT ENGINE · BR**.
- Green dot and **CONNECTED** appear as a fixed header label in `GrowthWorkspace.tsx`; the header does not bind that label to `overview.identity.status`. Analytics separately displays server identity. This is a visual truth issue to resolve in a later presentation/state-contract change.
- Dark navy base with cyan, blue and pink gradients; compact Inter/system typography and lucide icons.

### Home

- Hero: “AGENTE DE CONTEÚDO · BRASIL”, server mode (`READY`, `RUNNING`, `PAUSED`, `STOPPED`, `ACTION_REQUIRED`, `BLOCKED`, `FAILED`), worker and scheduler, activity and active job.
- Three metric cards: experiments, rendered MP4, followers. Missing follower snapshot is `UNKNOWN`.
- Separate 1,000-follower goal card; progress is shown only when a backed follower snapshot exists.
- Pipeline is a dense text/status list for discover, analyze, create, render, delivery, autonomous publish, observe, learn and repeat.
- Controls: start/resume, open latest video, pause, emergency stop. Recent experiment card follows the controls.

### Experiments

- Server-backed list with topic, experiment ID/time, search score and TikTok views (`UNKNOWN` when absent).
- Details include source/ref, geography, search score/components, observed time, selection reason/evidence, hook, hypothesis, scene plan, visual/audio asset plan, delivery state, observation and learning.

### Media

- Text-heavy generated-media list with topic, state, truncated SHA-256 and timestamp.
- Open fetches the video URL and displays an inline video player in Preview.
- Preview offers MP4 download and Android TikTok intent / Web Share handoff. The UI says this does not confirm import or publication. Reopening currently causes backend rerender (see storage debt).

### Analytics

- Identity and scope capabilities for follower count, public video metrics and watch-time/retention.
- Manual observation form labelled `OWNER_REPORTED`, with publication link/ID, evidence reference, timestamp and optional views/likes/comments/shares. Blank values remain `UNKNOWN`.
- Observation cards and learning status/rationale; thresholds and replication are server-side.

### Tools

- **Manual Studio:** operator-provided photo, hook, message and CTA; separate manual video endpoint and share flow.
- **Niche Settings:** explicitly `UNKNOWN` / not implemented.
- **Trend Sources:** Google Trends BR search interest; no claim of TikTok virality.
- **Scheduling:** `BLOCKED` / `NOT_CONFIGURED`; no automatic repeat.
- **System Status:** identity, mode/time and disconnect action.

### Navigation

Fixed bottom bar: **INÍCIO / EXPERIMENTOS / MÍDIA / ANALYTICS / FERRAMENTAS**.

## Legacy visual elements to catalogue for the next prompt

No elements were removed or changed during this checkpoint. Mark these for later design work:

- square **A** logo;
- **AGENT TIKTOK** primary branding and technical **CONTENT ENGINE · BR** subtitle;
- technical status labels and dense pipeline;
- large rounded hero/metric/control cards and repeated panels;
- weak hierarchy between headline, goal, controls and recent experiment;
- pipeline rendered as a long operational status list;
- media library dominated by text/hash rather than visual thumbnails;
- analytics layout resembles a data-entry/admin form;
- no Mr.Who? character or brand identity yet.

## Redesign safety map

| Class | Files/components | Boundary for future prompts |
| --- | --- | --- |
| A — presentation only | `src/styles.css` selectors scoped to `.gw-*`; presentational icon/color/spacing classes in `GrowthWorkspace.tsx` | Safe to restyle if component selectors stay scoped and no control/form semantics are removed. `styles.css` is shared with older screens; avoid global selectors. |
| B — presentation + server state | `GrowthWorkspace.tsx` page render branches, data types and `refresh`; list/experiment/media/analytics/tools views; `GrowthStudio.tsx` presentation | May be rearranged, but preserve field meanings, `UNKNOWN`, owner-reported labels, evidence, mode mapping and empty states. Header CONNECTED must eventually bind to the actual status. |
| C — operational control | `GrowthWorkspace.tsx`: `control`, `startAgent`, `openMedia`, `sendToTikTok`, `submitObservation`; button enablement, CSRF, confirmation, refresh/polling; `src/apiClient.ts`; Android share plugin and `GrowthStudio` submit/share handlers | Treat as protected action contracts. Do not restyle by replacing handlers, dropping CSRF/idempotency, changing payloads, or interpreting intent as delivery/publication. Keep accessibility labels and disabled reasons. |
| D — backend / worker | `server/api.py`, `server/growth_api.py`, `server/growth_worker.py`, `server/growth_queue_models.py`, `server/growth_models.py`, migrations `0006–0009`, `server/growth_brain.py`, `server/trend_sources.py`, `server/growth_renderer.py`, `server/growth_quality.py`, Docker worker startup | Do not touch in visual redesign prompts. API response names, DB rows, transition logic, queue leases, quality gate, renderer, migration head and `/ready` are part of the proven engine contract. |

The UI has no screenshot/golden-image tests. Existing automated protection is behavioral/API/render-oriented; future presentation work should keep those tests and add visual QA separately, without changing operational semantics.

## Local verification for this checkpoint

- Before documentation/test checkpoint: Backend `52 passed, 1 skipped`; Frontend `284 passed`; `npm run build` green. On the starting SHA, all four corresponding GitHub workflows were green.
- The newly added regression test passed locally: `1 passed`; its full backend suite and the new documentation commit still need to complete CI before this checkpoint is considered published.
- `npm` has no configured lint script.

## Next prompt boundary

This document prepares the baseline only. Mr.Who? visual identity and all listed legacy replacements belong to Prompt #2. No new branding or appearance has been implemented here.
