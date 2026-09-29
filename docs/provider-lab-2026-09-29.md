# Provider Lab and reconciliation

## Scope

`server/provider_lab.py` is an internal deterministic simulator. It makes no HTTP
requests, has no FastAPI route, and is not a TikTok adapter. Production TikTok
publishing, draft upload, and real-provider credentials remain untouched.

The lab consumes the existing immutable Action Contract, Effect Ledger, and
fenced Transactional Outbox. It snapshots provider, operation, artifact ID and
SHA-256, target account, business-parameter digest, request/contract digest, and
the stable effect marker from those records. No second action architecture is
introduced.

## Send outcome rules

| Simulation | Durable result | May it retry? |
|---|---|---|
| `SUCCESS_ACK` | Outbox ACK; effect remains `UNKNOWN` | No; observe first |
| Timeout before accept | `FAILED_BEFORE_EFFECT`, with a no-effect evidence digest | Only with explicit retry authorization and provider capability |
| Provider reject | `REJECTED`, with a no-effect evidence digest | No automatic retry |
| Rate limit / 5xx before send | Positive no-effect result | Only if the caller supplies fresh retry authorization and the adapter declares safe pre-effect retry |
| Timeout/drop/5xx after accept | `UNKNOWN`, outbox ACK only | Never blindly; reconcile |
| Malformed response | `UNKNOWN` | Never blindly; reconcile |

The dispatcher commits `UNKNOWN` while holding the current outbox fence before
the simulated send. The default is no retry authorization. An authorized safe
retry reuses the same contract, effect, effect key, and outbox; it increments a
new fenced attempt. It never mints a second logical action.

## Observation and confirmation

Observation is a separate read path. It queries the simulator using the stable
effect marker and compares one candidate with the frozen provider, operation,
effect/action IDs, contract digest, artifact ID and SHA, target, parameter digest,
request digest, and provider reference when that capability exists.

- unavailable observation, zero matches, multiple matches, and any mismatch
  record reconciliation evidence and remain `RECONCILIATION_REQUIRED`;
- exactly one complete match records digest-only evidence and atomically stores
  `confirmation_evidence_id`, `confirmed_at`, and `CONFIRMED`;
- a fault after evidence insertion rolls back both the evidence and confirmation.

Migration `0013_effect_confirmation_evidence` adds a composite foreign key from
the effect to evidence belonging to that same effect. The existing `0012` schema
did not retain this explicit confirmation link.

## Capability degradation

The simulator declares `supports_idempotency`, `supports_status_lookup`,
`supports_observation`, `supports_provider_reference`, and
`supports_safe_retry_before_effect`. Missing status/observation capability
returns unavailable and leaves the effect unresolved. Lack of idempotency keeps
the internal outbox from dispatching the same ambiguous effect again. Lack of a
provider reference is represented as unknown; the lab does not fabricate one.

## Verification record

Local adversarial coverage is in `server/tests/test_action_effects.py`; the live
PostgreSQL restart, lost-response, atomic-reconciliation, and stale-fence test is
in `server/tests/test_postgres.py` and runs in Backend CI against PostgreSQL 16.
The deployed migration and commit must be verified from Railway after CI passes.
