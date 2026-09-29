from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.action_effect_models import ActionContract, EffectAttempt, EffectEvidence, EffectLedger, EffectOutbox
from server.action_effects import (ActionContractConflict, ReconciliationRequired,
    acknowledge_outbox, claim_outbox, create_action_intent, mark_effect_unknown_before_provider_io,
    record_effect_evidence, record_fenced_provider_evidence, request_effect_retry)
from server.growth_models import (GrowthControl, GrowthCreative, GrowthMediaArtifact,
    NicheHypothesis, TrendSignal)
from server.growth_queue_models import GrowthJob, utcnow
from server.growth_worker import LeaseLostError, _capture_lease
from server.media_storage import RailwayVolumeMediaStore, artifact_object_key
from server.models import Base
from server.provider_lab import (DeterministicProviderLab, ObservationScenario,
    ProviderCapabilities, SendScenario, SimulatedProcessCrash, dispatch_provider_lab,
    reconcile_provider_lab)


def action_db(tmp_path, name="actions"):
    engine = create_engine(f"sqlite:///{tmp_path / (name + '.db')}")
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:10]
    now = utcnow()
    store = RailwayVolumeMediaStore(tmp_path / (name + "-volume"),
        max_artifact_bytes=1024 * 1024, max_total_bytes=4 * 1024 * 1024)
    store.preflight()
    content = (b"validated-local-test-mp4" * 32)
    import hashlib
    digest = hashlib.sha256(content).hexdigest()
    niche_id, trend_id = "n-" + suffix, "t-" + suffix
    creative_id, job_id, artifact_id = "c-" + suffix, "j-" + suffix, str(uuid4())
    key = artifact_object_key(creative_id, digest)
    path = store.object_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    job_attempt = str(uuid4())
    with Session(engine) as session:
        session.add(GrowthControl(control_id="default", mode="READY", updated_at=now))
        session.add(NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR",
            hypothesis="local test", trend_evidence="test:evidence", production_cost_centavos=0,
            risk="LOW", status="EXPLORING", created_at=now))
        session.add(TrendSignal(trend_id=trend_id, source="LOCAL_TEST", source_ref=f"local://{suffix}",
            topic="test", market="BR", language="pt-BR", metrics_json="{}", evidence="LOCAL_TEST",
            observed_at=now))
        session.add(GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=trend_id,
            experiment_id="e-" + suffix, plan_json="{}", evidence_ref=f"local://{suffix}",
            state="READY", media_ref=key, media_hash=digest, quality_status="QUALITY_PASS",
            quality_json='{"status":"QUALITY_PASS"}', created_at=now))
        session.flush()
        session.add(GrowthJob(job_id=job_id, creative_id=creative_id, job_type="PREPARE_ASSETS",
            idempotency_key="job:" + suffix, state="RUNNING", attempts=1, available_at=now,
            lease_owner="job-worker-a", lease_until=now + timedelta(minutes=2),
            lease_acquired_at=now, heartbeat_at=now, lease_generation=1,
            lease_attempt_id=job_attempt, revision=1, created_at=now, updated_at=now))
        session.add(GrowthMediaArtifact(artifact_id=artifact_id, creative_id=creative_id,
            experiment_id="e-" + suffix, render_job_id=job_id, source_render_attempt="try-1-local",
            storage_provider="RAILWAY_VOLUME", object_key=key, staging_key=".staging/local-test/try-1",
            content_type="video/mp4", size_bytes=len(content), sha256=digest, duration_ms=1000,
            width=540, height=960, codec="h264_aac", quality_status="QUALITY_PASS",
            quality_manifest='{"qualityGate":{"status":"QUALITY_PASS"}}', storage_state="STORED_VERIFIED",
            created_at=now, stored_at=now, verified_at=now))
        session.commit()
    return engine, store, {"suffix": suffix, "creative_id": creative_id, "experiment_id": "e-" + suffix,
        "job_id": job_id, "artifact_id": artifact_id, "attempt_id": job_attempt, "sha256": digest}


def make_intent(session, store, ids, *, key="logical-action-1", parameters=None, **kwargs):
    job = session.get(GrowthJob, ids["job_id"])
    return create_action_intent(session, identity=_capture_lease(job), idempotency_key=key,
        action_type="LOCAL_TEST", market="BR", experiment_id=ids["experiment_id"],
        creative_id=ids["creative_id"], artifact_id=ids["artifact_id"],
        required_capability="internal.test", provider="INTERNAL_TEST_STUB",
        business_parameters=parameters or {"purpose": "exercise transactional outbox"},
        media_store=store, **kwargs)


