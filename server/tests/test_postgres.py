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
from server.growth_models import GrowthCreative, GrowthControl, NicheHypothesis, TrendSignal
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
