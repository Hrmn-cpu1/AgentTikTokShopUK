"""Safe action/effect/outbox foundation. No external provider adapter lives here."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .action_effect_models import ActionContract, EffectAttempt, EffectEvidence, EffectLedger, EffectOutbox
from .growth_models import GrowthCreative, GrowthMediaArtifact, NicheHypothesis
from .growth_queue_models import GrowthJob
from .growth_worker import LeaseIdentity, LeaseLostError, renew_lease

logger = logging.getLogger(__name__)
OUTBOX_LEASE_SECONDS = 120
_SECRET_KEY_PARTS = ("token", "secret", "password", "credential", "authorization", "cookie")
_LOCAL_TEST_FIELDS = {"purpose", "case", "scenario"}


class ActionContractConflict(ValueError):
    """An idempotency key was reused for materially different action data."""


class ReconciliationRequired(RuntimeError):
    """An ambiguous effect must be reconciled before any further attempt."""


@dataclass(frozen=True)
class ActionIntentIdentity:
    action_contract_id: str
    effect_id: str
    outbox_id: str
    request_digest: str
    duplicate: bool = False


@dataclass(frozen=True)
class OutboxLeaseIdentity:
    outbox_id: str
    effect_id: str
    owner: str
    generation: int
    attempt_id: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _reject_secret_fields(value, path="parameters"):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SECRET_KEY_PARTS):
                raise ValueError(f"sensitive field is forbidden in action data: {path}.{key}")
            _reject_secret_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, f"{path}[{index}]")


def _current_db_clock(session: Session):
    return func.clock_timestamp() if session.get_bind().dialect.name == "postgresql" else utcnow()


def _load_existing(session: Session, key: str, request_digest: str) -> ActionIntentIdentity | None:
    contract = session.scalar(select(ActionContract).where(ActionContract.idempotency_key == key))
    if contract is None:
        return None
    if contract.request_digest != request_digest:
        raise ActionContractConflict("idempotency key is already bound to a different immutable contract")
    effect = session.scalar(select(EffectLedger).where(EffectLedger.action_contract_id == contract.action_contract_id))
    outbox = session.scalar(select(EffectOutbox).where(EffectOutbox.action_contract_id == contract.action_contract_id))
    if effect is None or outbox is None:
        raise RuntimeError("integrity violation: prepared action is missing its effect or outbox row")
    return ActionIntentIdentity(contract.action_contract_id, effect.effect_id, outbox.outbox_id,
                                contract.request_digest, duplicate=True)


def create_action_intent(session: Session, *, identity: LeaseIdentity, idempotency_key: str,
                         action_type: str, market: str, experiment_id: str, creative_id: str,
                         artifact_id: str, required_capability: str, provider: str,
                         business_parameters: dict, target_account_id: str | None = None,
                         requested_at: datetime | None = None, media_store=None,
                         fault_after: str | None = None) -> ActionIntentIdentity:
    """Atomically persist a safe LOCAL_TEST contract + ledger row + outbox intent.

    The selected local test sink never performs a network call. Production action types
    are deliberately denied until Provider Lab installs a separately reviewed adapter.
    The caller owns and commits/rolls back the transaction.
    """
    if action_type != "LOCAL_TEST" or provider != "INTERNAL_TEST_STUB":
        raise ValueError("this phase only admits LOCAL_TEST / INTERNAL_TEST_STUB actions")
    if not idempotency_key or len(idempotency_key) > 180:
        raise ValueError("idempotency_key must be 1..180 characters")
    if market not in {"BR", "UK", "US", "DE", "FR", "ES", "JP", "KR", "CN", "IN", "ID", "VN", "TH", "SG", "RU"}:
        raise ValueError("unsupported market")
    if required_capability != "internal.test":
        raise ValueError("LOCAL_TEST requires the internal.test capability")
    if not isinstance(business_parameters, dict):
        raise ValueError("business_parameters must be a JSON object")
    _reject_secret_fields(business_parameters)
    if set(business_parameters) - _LOCAL_TEST_FIELDS or any(
            not isinstance(value, str) or len(value) > 160 for value in business_parameters.values()):
        raise ValueError("LOCAL_TEST business_parameters are limited to short purpose/case/scenario labels")
    params_canonical = _canonical(business_parameters)
    params_digest = hashlib.sha256(params_canonical.encode("utf-8")).hexdigest()

    creative = session.get(GrowthCreative, creative_id)
    artifact = session.get(GrowthMediaArtifact, artifact_id)
    if creative is None or artifact is None:
        raise ValueError("action contract requires an existing creative and media artifact")
    if creative.experiment_id != experiment_id or creative.state != "READY":
        raise ValueError("creative/experiment binding is invalid or creative is not READY")
    niche = session.get(NicheHypothesis, creative.niche_id)
    if niche is None or niche.market != market:
        raise ValueError("action market does not match the creative's recorded market")
    if artifact.creative_id != creative_id or artifact.quality_status != "QUALITY_PASS" or artifact.storage_state != "STORED_VERIFIED":
        raise ValueError("action contract requires this creative's QUALITY_PASS / STORED_VERIFIED artifact")
    if not creative.media_hash or creative.media_hash != artifact.sha256:
        raise ValueError("artifact SHA-256 does not match the creative's recorded media hash")
    if media_store is not None:
        verified = media_store.verify_object(artifact.object_key, expected_sha256=artifact.sha256,
            expected_size_bytes=artifact.size_bytes, expected_content_type=artifact.content_type)
        if verified.sha256 != artifact.sha256 or verified.size_bytes != artifact.size_bytes:
            raise ValueError("fresh media readback does not match the verified artifact")

    request_material = {
        "action_type": action_type, "market": market, "experiment_id": experiment_id,
        "creative_id": creative_id, "artifact_id": artifact_id, "job_id": identity.job_id,
        "required_capability": required_capability, "provider": provider,
        "target_account_id": target_account_id, "business_parameters_digest": params_digest,
        "artifact_sha256": artifact.sha256,
    }
    request_digest = _digest(request_material)
    previous = _load_existing(session, idempotency_key, request_digest)
    if previous is not None:
        # A read-only duplicate lookup can return the already-frozen identity after
        # lease expiry. It never prepares a new effect or changes outbox state.
        return previous

    # Renewal is a conditional DB write and holds the GrowthJob row lock through commit.
    if not renew_lease(session, identity):
        raise LeaseLostError(f"no current lease for action preparation job {identity.job_id}")
    job = session.scalar(select(GrowthJob).where(GrowthJob.job_id == identity.job_id).with_for_update())
    if (job is None or job.state != "RUNNING" or job.lease_owner != identity.owner or
            job.lease_generation != identity.generation or job.lease_attempt_id != identity.attempt_id or
            job.creative_id != creative_id or job.lease_until is None):
        raise LeaseLostError("job lease snapshot does not authorize this action preparation")

    now = utcnow()
    requested = requested_at or now
    contract_id, effect_id, outbox_id = str(uuid4()), str(uuid4()), str(uuid4())
    effect_key = f"{provider}:{action_type}:{contract_id}"
    dedupe_key = f"{effect_key}:dispatch:v1"
    outbox_payload = {"actionContractId": contract_id, "effectId": effect_id,
                      "actionType": action_type, "provider": provider}
    payload = _canonical(outbox_payload)
    contract = ActionContract(action_contract_id=contract_id, idempotency_key=idempotency_key,
        action_type=action_type, market=market, experiment_id=experiment_id, creative_id=creative_id,
        artifact_id=artifact_id, job_id=identity.job_id, job_attempt_id=identity.attempt_id,
        required_capability=required_capability, provider=provider, target_account_id=target_account_id,
        business_parameters=params_canonical, business_parameters_digest=params_digest,
        request_digest=request_digest, artifact_sha256=artifact.sha256, requested_at=requested,
        created_at=now, contract_version=1, status="PREPARED", lease_owner=identity.owner,
        lease_generation=identity.generation, lease_attempt_id=identity.attempt_id)
    effect = EffectLedger(effect_id=effect_id, effect_key=effect_key,
        action_contract_id=contract_id, operation=action_type, provider=provider, state="PREPARED",
        request_digest=request_digest, artifact_sha256=artifact.sha256, current_attempt=0,
        reconciliation_required=False, created_at=now, updated_at=now)
    outbox = EffectOutbox(outbox_id=outbox_id, topic="action.dispatch.requested",
        aggregate_type="effect", aggregate_id=effect_id, effect_id=effect_id,
        action_contract_id=contract_id, dedupe_key=dedupe_key, payload=payload,
        payload_digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(), state="PENDING",
        created_at=now, available_at=now, lease_generation=0, revision=0, attempts=0)
    try:
        # Savepoint makes a concurrent idempotency race recoverable while preserving
        # the caller's encompassing transaction and the all-or-none three-row invariant.
        with session.begin_nested():
            session.add(contract)
            session.flush()
            if fault_after == "contract":
                raise RuntimeError("injected fault after contract insert")
            session.add(effect)
            session.flush()
            if fault_after == "effect":
                raise RuntimeError("injected fault after effect insert")
            session.add(outbox)
            session.flush()
            if fault_after == "outbox":
                raise RuntimeError("injected fault after outbox insert")
    except IntegrityError:
        duplicate = _load_existing(session, idempotency_key, request_digest)
        if duplicate is not None:
            return duplicate
        raise
    return ActionIntentIdentity(contract_id, effect_id, outbox_id, request_digest)


def renew_outbox_lease(session: Session, identity: OutboxLeaseIdentity,
                       *, seconds: int = OUTBOX_LEASE_SECONDS) -> bool:
    clock = _current_db_clock(session)
    result = session.execute(update(EffectOutbox).where(
        EffectOutbox.outbox_id == identity.outbox_id,
        EffectOutbox.state == "CLAIMED",
        EffectOutbox.lease_owner == identity.owner,
        EffectOutbox.lease_generation == identity.generation,
        EffectOutbox.lease_attempt_id == identity.attempt_id,
        EffectOutbox.lease_until > clock,
    ).values(lease_until=clock + timedelta(seconds=seconds), heartbeat_at=clock,
             revision=EffectOutbox.revision + 1),
        execution_options={"synchronize_session": False})
    return result.rowcount == 1


def claim_outbox(session: Session, worker_id: str, *, seconds: int = OUTBOX_LEASE_SECONDS) -> OutboxLeaseIdentity | None:
    now = utcnow()
    clock = _current_db_clock(session)
    candidate = session.scalar(select(EffectOutbox).join(
        EffectLedger, EffectLedger.effect_id == EffectOutbox.effect_id).where(
        EffectLedger.state.in_(("PREPARED", "DISPATCH_PENDING")),
        (EffectOutbox.state == "PENDING") |
        ((EffectOutbox.state == "CLAIMED") & (EffectOutbox.lease_until < clock)),
        EffectOutbox.available_at <= clock,
    ).order_by(EffectOutbox.available_at).with_for_update(skip_locked=True).limit(1))
    if candidate is None:
        return None
    attempt_id = str(uuid4())
    result = session.execute(update(EffectOutbox).where(
        EffectOutbox.outbox_id == candidate.outbox_id,
        EffectOutbox.effect_id.in_(select(EffectLedger.effect_id).where(
            EffectLedger.effect_id == EffectOutbox.effect_id,
            EffectLedger.state.in_(("PREPARED", "DISPATCH_PENDING")))),
        ((EffectOutbox.state == "PENDING") |
         ((EffectOutbox.state == "CLAIMED") & (EffectOutbox.lease_until < clock))),
        EffectOutbox.available_at <= clock,
    ).values(state="CLAIMED", lease_owner=worker_id,
        lease_until=clock + timedelta(seconds=seconds), claimed_at=now, heartbeat_at=now,
        lease_generation=EffectOutbox.lease_generation + 1,
        lease_attempt_id=attempt_id, attempts=EffectOutbox.attempts + 1,
        revision=EffectOutbox.revision + 1),
        execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        session.rollback()
        return None
    # The conditional UPDATE intentionally disables ORM synchronization. Reload
    # its new fencing generation before creating the attempt identity.
    session.refresh(candidate)
    row = candidate
    contract = session.get(ActionContract, row.action_contract_id)
    effect = session.get(EffectLedger, row.effect_id)
    effect.current_attempt += 1
    effect.updated_at = now
    session.add(EffectAttempt(attempt_id=attempt_id, effect_id=row.effect_id, outbox_id=row.outbox_id,
        job_id=contract.job_id, job_attempt_id=contract.job_attempt_id,
        job_worker_id=contract.lease_owner, job_lease_generation=contract.lease_generation,
        outbox_worker_id=worker_id, outbox_lease_generation=row.lease_generation,
        outbox_attempt_id=attempt_id, started_at=now,
        stage="OUTBOX_CLAIMED", result_class="IN_PROGRESS"))
    session.flush()
    return OutboxLeaseIdentity(row.outbox_id, row.effect_id, worker_id, row.lease_generation, attempt_id)


def acknowledge_outbox(session: Session, identity: OutboxLeaseIdentity) -> bool:
    """Internal ACK only. This function never confirms the provider effect."""
    attempt = session.get(EffectAttempt, identity.attempt_id)
    if (attempt is None or attempt.effect_id != identity.effect_id or
            attempt.outbox_id != identity.outbox_id or attempt.outbox_worker_id != identity.owner or
            attempt.outbox_lease_generation != identity.generation or
            attempt.outbox_attempt_id != identity.attempt_id):
        logger.warning("Rejected mismatched outbox ACK identity outbox=%s generation=%s", identity.outbox_id, identity.generation)
        return False
    clock = _current_db_clock(session)
    now = utcnow()
    result = session.execute(update(EffectOutbox).where(
        EffectOutbox.outbox_id == identity.outbox_id,
        EffectOutbox.state == "CLAIMED",
        EffectOutbox.lease_owner == identity.owner,
        EffectOutbox.lease_generation == identity.generation,
        EffectOutbox.lease_attempt_id == identity.attempt_id,
        EffectOutbox.lease_until > clock,
    ).values(state="ACKED", acked_at=now, lease_owner=None, lease_until=None,
             revision=EffectOutbox.revision + 1),
        execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        logger.warning("Rejected stale outbox ACK outbox=%s generation=%s", identity.outbox_id, identity.generation)
        return False
    attempt.finished_at = now
    if attempt.result_class == "OUTCOME_UNKNOWN":
        attempt.stage = "INTERNAL_ACK_AFTER_UNKNOWN"
    else:
        attempt.stage = "INTERNAL_TEST_SINK_ACK"
        attempt.result_class = "INTERNAL_ACK_ONLY"
    session.flush()
    return True


def mark_effect_unknown_before_provider_io(session: Session, identity: OutboxLeaseIdentity) -> None:
    """Persist ambiguity under the current outbox fence before any future provider I/O.

    This is a boundary primitive only. No provider call is made from this module.
    """
    if not renew_outbox_lease(session, identity):
        raise LeaseLostError(f"no current outbox lease for {identity.outbox_id}")
    effect = session.scalar(select(EffectLedger).where(
        EffectLedger.effect_id == identity.effect_id).with_for_update())
    if effect is None:
        raise RuntimeError("outbox references a missing effect")
    outbox = session.get(EffectOutbox, identity.outbox_id)
    attempt = session.get(EffectAttempt, identity.attempt_id)
    if (outbox is None or outbox.effect_id != identity.effect_id or
            attempt is None or attempt.effect_id != identity.effect_id or
            attempt.outbox_id != identity.outbox_id or attempt.outbox_worker_id != identity.owner or
            attempt.outbox_lease_generation != identity.generation or
            attempt.outbox_attempt_id != identity.attempt_id):
        raise LeaseLostError("outbox lease identity does not authorize this effect attempt")
    if effect.state in {"UNKNOWN", "RECONCILIATION_REQUIRED"}:
        effect.state = "RECONCILIATION_REQUIRED"
        effect.reconciliation_required = True
        effect.updated_at = utcnow()
        return
    if effect.state != "PREPARED":
        raise ReconciliationRequired(f"effect in {effect.state} cannot enter provider boundary")
    effect.state = "UNKNOWN"
    effect.reconciliation_required = True
    effect.updated_at = utcnow()
    attempt.stage = "EXTERNAL_EFFECT_BOUNDARY"
    attempt.result_class = "OUTCOME_UNKNOWN"
    session.flush()


def request_effect_retry(session: Session, effect_id: str) -> str:
    """Never create a fresh identity/outbox after ambiguity; require reconciliation."""
    effect = session.scalar(select(EffectLedger).where(EffectLedger.effect_id == effect_id).with_for_update())
    if effect is None:
        raise KeyError(effect_id)
    if effect.state in {"UNKNOWN", "RECONCILIATION_REQUIRED"} or effect.reconciliation_required:
        effect.state = "RECONCILIATION_REQUIRED"
        effect.reconciliation_required = True
        effect.updated_at = utcnow()
        session.flush()
        return "RECONCILIATION_REQUIRED"
    return "RETRY_NOT_AUTHORIZED_IN_FOUNDATION_PHASE"


def record_effect_evidence(session: Session, *, effect_id: str, evidence_type: str,
                           source: str, source_reference: str, observed_at: datetime,
                           payload: dict, classification: str) -> EffectEvidence:
    """Store a provenance-tagged observation; it does not grant authority or confirm."""
    allowed = {"SYSTEM_OBSERVED", "PROVIDER_OBSERVED", "OWNER_REPORTED", "RECONCILIATION_RESULT"}
    if classification not in allowed:
        raise ValueError("unsupported evidence classification")
    _reject_secret_fields(payload)
    payload_digest = _digest(payload)
    existing = session.scalar(select(EffectEvidence).where(
        EffectEvidence.effect_id == effect_id,
        EffectEvidence.evidence_type == evidence_type,
        EffectEvidence.payload_digest == payload_digest))
    if existing is not None:
        return existing
    evidence = EffectEvidence(evidence_id=str(uuid4()), effect_id=effect_id,
        evidence_type=evidence_type, source=source, source_reference=source_reference,
        observed_at=observed_at, payload_digest=payload_digest,
        classification=classification, created_at=utcnow())
    session.add(evidence)
    session.flush()
    # No state promotion: evidence must be separately evaluated by reconciliation.
    return evidence