def make_provider_lab_intent(session, store, ids, *, key="provider-lab-action-1", parameters=None):
    job = session.get(GrowthJob, ids["job_id"])
    return create_action_intent(session, identity=_capture_lease(job), idempotency_key=key,
        action_type="PROVIDER_LAB_TEST", market="BR", experiment_id=ids["experiment_id"],
        creative_id=ids["creative_id"], artifact_id=ids["artifact_id"],
        required_capability="provider.lab.test", provider="PROVIDER_LAB",
        business_parameters=parameters or {"case": "deterministic provider simulator"},
        media_store=store)


def test_contract_effect_and_outbox_commit_atomically_with_immutable_digest(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        first = make_intent(session, store, ids)
        session.commit()
        again = make_intent(session, store, ids)
        assert again.duplicate
        assert (again.action_contract_id, again.effect_id, again.outbox_id) == (
            first.action_contract_id, first.effect_id, first.outbox_id)
        with pytest.raises(ActionContractConflict):
            make_intent(session, store, ids, parameters={"purpose": "materially changed"})
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 1
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 1
        assert session.scalar(select(func.count(EffectOutbox.outbox_id))) == 1
        contract = session.get(ActionContract, first.action_contract_id)
        assert contract.artifact_sha256 == ids["sha256"]
        assert contract.job_attempt_id == ids["attempt_id"]
        contract.business_parameters = '{"purpose":"tampered"}'
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("fault_after", ["contract", "effect", "outbox"])
def test_fault_injection_rolls_back_every_partial_intent(tmp_path, fault_after):
    engine, store, ids = action_db(tmp_path, name="fault-" + fault_after)
    with pytest.raises(RuntimeError, match="injected fault"):
        with Session(engine) as session:
            with session.begin():
                make_intent(session, store, ids, key="fault-action", fault_after=fault_after)
    with Session(engine) as session:
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 0
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 0
        assert session.scalar(select(func.count(EffectOutbox.outbox_id))) == 0


def test_no_current_lease_no_contract_and_artifact_must_be_verified(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        job = session.get(GrowthJob, ids["job_id"])
        identity = _capture_lease(job)
        job.lease_until = utcnow() - timedelta(seconds=1)
        session.commit()
        with pytest.raises(LeaseLostError):
            create_action_intent(session, identity=identity, idempotency_key="expired",
                action_type="LOCAL_TEST", market="BR", experiment_id=ids["experiment_id"],
                creative_id=ids["creative_id"], artifact_id=ids["artifact_id"],
                required_capability="internal.test", provider="INTERNAL_TEST_STUB",
                business_parameters={}, media_store=store)
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 0


def test_stale_job_cannot_create_new_intent_but_can_read_same_idempotent_identity(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        original = make_intent(session, store, ids, key="stable-before-lease-loss")
        session.commit()
        job = session.get(GrowthJob, ids["job_id"])
        job.lease_until = utcnow() - timedelta(seconds=1)
        session.commit()
        duplicate = make_intent(session, store, ids, key="stable-before-lease-loss")
        assert duplicate.duplicate
        assert duplicate.effect_id == original.effect_id
        with pytest.raises(LeaseLostError):
            make_intent(session, store, ids, key="new-after-lease-loss")
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 1
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 1
        assert session.scalar(select(func.count(EffectOutbox.outbox_id))) == 1


def test_secret_fields_are_rejected_and_contract_binds_media_readback(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="sensitive field"):
            make_intent(session, store, ids, parameters={"access_token": "must-not-persist"})
        path = store.object_path("media/" + ids["creative_id"] + "/" + ids["sha256"] + ".mp4")
        path.write_bytes(b"changed bytes")
        with pytest.raises(Exception):
            make_intent(session, store, ids, key="bad-readback")
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 0


def test_provider_effect_types_are_denied_in_foundation_phase(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="only admits LOCAL_TEST"):
            create_action_intent(session, identity=_capture_lease(session.get(GrowthJob, ids["job_id"])),
                idempotency_key="no-real-provider", action_type="TIKTOK_DIRECT_POST", market="BR",
                experiment_id=ids["experiment_id"], creative_id=ids["creative_id"],
                artifact_id=ids["artifact_id"], required_capability="video.publish", provider="TIKTOK",
                business_parameters={"purpose": "must remain blocked"}, media_store=store)
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 0
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 0
        assert session.scalar(select(func.count(EffectOutbox.outbox_id))) == 0


def test_outbox_claim_fence_stale_ack_and_internal_ack_is_not_effect_confirmation(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        action = make_intent(session, store, ids)
        session.commit()
        first = claim_outbox(session, "outbox-worker-a")
        assert first is not None and first.generation == 1
        session.commit()
        first_attempt = session.get(EffectAttempt, first.attempt_id)
        assert first_attempt.job_worker_id == "job-worker-a"
        assert first_attempt.job_lease_generation == 1
        assert first_attempt.outbox_worker_id == "outbox-worker-a"
        assert first_attempt.outbox_lease_generation == 1
        session.execute(update(EffectOutbox).where(EffectOutbox.outbox_id == first.outbox_id)
            .values(lease_until=utcnow() - timedelta(seconds=1)),
            execution_options={"synchronize_session": False})
        session.commit()
        second = claim_outbox(session, "outbox-worker-b")
        assert second is not None and second.generation == 2
        assert second.attempt_id != first.attempt_id
        session.commit()
        assert not acknowledge_outbox(session, first)
        session.rollback()
        assert acknowledge_outbox(session, second)
        session.commit()
        assert session.get(EffectOutbox, action.outbox_id).state == "ACKED"
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "PREPARED"
        assert effect.confirmed_at is None
        assert session.scalar(select(func.count(EffectAttempt.attempt_id))) == 2


def test_unknown_requires_reconciliation_and_never_creates_retry_effect(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        action = make_intent(session, store, ids)
        session.commit()
        lease = claim_outbox(session, "internal-boundary-test")
        session.commit()
        mark_effect_unknown_before_provider_io(session, lease)
        session.commit()
        assert request_effect_retry(session, action.effect_id) == "RECONCILIATION_REQUIRED"
        session.commit()
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "RECONCILIATION_REQUIRED"
        assert effect.reconciliation_required
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 1
        assert session.scalar(select(func.count(EffectOutbox.outbox_id))) == 1
        assert acknowledge_outbox(session, lease)
        session.commit()
        assert session.get(EffectLedger, action.effect_id).state == "RECONCILIATION_REQUIRED"


def test_unknown_outbox_is_not_reclaimed_after_lease_expiry(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        make_intent(session, store, ids)
        session.commit()
        lease = claim_outbox(session, "unknown-boundary")
        session.commit()
        mark_effect_unknown_before_provider_io(session, lease)
        session.commit()
        session.execute(update(EffectOutbox).where(EffectOutbox.outbox_id == lease.outbox_id)
            .values(lease_until=utcnow() - timedelta(seconds=1)),
            execution_options={"synchronize_session": False})
        session.commit()
        assert claim_outbox(session, "must-not-blindly-retry") is None
        effect = session.get(EffectLedger, lease.effect_id)
        assert effect.state == "UNKNOWN" and effect.reconciliation_required


def test_evidence_is_durable_and_does_not_promote_effect_state(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        action = make_intent(session, store, ids)
        session.commit()
        evidence = record_effect_evidence(session, effect_id=action.effect_id,
            evidence_type="INTERNAL_AUDIT", source="LOCAL_TEST", source_reference="local://audit",
            observed_at=utcnow(), payload={"outboxState": "PENDING"}, classification="SYSTEM_OBSERVED")
        same = record_effect_evidence(session, effect_id=action.effect_id,
            evidence_type="INTERNAL_AUDIT", source="LOCAL_TEST", source_reference="local://audit",
            observed_at=utcnow(), payload={"outboxState": "PENDING"}, classification="SYSTEM_OBSERVED")
        assert evidence.evidence_id == same.evidence_id
        session.commit()
        session.expire_all()
        assert session.scalar(select(func.count(EffectEvidence.evidence_id))) == 1
        assert session.get(EffectLedger, action.effect_id).state == "PREPARED"


def test_intent_and_unacked_outbox_survive_engine_restart(tmp_path):
    engine, store, ids = action_db(tmp_path)
    with Session(engine) as session:
        action = make_intent(session, store, ids)
        session.commit()
    url = str(engine.url)
    engine.dispose()
    restarted = create_engine(url)
    with Session(restarted) as session:
        contract = session.get(ActionContract, action.action_contract_id)
        effect = session.get(EffectLedger, action.effect_id)
        outbox = session.get(EffectOutbox, action.outbox_id)
        assert contract and effect and outbox
        assert outbox.state == "PENDING"
        assert effect.state == "PREPARED"


def _prepare_lab_dispatch(engine, store, ids, provider=None, key="provider-lab-action"):
    provider = provider or DeterministicProviderLab()
    with Session(engine) as session:
        action = make_provider_lab_intent(session, store, ids, key=key)
        session.commit()
        lease = claim_outbox(session, "provider-lab-worker")
        assert lease and lease.effect_id == action.effect_id
        session.commit()
    return action, lease, provider


def test_provider_lab_ack_is_not_confirmation_and_observation_atomically_confirms(tmp_path):
    engine, store, ids = action_db(tmp_path, name="provider-ack")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        response = dispatch_provider_lab(session, lease, lab, SendScenario.SUCCESS_ACK)
        assert response and response.result_class == "PROVIDER_ACKNOWLEDGED"
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert session.get(EffectLedger, action.effect_id).confirmed_at is None
        assert session.get(EffectOutbox, action.outbox_id).state == "ACKED"
        assert session.get(EffectAttempt, lease.attempt_id).result_class == "PROVIDER_ACKNOWLEDGED"
        session.commit()
        assert reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH) == "CONFIRMED"
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "CONFIRMED" and not effect.reconciliation_required
        assert effect.confirmation_evidence_id
        evidence = session.get(EffectEvidence, effect.confirmation_evidence_id)
        assert evidence and evidence.effect_id == action.effect_id
        assert evidence.classification == "RECONCILIATION_RESULT"
        assert evidence.source == "PROVIDER_LAB"
        session.commit()
    url = str(engine.url)
    engine.dispose()
    restarted = create_engine(url)
    with Session(restarted) as session:
        persisted = session.get(EffectLedger, action.effect_id)
        assert persisted.state == "CONFIRMED"
        assert session.get(EffectEvidence, persisted.confirmation_evidence_id)


def test_provider_lab_material_contract_change_mints_a_distinct_action_and_effect(tmp_path):
    engine, store, ids = action_db(tmp_path, name="material-contract-change")
    with Session(engine) as session:
        first = make_provider_lab_intent(session, store, ids, key="contract-v1",
            parameters={"case": "v1"})
        second = make_provider_lab_intent(session, store, ids, key="contract-v2",
            parameters={"case": "v2"})
        assert first.request_digest != second.request_digest
        assert first.action_contract_id != second.action_contract_id
        assert first.effect_id != second.effect_id
        assert first.outbox_id != second.outbox_id


def test_provider_lab_lost_response_unknown_then_reconciles_one_original_effect(tmp_path):
    engine, store, ids = action_db(tmp_path, name="lost-response")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        response = dispatch_provider_lab(session, lease, lab, SendScenario.TIMEOUT_AFTER_ACCEPT)
        assert response and response.ambiguous and response.accepted
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "UNKNOWN" and effect.reconciliation_required
        assert session.get(EffectOutbox, action.outbox_id).state == "ACKED"
        assert len(lab.records) == 1
        assert claim_outbox(session, "blind-retry-must-not-claim") is None
        assert request_effect_retry(session, action.effect_id) == "RECONCILIATION_REQUIRED"
        session.commit()
    url = str(engine.url)
    engine.dispose()
    restarted = create_engine(url)
    with Session(restarted) as session:
        assert session.get(EffectLedger, action.effect_id).state == "RECONCILIATION_REQUIRED"
        assert reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH) == "CONFIRMED"
        session.commit()
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "CONFIRMED" and effect.confirmation_evidence_id
        assert len(lab.records) == 1


@pytest.mark.parametrize(("send_case", "expected_state"), [
    (SendScenario.TIMEOUT_BEFORE_ACCEPT, "FAILED_BEFORE_EFFECT"),
    (SendScenario.PROVIDER_REJECT, "REJECTED"),
    (SendScenario.TEMPORARY_5XX_BEFORE_SEND, "FAILED_BEFORE_EFFECT"),
    (SendScenario.RATE_LIMIT, "FAILED_BEFORE_EFFECT"),
    (SendScenario.TIMEOUT_AFTER_ACCEPT, "UNKNOWN"),
    (SendScenario.CONNECTION_DROP_AFTER_SEND, "UNKNOWN"),
    (SendScenario.TEMPORARY_5XX_AFTER_SEND, "UNKNOWN"),
    (SendScenario.MALFORMED_RESPONSE, "UNKNOWN"),
    (SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY, "UNKNOWN"),
])
def test_provider_lab_response_classes_are_conservative_and_deterministic(tmp_path, send_case, expected_state):
    engine, store, ids = action_db(tmp_path, name="send-" + send_case.value.lower())
    caps = ProviderCapabilities(supports_idempotency=False) if send_case == SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY else None
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids, provider=DeterministicProviderLab(caps))
    with Session(engine) as session:
        response = dispatch_provider_lab(session, lease, lab, send_case)
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == expected_state
        if expected_state == "UNKNOWN":
            assert effect.reconciliation_required
            assert session.get(EffectOutbox, action.outbox_id).state == "ACKED"
        if send_case == SendScenario.PROVIDER_REJECT:
            assert response.result_class == "PROVIDER_REJECTED"
        if send_case == SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY:
            assert not lab.capabilities.supports_idempotency
            assert len(lab.records) == 1
            assert claim_outbox(session, "duplicate-dispatch") is None
            assert len(lab.records) == 1
        session.commit()


def test_provider_lab_rate_limit_retries_same_action_identity_only_with_positive_no_effect(tmp_path):
    engine, store, ids = action_db(tmp_path, name="safe-rate-limit")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        dispatch_provider_lab(session, lease, lab, SendScenario.RATE_LIMIT,
                              retry_delay_override=timedelta(0), retry_authorized=True)
        effect = session.get(EffectLedger, action.effect_id)
        outbox = session.get(EffectOutbox, action.outbox_id)
        assert effect.state == "PREPARED" and not effect.reconciliation_required
        assert outbox.state == "PENDING"
        assert session.scalar(select(func.count(EffectLedger.effect_id))) == 1
        assert session.scalar(select(func.count(ActionContract.action_contract_id))) == 1
        next_lease = claim_outbox(session, "fresh-rate-limit-retry")
        assert next_lease and next_lease.effect_id == action.effect_id
        assert next_lease.outbox_id == action.outbox_id
        session.commit()
        dispatch_provider_lab(session, next_lease, lab, SendScenario.SUCCESS_ACK)
        assert len(lab.records) == 1
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert session.scalar(select(func.count(EffectAttempt.attempt_id)).where(
            EffectAttempt.effect_id == action.effect_id)) == 2
        session.commit()

    unsafe_engine, unsafe_store, unsafe_ids = action_db(tmp_path, name="unsafe-rate-limit")
    no_retry = ProviderCapabilities(supports_safe_retry_before_effect=False)
    blocked, blocked_lease, blocked_lab = _prepare_lab_dispatch(unsafe_engine, unsafe_store, unsafe_ids,
        provider=DeterministicProviderLab(no_retry))
    with Session(unsafe_engine) as session:
        dispatch_provider_lab(session, blocked_lease, blocked_lab, SendScenario.RATE_LIMIT,
                              retry_delay_override=timedelta(0), retry_authorized=True)
        assert session.get(EffectLedger, blocked.effect_id).state == "FAILED_BEFORE_EFFECT"
        assert claim_outbox(session, "unsafe-retry") is None


@pytest.mark.parametrize(("observation", "expected"), [
    (ObservationScenario.UNAVAILABLE, "OBSERVATION_UNAVAILABLE"),
    (ObservationScenario.ZERO_MATCHES, "ZERO_MATCHES"),
    (ObservationScenario.MULTIPLE_MATCHES, "MULTIPLE_MATCHES"),
    (ObservationScenario.MISMATCH, "MISMATCH"),
    (ObservationScenario.REFERENCE_MISMATCH, "MISMATCH"),
])
def test_provider_lab_observations_without_one_exact_match_never_confirm(tmp_path, observation, expected):
    engine, store, ids = action_db(tmp_path, name="observe-" + observation.value.lower())
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        dispatch_provider_lab(session, lease, lab, SendScenario.SUCCESS_ACK)
        result = reconcile_provider_lab(session, action.effect_id, lab, observation)
        assert result == expected
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "RECONCILIATION_REQUIRED"
        assert effect.reconciliation_required
        assert effect.confirmation_evidence_id is None
        assert effect.confirmed_at is None
        assert session.scalar(select(func.count(EffectEvidence.evidence_id)).where(
            EffectEvidence.effect_id == action.effect_id)) == 1
        session.commit()


def test_provider_lab_ack_reference_mismatch_is_not_confirmed(tmp_path):
    engine, store, ids = action_db(tmp_path, name="ack-ref-mismatch")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        dispatch_provider_lab(session, lease, lab, SendScenario.PROVIDER_REFERENCE_MISMATCH)
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        result = reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH)
        assert result == "MISMATCH"
        assert session.get(EffectLedger, action.effect_id).state == "RECONCILIATION_REQUIRED"


def test_provider_lab_duplicate_delivery_is_idempotent_or_blocked_by_our_outbox(tmp_path):
    engine, store, ids = action_db(tmp_path, name="duplicate-idempotency")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        response = dispatch_provider_lab(session, lease, lab,
            SendScenario.DUPLICATE_REQUEST_WITH_IDEMPOTENCY)
        assert response.accepted and lab.capabilities.supports_idempotency
        assert len(lab.records) == 1
        assert lab.records[0].unique_marker.startswith("PROVIDER_LAB:PROVIDER_LAB_TEST:")
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert claim_outbox(session, "duplicate-idempotent-dispatch") is None

    unsafe_engine, unsafe_store, unsafe_ids = action_db(tmp_path, name="duplicate-no-idempotency")
    no_idem_lab = DeterministicProviderLab(ProviderCapabilities(supports_idempotency=False))
    one, one_lease, no_idem_lab = _prepare_lab_dispatch(unsafe_engine, unsafe_store, unsafe_ids,
        provider=no_idem_lab)
    with Session(unsafe_engine) as session:
        repeated = make_provider_lab_intent(session, unsafe_store, unsafe_ids,
            key="provider-lab-action")
        assert repeated.duplicate
        assert (repeated.effect_id, repeated.outbox_id) == (one.effect_id, one.outbox_id)
        dispatch_provider_lab(session, one_lease, no_idem_lab,
            SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY)
        assert len(no_idem_lab.records) == 1
        assert claim_outbox(session, "must-not-send-without-idempotency") is None
        assert no_idem_lab.send_calls == 1 and len(no_idem_lab.records) == 1


@pytest.mark.parametrize("crash_at", [
    "AFTER_UNKNOWN_COMMIT", "IMMEDIATELY_BEFORE_SEND", "AFTER_PROVIDER_ACCEPT",
    "BEFORE_RESPONSE_PERSISTENCE",
])
def test_provider_lab_crashes_leave_recoverable_unknown_without_duplicate_send(tmp_path, crash_at):
    engine, store, ids = action_db(tmp_path, name="crash-" + crash_at.lower())
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        with pytest.raises(SimulatedProcessCrash):
            dispatch_provider_lab(session, lease, lab, SendScenario.SUCCESS_ACK, crash_at=crash_at)
        effect = session.get(EffectLedger, action.effect_id)
        if crash_at == "AFTER_UNKNOWN_COMMIT":
            assert effect.state == "UNKNOWN"
        if crash_at in {"IMMEDIATELY_BEFORE_SEND", "AFTER_PROVIDER_ACCEPT", "BEFORE_RESPONSE_PERSISTENCE"}:
            assert effect.state == "UNKNOWN" and effect.reconciliation_required
        assert len(lab.records) == (0 if crash_at in {"AFTER_UNKNOWN_COMMIT", "IMMEDIATELY_BEFORE_SEND"} else 1)
        session.commit()
    # Restart the database connection at each recoverable crash stage.
    url = str(engine.url)
    engine.dispose()
    engine = create_engine(url)
    with Session(engine) as session:
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        # After lease expiry the queue recovery only ACKs internal work. It never sends.
        session.execute(update(EffectOutbox).where(EffectOutbox.outbox_id == action.outbox_id)
            .values(lease_until=utcnow() - timedelta(seconds=1)),
            execution_options={"synchronize_session": False})
        session.commit()
        from server.action_effects import recover_unknown_outbox_ack
        if crash_at != "BEFORE_PROVIDER_BOUNDARY":
            assert recover_unknown_outbox_ack(session, action.outbox_id) is True
            session.commit()
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert len(lab.records) <= 1
        assert claim_outbox(session, "crash-recovery-must-not-resend") is None


def test_provider_lab_crash_before_boundary_leaves_prepared_and_stale_worker_is_fenced(tmp_path):
    engine, store, ids = action_db(tmp_path, name="crash-before-boundary")
    action, first, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        with pytest.raises(SimulatedProcessCrash):
            dispatch_provider_lab(session, first, lab, SendScenario.SUCCESS_ACK,
                                  crash_at="BEFORE_PROVIDER_BOUNDARY")
        assert session.get(EffectLedger, action.effect_id).state == "PREPARED"
        assert not lab.records
        session.execute(update(EffectOutbox).where(EffectOutbox.outbox_id == action.outbox_id)
            .values(lease_until=utcnow() - timedelta(seconds=1)),
            execution_options={"synchronize_session": False})
        session.commit()
        second = claim_outbox(session, "replacement-worker")
        assert second and second.generation == first.generation + 1
        session.commit()
        with pytest.raises(LeaseLostError):
            mark_effect_unknown_before_provider_io(session, first)
        session.rollback()
        with pytest.raises(LeaseLostError):
            record_fenced_provider_evidence(session, first, evidence_type="STALE_PROVIDER_WRITE",
                source="PROVIDER_LAB", source_reference="plab://stale",
                observed_at=utcnow(), payload={"effectId": action.effect_id})
        session.rollback()
        assert acknowledge_outbox(session, first) is False
        session.rollback()
        assert session.get(EffectLedger, action.effect_id).state == "PREPARED"
        assert session.scalar(select(func.count(EffectEvidence.evidence_id)).where(
            EffectEvidence.effect_id == action.effect_id)) == 0
        assert not lab.records


def test_provider_lab_reconciliation_crash_rolls_back_evidence_then_resumes(tmp_path):
    engine, store, ids = action_db(tmp_path, name="reconcile-crash")
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids)
    with Session(engine) as session:
        dispatch_provider_lab(session, lease, lab, SendScenario.TIMEOUT_AFTER_ACCEPT)
        with pytest.raises(SimulatedProcessCrash):
            reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH,
                                   crash_before_evidence=True)
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert session.scalar(select(func.count(EffectEvidence.evidence_id)).where(
            EffectEvidence.effect_id == action.effect_id)) == 0
        with pytest.raises(SimulatedProcessCrash):
            reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH,
                                   fault_after_evidence=True)
        session.commit()  # the nested transaction rolled back evidence and confirmation together
        assert session.get(EffectLedger, action.effect_id).state == "UNKNOWN"
        assert session.scalar(select(func.count(EffectEvidence.evidence_id)).where(
            EffectEvidence.effect_id == action.effect_id)) == 0
        assert reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH) == "CONFIRMED"
        session.commit()
        assert len(lab.records) == 1
        assert session.get(EffectLedger, action.effect_id).confirmation_evidence_id


