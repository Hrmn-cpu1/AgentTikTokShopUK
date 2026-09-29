# Durable media provenance reconciliation — 2026-09-29

## Verdict

- `HISTORICAL_MEDIA_CONTINUITY = UNKNOWN`
- `CURRENT_DURABLE_MEDIA = PROVEN` across pre-restart baseline T0 and post-restart baseline T1.
- No database or media file was changed to make the records agree. No render was started during this reconciliation.
- Android playback remains outside this backend proof.

## Conflicting historical note

The owner-supplied checkpoint `Texto colado(20260929-074453).txt` recorded:

| Field | Historical note |
|---|---|
| artifact_id | `13dd304b-bfb2-4002-90b1-ce60cd40ea0a` |
| creative_id | `creative-gtr-br-81ee0606898b025f741fb5d` |
| job_id | `71defb6a-3d92-419a-a75f-ff868b5ae957` |
| render attempt | `try-1-2ccd1311295a458da488` |
| SHA-256 | `a3c063b9c4de316b9c7ebffb4fbee6e63f3c471a86dad93f8bdc3981898246ea` |
| size | 3,075,632 bytes |

The current machine record retains the artifact, job, attempt, and size, but its `creative_id` and SHA-256 differ from that note. The current physical file, database row, and persisted manifest agree. PostgreSQL has no row-version/audit history for the media artifact identity columns, and the old checkpoint does not include an independently verifiable manifest, object key, or historical file digest. Therefore the old values cannot be classified as a documentation typo or as evidence of a past data/file change. They remain `UNKNOWN`; the note is not silently rewritten.

| Historical question | Finding |
|---|---|
| Was the artifact UUID changed? | `UNKNOWN`; the old note and current row show the same UUID, but there is no row-version history. |
| Did the creative association or object key change? | `UNKNOWN` before T0; both are stable across T0→T1. |
| Was an earlier rerender, rematerialization, or replacement performed? | `UNKNOWN` before T0; no render or replacement occurred between T0 and T1. |
| Is the discrepancy a documentation error, identity mapping error, or physical artifact change? | `UNKNOWN`; available evidence cannot distinguish these cases. |

## Current artifact identity

| Field | Verified value |
|---|---|
| artifact_id | `13dd304b-bfb2-4002-90b1-ce60cd40ea0a` |
| creative_id | `creative-gtr-br-81eee0606898b025f741fb5d` |
| experiment_id | `gtr-br-81eee0606898b025f741fb5d` |
| job_id / render_job_id | `71defb6a-3d92-419a-a75f-ff868b5ae957` |
| job type / state / attempts | `MATERIALIZE_DURABLE_MEDIA / SUCCEEDED / 1` |
| render attempt | `try-1-2ccd1311295a458da488` |
| object_key | `media/creative-gtr-br-81eee0606898b025f741fb5d/a3c063b9c4de316b9c7ebffb4bee6e63f3c471a86dad93f8bdc3981898246ea.mp4` |
| size | 3,075,632 bytes |
| SHA-256 | `a3c063b9c4de316b9c7ebffb4bee6e63f3c471a86dad93f8bdc3981898246ea` |
| quality / storage | `QUALITY_PASS / STORED_VERIFIED` |
| quality_manifest SHA-256 | `86459a16292eaa47cf26977e82b01947029d051778bf527107e3d824dd3e823c` |
| manifest `sha256` / PostgreSQL `sha256` / volume file SHA-256 | identical to the artifact SHA-256 above |
| media volume mount | `/data/media` (`/data/media/agenttiktok-media` is the media-store root) |
| PostgreSQL migration | `0012_action_effect_outbox` |

## Creation and state history

Times below are UTC and come from current PostgreSQL rows/transitions:

1. `2026-09-29 07:07:52.782958` — operator requested durable-media materialization (`READY → READY`); TikTok delivery was not invoked.
2. `2026-09-29 07:16:23.741110` — worker began the FFmpeg render (`READY → RENDERING`).
3. `2026-09-29 07:16:30.530154` — first known `growth_media_artifacts` row for this artifact.
4. `2026-09-29 07:16:30.570059` — artifact readback verified and creative returned to `READY` (`RENDERING → READY`).

The materialization job has one attempt and the three transitions listed above. Its canonical volume file has size 3,075,632, the verified SHA-256, and filesystem `mtime` `2026-09-29T07:16:30.140946Z` / `ctime` `2026-09-29T07:16:30.574436Z`.

## T0 → restart → T1 proof

T0 was read from the production PostgreSQL row, its quality manifest, and the canonical volume bytes before the Railway restart. Railway deployment `93bdf129-76a3-47dc-83e1-1333e0aa6d54` was active from commit `9d188abcbd490ad8b7fe6dabd5d917b9a27d8a5e`. Railway confirmed `Restart successful`; the existing container was stopped and then reconnected. T1 was queried from the same deployment after restart.

| Field | T0 | T1 |
|---|---|---|
| artifact_id | `13dd304b-bfb2-4002-90b1-ce60cd40ea0a` | unchanged |
| creative_id | `creative-gtr-br-81eee0606898b025f741fb5d` | unchanged |
| job_id | `71defb6a-3d92-419a-a75f-ff868b5ae957` | unchanged |
| render attempt | `try-1-2ccd1311295a458da488` | unchanged |
| object_key | as listed above | unchanged |
| size | 3,075,632 | 3,075,632 |
| PostgreSQL SHA-256 | current artifact SHA | unchanged |
| physical volume SHA-256 | current artifact SHA | unchanged |
| manifest SHA-256 | `86459a16292eaa47cf26977e82b01947029d051778bf527107e3d824dd3e823c` | unchanged |
| storage / quality | `STORED_VERIFIED / QUALITY_PASS` | unchanged |
| job | `SUCCEEDED`, attempts `1` | unchanged |
| job transitions | `3` | `3` |

After restart, local service checks returned `/health = 200` and `/ready = 200`; the media file was read from the `/data/media` volume and its SHA-256 was recomputed directly. No renderer was invoked between T0 and T1. The unchanged one-attempt job and transition count provide a second guard against a rerender being presented as persistence.

## Other media rows and scope

PostgreSQL also contains a separate `leaseproof_6f65c9c3a969` test artifact, with its own creative, job, render attempt, and object key, created around `08:25 UTC`. It has the same deterministic media SHA-256 and size, but it is a distinct artifact identity; it did not replace or alter `13dd304b-bfb2-4002-90b1-ce60cd40ea0a`. It is preserved.

No identity audit trail, database row history, or old physical bytes were available to establish the historical continuity beyond the matching artifact/job/attempt/size note. Object-key continuity before T0 is also `UNKNOWN` because the historical note did not record a key. The current durable invariant is independently established by T0/T1.

## Remaining gates

- Fresh post-change deployment baseline T2: pending any future code deployment.
- Android playback after restart: `ACTION_REQUIRED`.
- This proof does not imply delivery, TikTok publication, or publication permission.
