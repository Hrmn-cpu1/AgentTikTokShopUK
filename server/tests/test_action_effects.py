from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.action_effect_models import ActionContract, EffectAttempt, EffectEvidence, EffectLedger, EffectOutbox
from server.action_effects import (ActionContractConflict, ReconciliationRequired,
    acknowledge_outbox, claim_outbox, create_action_intent, mark_effect_unknown_before_provider_io,
    record_effect_evidence, request_effect_retry)
from server.growth_models import (GrowthControl, GrowthCreative, GrowthMediaArtifact,
    NicheHypothesis, TrendSignal)
from server.growth_queue_models import GrowthJob, utcnow
from server.growth_worker import LeaseLostError, _capture_lease
from server.media_storage import RailwayVolumeMediaStore, artifact_object_key
from server.models import Base


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