def test_provider_lab_missing_observation_capability_stays_unknown_and_action_required(tmp_path):
    engine, store, ids = action_db(tmp_path, name="no-observation")
    no_observation = ProviderCapabilities(supports_idempotency=False,
        supports_status_lookup=False, supports_observation=False,
        supports_provider_reference=False, supports_safe_retry_before_effect=False)
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids,
        provider=DeterministicProviderLab(no_observation))
    with Session(engine) as session:
        dispatch_provider_lab(session, lease, lab, SendScenario.TIMEOUT_AFTER_ACCEPT)
        result = reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH)
        assert result == "OBSERVATION_UNAVAILABLE"
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.state == "RECONCILIATION_REQUIRED"
        assert effect.confirmation_evidence_id is None
        assert effect.reconciliation_required


def test_provider_lab_without_reference_uses_exact_observation_match_without_inventing_reference(tmp_path):
    engine, store, ids = action_db(tmp_path, name="no-provider-reference")
    capabilities = ProviderCapabilities(supports_provider_reference=False)
    action, lease, lab = _prepare_lab_dispatch(engine, store, ids,
        provider=DeterministicProviderLab(capabilities))
    with Session(engine) as session:
        response = dispatch_provider_lab(session, lease, lab, SendScenario.SUCCESS_ACK)
        assert response.provider_reference is None
        assert session.get(EffectLedger, action.effect_id).provider_reference is None
        assert reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH) == "CONFIRMED"
        effect = session.get(EffectLedger, action.effect_id)
        assert effect.provider_reference is None
        evidence = session.get(EffectEvidence, effect.confirmation_evidence_id)
        assert evidence.source_reference == f"provider-lab://effect/{action.effect_id}"


