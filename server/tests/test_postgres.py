import os
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from server.api import create_app
from server.models import TikTokConnection
from server.growth_models import GrowthCreative, GrowthControl, GrowthMediaArtifact, NicheHypothesis, TrendSignal
from server.growth_queue_models import GrowthJob, utcnow
from server.growth_worker import claim_due_job, finish_internal_job, _capture_lease, renew_lease, LeaseLostError

TOKEN = "ci-only-operator-token-longer-than-32-characters"
POSTGRES_URL = os.environ.get("DATABASE_URL", "")


@pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql+psycopg://"), reason="PostgreSQL URL not configured")
def test_live_postgres_constraints_restart_and_decimal():
    url = POSTGRES_URL
    engine = create_engine(url)
    assert "commerce_events" in inspect(engine).get_table_names()
    current = datetime.now(timezone.utc)
    with Session(engine) as session:
        record = session.get(TikTokConnection, "ci-account")
        if record is None:
            session.add(TikTokConnection(connection_id="ci-account",operator_id="primary",
                provider_user_id="CI-FAKE-NO-REAL-ACCOUNT",granted_scopes="user.info.basic",status="ACTIVE",
                connected_at=current,last_validated_at=current,access_expires_at=current+timedelta(days=1),
                refresh_expires_at=current+timedelta(days=365),manual_verified_at=current,
                manual_uk_evidence_ref="ci:market:uk",manual_affiliate_evidence_ref="ci:affiliate:status"))
            session.commit()
    suffix = uuid4().hex[:12]
    eid = f"EXP-PG-{suffix}"
    c = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    timestamp = datetime.now(timezone.utc).isoformat()
    assert c.post('/v1/capital-authority',json={'authority_id':f'capital-{suffix}',
        'available_capital_gbp':'10.00','capital_limit_gbp':'8.00','loss_limit_gbp':'5.00',
        'minimum_allocation_score':60,'evidence_ref':f'ci:capital:{suffix}'}).status_code==200
    assert c.post('/v1/products',json={'product_id':f'product-{suffix}','listing_ref':f'ci:listing:{suffix}',
        'evidence_ref':f'ci:product:{suffix}','observed_at':timestamp}).status_code==200
    assert c.post('/v1/opportunities',json={'opportunity_id':f'opportunity-{suffix}',
        'product_id':f'product-{suffix}','capital_required_gbp':'3.00','maximum_loss_gbp':'2.00',
        'allocation_score':70,'evidence_ref':f'ci:opportunity:{suffix}','observed_at':timestamp}).status_code==200
    payload = {"experiment_id": eid, "decision_id": f"DEC-{suffix}", "product_id": "p1", "creative_id": "c1",
               "publication_action_id": f"publish-{eid}", "authority_evidence_ref": "ci:manual:authority",
               "opportunity_id":f'opportunity-{suffix}'}
    payload['product_id']=f'product-{suffix}'
    payload['creative_id']=f'creative-{suffix}'
    assert c.post("/v1/experiments", json=payload).status_code == 200
    assert c.post('/v1/product-claims',json={'claim_id':f'claim-{suffix}','product_id':payload['product_id'],
        'text':'Operator observed feature','state':'SUPPORTED','evidence_ref':f'ci:claim:{suffix}'}).status_code==200
    assert c.post('/v1/creatives',json={'creative_id':payload['creative_id'],'experiment_id':eid,
        'content':'Manual video concept','claim_ids':[f'claim-{suffix}'],
        'evidence_ref':f'ci:creative:{suffix}'}).status_code==200
    assert c.post('/v1/creative-approvals',json={'approval_id':f'approval-{suffix}',
        'experiment_id':eid,'creative_id':payload['creative_id'],
        'evidence_ref':f'ci:approval:{suffix}'}).status_code==200
    assert c.post('/v1/launch-intents',json={'packet_id':f'packet-{suffix}',
        'experiment_id':eid,'approval_id':f'approval-{suffix}'}).status_code==200

    def post_event(kind, ext, amount=None, parent=None):
        return c.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-{ext}", "event_type": kind,
             "parent_external_event_id":f"{suffix}-{parent}" if parent else None,
             "amount_gbp": amount, "evidence_ref": f"ci:evidence:{ext}", "occurred_at": timestamp})

    assert post_event("PUBLISHED", "video").status_code == 200
    assert post_event("ORDER_CREATED", "order",parent='video').status_code == 200
    assert post_event("DELIVERED", "delivery",parent='order').status_code == 200
    assert post_event("COMMISSION_SETTLED", "settlement", "1.99",parent='order').status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": eid, "amount_gbp": "0.99", "evidence_ref": "ci:observed:cost"}).status_code == 200
    assert c.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "1.00"
    recovered = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    assert recovered.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-settlement", "event_type": "COMMISSION_SETTLED",
             "parent_external_event_id":f"{suffix}-order","amount_gbp": "1.99", "evidence_ref": "ci:evidence:settlement", "occurred_at": timestamp}).json()["duplicate"] is True
    assert post_event("REFUNDED", "refund", "0.01",parent='settlement').status_code == 200
    assert recovered.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "0.99"


@pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql+psycopg://"), reason="PostgreSQL URL not configured")
def test_postgres_growth_queue_concurrent_claim_and_fencing():
    """Two independent PostgreSQL sessions prove single ownership and stale-writer rejection."""
    from sqlalchemy import delete, update

    engine = create_engine(POSTGRES_URL, pool_size=5)
    suffix = uuid4().hex[:12]
    now = utcnow()
    niche_id, trend_id = f"n-pg-{suffix}", f"t-pg-{suffix}"
    creative_id, job_id = f"c-pg-{suffix}", f"j-pg-{suffix}"
    previous_control_mode = None
    control_existed = False
    with Session(engine) as session:
        control = session.get(GrowthControl, "default")
        control_existed = control is not None
        previous_control_mode = control.mode if control else None
        if control is None:
            session.add(GrowthControl(control_id="default", mode="READY", updated_at=now))
        else:
            control.mode = "READY"
        session.add_all([
            NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR", hypothesis="CI lease probe",
                trend_evidence="ci:lease", production_cost_centavos=0, risk="LOW", status="EXPLORING", created_at=now),
            TrendSignal(trend_id=trend_id, source="CI", source_ref=f"ci://{suffix}", topic="lease probe",
                market="BR", language="pt-BR", metrics_json="{}", evidence="CI-only", observed_at=now),
        ])
        session.flush()
        session.add(GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=trend_id,
            experiment_id=f"e-pg-{suffix}", plan_json="{}", evidence_ref=f"ci://{suffix}",
            state="SCRIPTED", created_at=now))
        session.add(GrowthJob(job_id=job_id, creative_id=creative_id, job_type="PREPARE_ASSETS",
            idempotency_key=f"ci-lease:{suffix}", state="PENDING", attempts=0,
            available_at=now, created_at=now, updated_at=now))
        session.commit()

    barrier = threading.Barrier(2)
    def contender(worker_id):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            claimed = claim_due_job(session, worker_id, specific_job_id=job_id)
            return _capture_lease(claimed) if claimed else None

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            identities = list(pool.map(contender, (f"pg-worker-a-{suffix}", f"pg-worker-b-{suffix}")))
        winners = [identity for identity in identities if identity]
        assert len(winners) == 1
        old_identity = winners[0]
        with Session(engine) as session:
            session.execute(update(GrowthJob).where(GrowthJob.job_id == job_id)
                .values(lease_until=utcnow()-timedelta(seconds=1)))
            session.commit()
            replacement = claim_due_job(session, f"pg-replacement-{suffix}", specific_job_id=job_id)
            assert replacement and replacement.lease_generation == old_identity.generation + 1
            assert replacement.lease_owner != old_identity.owner

        with Session(engine) as stale_session:
            assert renew_lease(stale_session, old_identity) is False
            stale_session.rollback()
            stale_job = stale_session.get(GrowthJob, job_id)
            with pytest.raises(LeaseLostError):
                finish_internal_job(stale_session, stale_job, lease_identity=old_identity)
            stale_session.rollback()
        with Session(engine) as verify:
            current = verify.get(GrowthJob, job_id)
            assert current.state == "RUNNING"
            assert current.lease_owner == replacement.lease_owner
            assert current.lease_generation == old_identity.generation + 1
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(GrowthJob).where(GrowthJob.job_id == job_id))
            cleanup.execute(delete(GrowthCreative).where(GrowthCreative.creative_id == creative_id))
            cleanup.execute(delete(TrendSignal).where(TrendSignal.trend_id == trend_id))
            cleanup.execute(delete(NicheHypothesis).where(NicheHypothesis.niche_id == niche_id))
            control = cleanup.get(GrowthControl, "default")
            if control_existed and control is not None:
                control.mode = previous_control_mode
            elif not control_existed and control is not None:
                cleanup.delete(control)
            cleanup.commit()
        engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql+psycopg://"), reason="PostgreSQL URL not configured")
