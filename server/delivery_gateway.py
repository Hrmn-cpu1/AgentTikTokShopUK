"""Delivery gateway: durable identity, Android handoff evidence and conservative truth."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .action_effect_models import ActionContract, EffectLedger
from .action_effects import record_effect_evidence
from .delivery_models import DeliveryEffect
from .growth_models import GrowthCreative, GrowthMediaArtifact, NicheHypothesis
from .growth_queue_models import GrowthJob


ANDROID_TARGET = "ANDROID_SHARE_HANDOFF"
DIRECT_TARGET = "TIKTOK_OFFICIAL_DIRECT_POST"
UPLOAD_TARGET = "TIKTOK_OFFICIAL_UPLOAD_DRAFT"

_PROVIDER_FOR_TARGET = {
    ANDROID_TARGET: "ANDROID_SHARE",
    DIRECT_TARGET: "TIKTOK_OFFICIAL",
    UPLOAD_TARGET: "TIKTOK_OFFICIAL",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must include an explicit timezone")
    return value.astimezone(timezone.utc)


def _validate_delivery_binding(session: Session, delivery: DeliveryEffect):
    contract = session.get(ActionContract, delivery.action_contract_id)
    effect = session.get(EffectLedger, delivery.effect_id)
    artifact = session.get(GrowthMediaArtifact, delivery.artifact_id)
    creative = session.get(GrowthCreative, delivery.creative_id)
    if contract is None or effect is None or artifact is None or creative is None:
        raise RuntimeError("delivery binding references missing durable identity")
    if effect.action_contract_id != contract.action_contract_id:
        raise RuntimeError("delivery effect/action contract identity mismatch")
    if contract.artifact_id != artifact.artifact_id or contract.creative_id != creative.creative_id:
        raise RuntimeError("delivery artifact/creative binding mismatch")
    if effect.artifact_sha256 != delivery.artifact_sha256 or contract.artifact_sha256 != delivery.artifact_sha256:
        raise RuntimeError("delivery hash disagrees with frozen action/effect identity")
    if artifact.sha256 != delivery.artifact_sha256 or creative.media_hash != delivery.artifact_sha256:
        raise RuntimeError("delivery hash disagrees with verified media")
    if artifact.storage_state != "STORED_VERIFIED" or artifact.quality_status != "QUALITY_PASS":
        raise ValueError("delivery requires a STORED_VERIFIED / QUALITY_PASS artifact")
    if creative.state != "READY" or creative.quality_status != "QUALITY_PASS":
        raise ValueError("delivery requires a READY / QUALITY_PASS creative")
    if _PROVIDER_FOR_TARGET.get(delivery.target) != delivery.provider:
        raise RuntimeError("delivery provider does not match target")
    return contract, effect, artifact, creative


def prepare_delivery_for_effect(
    session: Session,
    *,
    action_contract_id: str,
    effect_id: str,
    target: str,
    target_account_id: str | None = None,
) -> DeliveryEffect:
    """Bind one already-frozen provider effect to one delivery target, idempotently."""
    if target not in _PROVIDER_FOR_TARGET:
        raise ValueError("unsupported delivery target")
    contract = session.get(ActionContract, action_contract_id)
    effect = session.get(EffectLedger, effect_id)
    if contract is None or effect is None or effect.action_contract_id != action_contract_id:
        raise ValueError("delivery requires an exact Action Contract / Effect Ledger pair")
    provider = _PROVIDER_FOR_TARGET[target]
    if contract.provider != provider or effect.provider != provider:
        raise ValueError("frozen provider identity does not authorize the requested target")
    artifact = session.get(GrowthMediaArtifact, contract.artifact_id)
    creative = session.get(GrowthCreative, contract.creative_id)
    if artifact is None or creative is None:
        raise ValueError("delivery requires the frozen artifact and creative")
    existing = session.scalar(select(DeliveryEffect).where(
        DeliveryEffect.action_contract_id == action_contract_id))
    if existing is not None:
        if (existing.effect_id, existing.target, existing.target_account_id) != (
                effect_id, target, target_account_id):
            raise ValueError("Action Contract is already bound to a different delivery")
        _validate_delivery_binding(session, existing)
        return existing
    now = utcnow()
    delivery = DeliveryEffect(
        delivery_id=str(uuid4()),
        action_contract_id=action_contract_id,
        effect_id=effect_id,
        artifact_id=contract.artifact_id,
        creative_id=contract.creative_id,
        artifact_sha256=contract.artifact_sha256,
        target=target,
        provider=provider,
        target_account_id=target_account_id,
        state="PREPARED",
        created_at=now,
        updated_at=now,
    )
    session.add(delivery)
    session.flush()
    _validate_delivery_binding(session, delivery)
    return delivery


def prepare_android_handoff_from_render(
    session: Session,
    *,
    job: GrowthJob,
    creative: GrowthCreative,
    artifact: GrowthMediaArtifact,
) -> DeliveryEffect:
    """Freeze a local device-handoff identity before the render worker releases its valid lease."""
    if (job.state != "RUNNING" or not job.lease_owner or not job.lease_attempt_id
            or job.lease_generation <= 0 or job.creative_id != creative.creative_id):
        raise ValueError("current render lease is required to freeze Android delivery identity")
    if (artifact.creative_id != creative.creative_id or artifact.render_job_id != job.job_id
            or artifact.storage_state != "STORED_VERIFIED"
            or artifact.quality_status != "QUALITY_PASS"
            or creative.state != "READY" or creative.quality_status != "QUALITY_PASS"):
        raise ValueError("Android handoff requires this READY creative's verified quality artifact")
    if not creative.media_hash or creative.media_hash != artifact.sha256:
        raise ValueError("Android handoff artifact hash mismatch")

    niche = session.get(NicheHypothesis, creative.niche_id)
    if niche is None:
        raise ValueError("creative market evidence is missing")
    idempotency_key = f"android-handoff:{artifact.artifact_id}"
    existing_contract = session.scalar(select(ActionContract).where(
        ActionContract.idempotency_key == idempotency_key))
    if existing_contract is not None:
        effect = session.scalar(select(EffectLedger).where(
            EffectLedger.action_contract_id == existing_contract.action_contract_id))
        delivery = session.scalar(select(DeliveryEffect).where(
            DeliveryEffect.action_contract_id == existing_contract.action_contract_id))
        if effect is None or delivery is None:
            raise RuntimeError("existing Android handoff identity is incomplete")
        _validate_delivery_binding(session, delivery)
        return delivery

    params = {"purpose": "operator_review", "target": ANDROID_TARGET}
    params_canonical = _canonical(params)
    params_digest = hashlib.sha256(params_canonical.encode("utf-8")).hexdigest()
    request_material = {
        "action_type": ANDROID_TARGET,
        "market": niche.market,
        "experiment_id": creative.experiment_id,
        "creative_id": creative.creative_id,
        "artifact_id": artifact.artifact_id,
        "job_id": job.job_id,
        "required_capability": "android.share.handoff",
        "provider": "ANDROID_SHARE",
        "target_account_id": None,
        "business_parameters_digest": params_digest,
        "artifact_sha256": artifact.sha256,
    }
    request_digest = _digest(request_material)
    now = utcnow()
    contract_id = str(uuid4())
    effect_id = str(uuid4())
    contract = ActionContract(
        action_contract_id=contract_id,
        idempotency_key=idempotency_key,
        action_type=ANDROID_TARGET,
        market=niche.market,
        experiment_id=creative.experiment_id,
        creative_id=creative.creative_id,
        artifact_id=artifact.artifact_id,
        job_id=job.job_id,
        job_attempt_id=job.lease_attempt_id,
        required_capability="android.share.handoff",
        provider="ANDROID_SHARE",
        target_account_id=None,
        business_parameters=params_canonical,
        business_parameters_digest=params_digest,
        request_digest=request_digest,
        artifact_sha256=artifact.sha256,
        requested_at=now,
        created_at=now,
        contract_version=1,
        status="PREPARED",
        lease_owner=job.lease_owner,
        lease_generation=job.lease_generation,
        lease_attempt_id=job.lease_attempt_id,
    )
    effect = EffectLedger(
        effect_id=effect_id,
        effect_key=f"ANDROID_SHARE:{ANDROID_TARGET}:{contract_id}",
        action_contract_id=contract_id,
        operation=ANDROID_TARGET,
        provider="ANDROID_SHARE",
        state="PREPARED",
        request_digest=request_digest,
        artifact_sha256=artifact.sha256,
        current_attempt=0,
        reconciliation_required=False,
        created_at=now,
        updated_at=now,
    )
    delivery = DeliveryEffect(
        delivery_id=str(uuid4()),
        action_contract_id=contract_id,
        effect_id=effect_id,
        artifact_id=artifact.artifact_id,
        creative_id=creative.creative_id,
        artifact_sha256=artifact.sha256,
        target=ANDROID_TARGET,
        provider="ANDROID_SHARE",
        target_account_id=None,
        state="PREPARED",
        created_at=now,
        updated_at=now,
    )
    session.add_all((contract, effect, delivery))
    session.flush()
    _validate_delivery_binding(session, delivery)
    return delivery


def record_android_handoff(
    session: Session,
    *,
    delivery_id: str,
    artifact_sha256: str,
    observed_at: datetime,
):
    """Record system-observed Android intent start; never claim TikTok publication."""
    observed = _aware(observed_at)
    if observed > utcnow() + timedelta(minutes=5):
        raise ValueError("future handoff observation is not accepted")
    delivery = session.scalar(select(DeliveryEffect).where(
        DeliveryEffect.delivery_id == delivery_id).with_for_update())
    if delivery is None:
        raise KeyError(delivery_id)
    if delivery.target != ANDROID_TARGET or delivery.provider != "ANDROID_SHARE":
        raise ValueError("delivery is not an Android share handoff")
    _contract, effect, _artifact, _creative = _validate_delivery_binding(session, delivery)
    if artifact_sha256 != delivery.artifact_sha256:
        raise ValueError("Android-observed bytes do not match the frozen artifact hash")
    if delivery.state not in {"PREPARED", "HANDOFF_INITIATED"}:
        raise ValueError(f"handoff cannot be recorded from delivery state {delivery.state}")
    payload = {
        "deliveryId": delivery.delivery_id,
        "effectId": delivery.effect_id,
        "artifactId": delivery.artifact_id,
        "creativeId": delivery.creative_id,
        "artifactSha256": delivery.artifact_sha256,
        "target": delivery.target,
        "state": "HANDOFF_INITIATED",
        "observedAt": observed.isoformat(),
    }
    evidence = record_effect_evidence(
        session,
        effect_id=effect.effect_id,
        evidence_type="SYSTEM_OBSERVED_HANDOFF",
        source="ANDROID_SHARE_HANDOFF",
        source_reference=f"delivery://{delivery.delivery_id}",
        observed_at=observed,
        payload=payload,
        classification="SYSTEM_OBSERVED",
    )
    delivery.state = "HANDOFF_INITIATED"
    delivery.updated_at = utcnow()
    session.flush()
    return delivery, evidence


def record_owner_publication_report(
    session: Session,
    *,
    delivery_id: str,
    publication_identity: str,
    observed_at: datetime,
):
    """Store owner-reported TikTok identity separately; it never confirms provider truth."""
    observed = _aware(observed_at)
    if not publication_identity or len(publication_identity) > 1000:
        raise ValueError("publication identity is required")
    delivery = session.get(DeliveryEffect, delivery_id)
    if delivery is None:
        raise KeyError(delivery_id)
    _contract, effect, _artifact, _creative = _validate_delivery_binding(session, delivery)
    evidence = record_effect_evidence(
        session,
        effect_id=effect.effect_id,
        evidence_type="OWNER_REPORTED_PUBLICATION",
        source="OWNER_TIKTOK_UI",
        source_reference=publication_identity,
        observed_at=observed,
        payload={
            "deliveryId": delivery.delivery_id,
            "effectId": delivery.effect_id,
            "publicationIdentity": publication_identity,
            "classification": "OWNER_REPORTED",
        },
        classification="OWNER_REPORTED",
    )
    return evidence


def delivery_summary(delivery: DeliveryEffect) -> dict:
    return {
        "deliveryId": delivery.delivery_id,
        "actionContractId": delivery.action_contract_id,
        "effectId": delivery.effect_id,
        "artifactId": delivery.artifact_id,
        "creativeId": delivery.creative_id,
        "artifactSha256": delivery.artifact_sha256,
        "target": delivery.target,
        "provider": delivery.provider,
        "targetAccountId": delivery.target_account_id,
        "state": delivery.state,
        "providerReference": delivery.provider_reference,
        "publicPostId": delivery.public_post_id,
        "createdAt": delivery.created_at.isoformat(),
        "updatedAt": delivery.updated_at.isoformat(),
        "confirmedAt": delivery.confirmed_at.isoformat() if delivery.confirmed_at else None,
    }