# Delivery gateway regression tests reuse the authoritative action_db fixture so
# media, lease and hash invariants stay identical to the Effect Ledger tests.
from pathlib import Path

from server.delivery_gateway import prepare_android_handoff_from_render, record_android_handoff


def test_android_handoff_delivery_is_frozen_under_render_lease_and_records_evidence(tmp_path):
    engine, _store, ids = action_db(tmp_path, name="delivery-handoff")
    with Session(engine) as session:
        creative = session.get(GrowthCreative, ids["creative_id"])
        artifact = session.get(GrowthMediaArtifact, ids["artifact_id"])
        job = session.get(GrowthJob, ids["job_id"])
        delivery = prepare_android_handoff_from_render(
            session, job=job, creative=creative, artifact=artifact)
        session.commit()
        first_id = delivery.delivery_id

    with Session(engine) as session:
        creative = session.get(GrowthCreative, ids["creative_id"])
        artifact = session.get(GrowthMediaArtifact, ids["artifact_id"])
        job = session.get(GrowthJob, ids["job_id"])
        duplicate = prepare_android_handoff_from_render(
            session, job=job, creative=creative, artifact=artifact)
        assert duplicate.delivery_id == first_id
        assert duplicate.action_contract_id
        assert duplicate.effect_id
        delivery, evidence = record_android_handoff(
            session, delivery_id=first_id, artifact_sha256=ids["sha256"], observed_at=utcnow())
        session.commit()
        assert delivery.state == "HANDOFF_INITIATED"
        assert evidence.classification == "SYSTEM_OBSERVED"
        assert evidence.evidence_type == "SYSTEM_OBSERVED_HANDOFF"
        assert session.get(EffectLedger, delivery.effect_id).state == "PREPARED"