def test_postgres_action_effect_outbox_atomicity_idempotency_and_fencing(tmp_path):
    """Independent PostgreSQL sessions prove durable identity and one fenced claim."""
    import hashlib
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import delete, func, select, update
    from sqlalchemy.exc import IntegrityError

    from server.action_effect_models import ActionContract, EffectAttempt, EffectLedger, EffectOutbox
    from server.action_effects import acknowledge_outbox, claim_outbox, create_action_intent
    from server.growth_worker import LeaseIdentity
    from server.media_storage import RailwayVolumeMediaStore, artifact_object_key

    engine = create_engine(POSTGRES_URL, pool_size=8)
    suffix = uuid4().hex[:12]
    now = utcnow()
    niche_id, trend_id = f"n-action-pg-{suffix}", f"t-action-pg-{suffix}"
    creative_id, job_id, artifact_id = f"c-action-pg-{suffix}", f"j-action-pg-{suffix}", str(uuid4())
    experiment_id, job_attempt_id = f"e-action-pg-{suffix}", str(uuid4())
    worker_id = f"action-worker-{suffix}"
    payload = b"postgres-only internal action fixture" * 100
    sha256 = hashlib.sha256(payload).hexdigest()
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=1024 * 1024,
                                    max_total_bytes=4 * 1024 * 1024)
    store.preflight()
    object_key = artifact_object_key(creative_id, sha256)
    object_path = store.object_path(object_key)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(payload)

    with Session(engine) as session:
        control = session.get(GrowthControl, "default")
        control_existed = control is not None
        previous_control_mode = control.mode if control else None
        if control is None:
            session.add(GrowthControl(control_id="default", mode="READY", updated_at=now))
        else:
            control.mode = "READY"
        session.add(NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR",
            hypothesis="PostgreSQL action fixture", trend_evidence=f"ci:{suffix}",
            production_cost_centavos=0, risk="LOW", status="EXPLORING", created_at=now))
        session.add(TrendSignal(trend_id=trend_id, source="CI", source_ref=f"ci://{suffix}",
            topic="action outbox", market="BR", language="pt-BR", metrics_json="{}",
            evidence="CI-only", observed_at=now))
        session.flush()
        session.add(GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=trend_id,
            experiment_id=experiment_id, plan_json="{}", evidence_ref=f"ci://{suffix}",
            state="READY", media_ref=object_key, media_hash=sha256, quality_status="QUALITY_PASS",
            quality_json='{"status":"QUALITY_PASS"}', created_at=now))
        session.flush()
        session.add(GrowthJob(job_id=job_id, creative_id=creative_id, job_type="PREPARE_ASSETS",
            idempotency_key=f"action-ci:{suffix}", state="RUNNING", attempts=1, available_at=now,
            lease_owner=worker_id, lease_until=now + timedelta(minutes=2), lease_acquired_at=now,
            heartbeat_at=now, lease_generation=1, lease_attempt_id=job_attempt_id,
            revision=1, created_at=now, updated_at=now))
        session.flush()
        session.add(GrowthMediaArtifact(artifact_id=artifact_id, creative_id=creative_id,
            experiment_id=experiment_id, render_job_id=job_id, source_render_attempt="try-1-ci",
            storage_provider="RAILWAY_VOLUME", object_key=object_key, staging_key=f".staging/ci/{suffix}",
            content_type="video/mp4", size_bytes=len(payload), sha256=sha256, duration_ms=1000,
            width=540, height=960, codec="h264_aac", quality_status="QUALITY_PASS",
            quality_manifest='{"qualityGate":{"status":"QUALITY_PASS"}}', storage_state="STORED_VERIFIED",
            created_at=now, stored_at=now, verified_at=now))
        session.commit()

    original_lease = LeaseIdentity(job_id, worker_id, 1, job_attempt_id)
    for fault_after in ("contract", "effect"):
        key = f"fault-{fault_after}:{suffix}"
        with pytest.raises(RuntimeError, match="injected fault"):
            with Session(engine) as session:
                with session.begin():
                    create_action_intent(session, identity=original_lease, idempotency_key=key,
                        action_type="LOCAL_TEST", market="BR", experiment_id=experiment_id,
                        creative_id=creative_id, artifact_id=artifact_id, required_capability="internal.test",
                        provider="INTERNAL_TEST_STUB", business_parameters={"case": "postgres-rollback"},
                        media_store=store, fault_after=fault_after)
        with Session(engine) as session:
            assert session.scalar(select(func.count(ActionContract.action_contract_id))
                .where(ActionContract.idempotency_key == key)) == 0

    barrier = threading.Barrier(2)
    def prepare_same_action(worker_label):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            intent = create_action_intent(session, identity=original_lease, idempotency_key=f"same-action:{suffix}",
                action_type="LOCAL_TEST", market="BR", experiment_id=experiment_id,
                creative_id=creative_id, artifact_id=artifact_id, required_capability="internal.test",
                provider="INTERNAL_TEST_STUB", business_parameters={"case": "concurrent-idempotency"},
                media_store=store)
            session.commit()
            return intent

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            intents = list(pool.map(prepare_same_action, ("writer-a", "writer-b")))
        assert intents[0].action_contract_id == intents[1].action_contract_id
        assert intents[0].effect_id == intents[1].effect_id
        assert intents[0].outbox_id == intents[1].outbox_id
        assert sorted((intents[0].duplicate, intents[1].duplicate)) == [False, True]
        with Session(engine) as session:
            assert session.scalar(select(func.count(ActionContract.action_contract_id))
                .where(ActionContract.idempotency_key == f"same-action:{suffix}")) == 1
            assert session.scalar(select(func.count(EffectLedger.effect_id))
                .where(EffectLedger.action_contract_id == intents[0].action_contract_id)) == 1
            assert session.scalar(select(func.count(EffectOutbox.outbox_id))
                .where(EffectOutbox.action_contract_id == intents[0].action_contract_id)) == 1
            contract = session.get(ActionContract, intents[0].action_contract_id)
            contract.business_parameters = '{"case":"tampered"}'
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        claim_barrier = threading.Barrier(2)
        def claim(worker):
            with Session(engine) as session:
                claim_barrier.wait(timeout=10)
                lease = claim_outbox(session, worker)
                if lease:
                    session.commit()
                else:
                    session.rollback()
                return lease
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, (f"dispatcher-a-{suffix}", f"dispatcher-b-{suffix}")))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        first = winners[0]
        with Session(engine) as session:
            session.execute(update(EffectOutbox).where(EffectOutbox.outbox_id == first.outbox_id)
                .values(lease_until=utcnow() - timedelta(seconds=1)))
            session.commit()
            recovered = claim_outbox(session, f"dispatcher-recovery-{suffix}")
            assert recovered and recovered.generation == first.generation + 1
            session.commit()
        with Session(engine) as session:
            assert acknowledge_outbox(session, first) is False
            session.rollback()
            assert acknowledge_outbox(session, recovered) is True
            session.commit()
            effect = session.get(EffectLedger, recovered.effect_id)
            row = session.get(EffectOutbox, recovered.outbox_id)
            assert row.state == "ACKED"
            assert effect.state == "PREPARED" and effect.confirmed_at is None
            assert session.scalar(select(func.count(EffectAttempt.attempt_id))
                .where(EffectAttempt.effect_id == recovered.effect_id)) == 2

        # A fresh SQLAlchemy engine is a process/restart boundary: committed intent and ACK survive.
        engine.dispose()


        restarted = create_engine(POSTGRES_URL)
        with Session(restarted) as session:
            assert session.get(ActionContract, intents[0].action_contract_id) is not None
            assert session.get(EffectLedger, intents[0].effect_id).state == "PREPARED"
            assert session.get(EffectOutbox, intents[0].outbox_id).state == "ACKED"
        restarted.dispose()

        with Session(engine) as session:
            job = session.get(GrowthJob, job_id)
            job.lease_until = utcnow() - timedelta(seconds=1)
            session.commit()
            replacement = claim_due_job(session, f"action-replacement-{suffix}", specific_job_id=job_id)
            assert replacement and replacement.lease_generation == 2
            session.commit()
        with Session(engine) as session:
            with pytest.raises(LeaseLostError):
                create_action_intent(session, identity=original_lease,
                    idempotency_key=f"stale-action:{suffix}", action_type="LOCAL_TEST", market="BR",
                    experiment_id=experiment_id, creative_id=creative_id, artifact_id=artifact_id,
                    required_capability="internal.test", provider="INTERNAL_TEST_STUB",
                    business_parameters={"case": "stale-worker"}, media_store=store)
            session.rollback()
            assert session.scalar(select(func.count(ActionContract.action_contract_id))
                .where(ActionContract.job_id == job_id)) == 1
    finally:
        with Session(engine) as cleanup:
            # Child rows are explicitly deleted in dependency order for shared CI databases.
            contract_ids = select(ActionContract.action_contract_id).where(
                ActionContract.idempotency_key == f"same-action:{suffix}")
            outbox_ids = select(EffectOutbox.outbox_id).where(EffectOutbox.action_contract_id.in_(contract_ids))
            cleanup.execute(delete(EffectAttempt).where(EffectAttempt.outbox_id.in_(outbox_ids)))
            cleanup.execute(delete(EffectOutbox).where(EffectOutbox.action_contract_id.in_(contract_ids)))
            cleanup.execute(delete(EffectLedger).where(EffectLedger.action_contract_id.in_(contract_ids)))
            cleanup.execute(delete(ActionContract).where(ActionContract.idempotency_key == f"same-action:{suffix}"))
            cleanup.execute(delete(GrowthMediaArtifact).where(GrowthMediaArtifact.artifact_id == artifact_id))
            cleanup.execute(delete(GrowthJob).where(GrowthJob.job_id == job_id))
            cleanup.execute(delete(GrowthCreative).where(GrowthCreative.creative_id == creative_id))
            cleanup.execute(delete(TrendSignal).where(TrendSignal.trend_id == trend_id))
            cleanup.execute(delete(NicheHypothesis).where(NicheHypothesis.niche_id == niche_id))
            control = cleanup.get(GrowthControl, "default")
            if control_existed and control is not None:
                control.mode = previous_control_mode
            elif not control_existed and control is not None:
                cleanup.delete(control)
            cleanup.commit()
        engine.dispose()

@pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql+psycopg://"), reason="PostgreSQL URL not configured")
def test_postgres_provider_lab_lost_response_restart_atomic_reconciliation_and_stale_fence(tmp_path):
    """Real PostgreSQL proves UNKNOWN/evidence durability and atomic confirmation."""
    import hashlib

    from sqlalchemy import delete, func, select, update
    from server.action_effect_models import ActionContract, EffectAttempt, EffectEvidence, EffectLedger, EffectOutbox
    from server.action_effects import (claim_outbox, create_action_intent,
        record_fenced_provider_evidence)
    from server.growth_worker import LeaseIdentity, _capture_lease
    from server.media_storage import RailwayVolumeMediaStore, artifact_object_key
    from server.provider_lab import (DeterministicProviderLab, ObservationScenario,
        SendScenario, SimulatedProcessCrash, dispatch_provider_lab, reconcile_provider_lab)

    engine = create_engine(POSTGRES_URL, pool_size=5)
    suffix = uuid4().hex[:12]
    now = utcnow()
    niche_id, trend_id = f"n-plab-{suffix}", f"t-plab-{suffix}"
    creative_id, job_id, artifact_id = f"c-plab-{suffix}", f"j-plab-{suffix}", str(uuid4())
    experiment_id, job_attempt_id = f"e-plab-{suffix}", str(uuid4())
    worker_id = f"provider-lab-job-{suffix}"
    payload = b"postgres provider lab stable media fixture" * 100
    sha256 = hashlib.sha256(payload).hexdigest()
    store = RailwayVolumeMediaStore(tmp_path / "provider-lab-volume", max_artifact_bytes=1024 * 1024,
                                    max_total_bytes=4 * 1024 * 1024)
    store.preflight()
    object_key = artifact_object_key(creative_id, sha256)
    object_path = store.object_path(object_key)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(payload)
    idempotency_key = f"provider-lab:{suffix}"

    with Session(engine) as session:
        session.add(NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR",
            hypothesis="PostgreSQL Provider Lab", trend_evidence=f"ci:plab:{suffix}",
            production_cost_centavos=0, risk="LOW", status="EXPLORING", created_at=now))
        session.add(TrendSignal(trend_id=trend_id, source="CI", source_ref=f"ci://plab/{suffix}",
            topic="provider lab", market="BR", language="pt-BR", metrics_json="{}",
            evidence="CI-only deterministic provider lab", observed_at=now))
        session.flush()
        session.add(GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=trend_id,
            experiment_id=experiment_id, plan_json="{}", evidence_ref=f"ci://plab/{suffix}",
            state="READY", media_ref=object_key, media_hash=sha256, quality_status="QUALITY_PASS",
            quality_json='{"status":"QUALITY_PASS"}', created_at=now))
        session.flush()
        session.add(GrowthJob(job_id=job_id, creative_id=creative_id, job_type="PREPARE_ASSETS",
            idempotency_key=f"plab-job:{suffix}", state="RUNNING", attempts=1, available_at=now,
            lease_owner=worker_id, lease_until=now + timedelta(minutes=2), lease_acquired_at=now,
            heartbeat_at=now, lease_generation=1, lease_attempt_id=job_attempt_id,
            revision=1, created_at=now, updated_at=now))
        session.flush()
        session.add(GrowthMediaArtifact(artifact_id=artifact_id, creative_id=creative_id,
            experiment_id=experiment_id, render_job_id=job_id, source_render_attempt="try-1-plab",
            storage_provider="RAILWAY_VOLUME", object_key=object_key, staging_key=f".staging/plab/{suffix}",
            content_type="video/mp4", size_bytes=len(payload), sha256=sha256, duration_ms=1000,
            width=540, height=960, codec="h264_aac", quality_status="QUALITY_PASS",
            quality_manifest='{"qualityGate":{"status":"QUALITY_PASS"}}', storage_state="STORED_VERIFIED",
            created_at=now, stored_at=now, verified_at=now))
        session.commit()

    action = None
    lab = DeterministicProviderLab()
    try:
        original_job_lease = LeaseIdentity(job_id, worker_id, 1, job_attempt_id)
        with Session(engine) as session:
            action = create_action_intent(session, identity=original_job_lease,
                idempotency_key=idempotency_key, action_type="PROVIDER_LAB_TEST", market="BR",
                experiment_id=experiment_id, creative_id=creative_id, artifact_id=artifact_id,
                required_capability="provider.lab.test", provider="PROVIDER_LAB",
                business_parameters={"case": "postgres lost response"}, media_store=store)
            duplicate = create_action_intent(session, identity=original_job_lease,
                idempotency_key=idempotency_key, action_type="PROVIDER_LAB_TEST", market="BR",
                experiment_id=experiment_id, creative_id=creative_id, artifact_id=artifact_id,
                required_capability="provider.lab.test", provider="PROVIDER_LAB",
                business_parameters={"case": "postgres lost response"}, media_store=store)
            assert duplicate.duplicate
            assert (duplicate.effect_id, duplicate.outbox_id) == (action.effect_id, action.outbox_id)
            session.commit()
            lease = claim_outbox(session, f"plab-dispatch-{suffix}")
            assert lease and lease.effect_id == action.effect_id
            session.commit()
            result = dispatch_provider_lab(session, lease, lab, SendScenario.TIMEOUT_AFTER_ACCEPT)
            assert result and result.ambiguous and result.accepted
            assert len(lab.records) == 1
            session.commit()

        # Engine replacement is a PostgreSQL process/restart boundary.
        engine.dispose()
        engine = create_engine(POSTGRES_URL, pool_size=5)
        with Session(engine) as session:
            effect = session.get(EffectLedger, action.effect_id)
            outbox = session.get(EffectOutbox, action.outbox_id)
            assert effect.state == "UNKNOWN" and effect.reconciliation_required
            assert outbox.state == "ACKED"
            assert session.scalar(select(func.count(EffectAttempt.attempt_id)).where(
                EffectAttempt.effect_id == action.effect_id)) == 1
            assert session.scalar(select(func.count(ActionContract.action_contract_id)).where(
                ActionContract.idempotency_key == idempotency_key)) == 1
            assert claim_outbox(session, f"plab-blind-retry-{suffix}") is None
            session.rollback()

        # Evidence insert then injected crash is rolled back to UNKNOWN in PG.
        with Session(engine) as session:
            with pytest.raises(SimulatedProcessCrash):
                reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH,
                                       fault_after_evidence=True)
            session.commit()
            effect = session.get(EffectLedger, action.effect_id)
            assert effect.state == "UNKNOWN" and effect.confirmation_evidence_id is None
            assert session.scalar(select(func.count(EffectEvidence.evidence_id)).where(
                EffectEvidence.effect_id == action.effect_id)) == 0
            assert reconcile_provider_lab(session, action.effect_id, lab, ObservationScenario.ONE_MATCH) == "CONFIRMED"
            session.commit()
            effect = session.get(EffectLedger, action.effect_id)
            assert effect.state == "CONFIRMED" and effect.confirmation_evidence_id
            evidence = session.get(EffectEvidence, effect.confirmation_evidence_id)
            assert evidence and evidence.effect_id == action.effect_id
            assert evidence.classification == "RECONCILIATION_RESULT"
            assert len(lab.records) == 1
            with pytest.raises(LeaseLostError):
                record_fenced_provider_evidence(session, lease,
                    evidence_type="STALE_ZOMBIE_EVIDENCE", source="PROVIDER_LAB",
                    source_reference="plab://stale", observed_at=utcnow(),
                    payload={"effectId": action.effect_id})
            session.rollback()

        # Confirmation and its evidence reference survive another connection/process restart.
        engine.dispose()
        engine = create_engine(POSTGRES_URL)
        with Session(engine) as session:
            effect = session.get(EffectLedger, action.effect_id)
            assert effect.state == "CONFIRMED"
            assert session.get(EffectEvidence, effect.confirmation_evidence_id) is not None
            assert len(lab.records) == 1
    finally:
        engine.dispose()
        with Session(create_engine(POSTGRES_URL)) as cleanup:
            if action is not None:
                cleanup.execute(update(EffectLedger).where(EffectLedger.effect_id == action.effect_id)
                    .values(confirmation_evidence_id=None))
                cleanup.execute(delete(EffectEvidence).where(EffectEvidence.effect_id == action.effect_id))
                cleanup.execute(delete(EffectAttempt).where(EffectAttempt.effect_id == action.effect_id))
                cleanup.execute(delete(EffectOutbox).where(EffectOutbox.outbox_id == action.outbox_id))
                cleanup.execute(delete(EffectLedger).where(EffectLedger.effect_id == action.effect_id))
                cleanup.execute(delete(ActionContract).where(ActionContract.action_contract_id == action.action_contract_id))
            cleanup.execute(delete(GrowthMediaArtifact).where(GrowthMediaArtifact.artifact_id == artifact_id))
            cleanup.execute(delete(GrowthJob).where(GrowthJob.job_id == job_id))
            cleanup.execute(delete(GrowthCreative).where(GrowthCreative.creative_id == creative_id))
            cleanup.execute(delete(TrendSignal).where(TrendSignal.trend_id == trend_id))
            cleanup.execute(delete(NicheHypothesis).where(NicheHypothesis.niche_id == niche_id))
            cleanup.commit()