def test_android_handoff_rejects_hash_and_quality_mismatch(tmp_path):
    engine, _store, ids = action_db(tmp_path, name="delivery-reject")
    with Session(engine) as session:
        creative = session.get(GrowthCreative, ids["creative_id"])
        artifact = session.get(GrowthMediaArtifact, ids["artifact_id"])
        job = session.get(GrowthJob, ids["job_id"])
        delivery = prepare_android_handoff_from_render(
            session, job=job, creative=creative, artifact=artifact)
        session.commit()
        with pytest.raises(ValueError, match="observed bytes"):
            record_android_handoff(
                session, delivery_id=delivery.delivery_id, artifact_sha256="0" * 64,
                observed_at=utcnow())
        session.rollback()
        artifact = session.get(GrowthMediaArtifact, ids["artifact_id"])
        artifact.quality_status = "QUALITY_REVIEW"
        session.flush()
        with pytest.raises(ValueError, match="verified quality artifact"):
            prepare_android_handoff_from_render(
                session, job=session.get(GrowthJob, ids["job_id"]),
                creative=session.get(GrowthCreative, ids["creative_id"]), artifact=artifact)


def test_android_fileprovider_is_confined_to_dedicated_share_cache():
    root = Path(__file__).resolve().parents[2]
    xml = (root / "android/app/src/main/res/xml/file_paths.xml").read_text(encoding="utf-8")
    java = (root / "android/app/src/main/java/com/tiktokshopprofitagent/app/TikTokSharePlugin.java").read_text(
        encoding="utf-8")
    assert "<external-path" not in xml
    assert 'path="."' not in xml
    assert '<cache-path name="tiktok_share_cache" path="share/" />' in xml
    assert 'new File(getContext().getCacheDir(), "share")' in java
    assert 'new File(shareDir, "agent-tiktok-share.mp4")' in java
    assert 'MessageDigest.getInstance("SHA-256")' in java
    assert "FLAG_GRANT_READ_URI_PERMISSION" in java
    assert "FLAG_GRANT_WRITE_URI_PERMISSION" not in java
