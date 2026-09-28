from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from server.growth_models import GrowthCreative, NicheHypothesis, TrendSignal
from server.growth_queue_models import GrowthJob
from server.growth_worker import claim_due_job, enqueue_job

def test_queue_idempotency_and_claim():
    import os
    from sqlalchemy import create_engine
    postgres_engine = create_engine(os.environ["DATABASE_URL"])
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    with Session(postgres_engine) as s:
        niche = NicheHypothesis(niche_id="n-"+suffix, market="BR", language="pt-BR",
            hypothesis="ci", trend_evidence="ci:evidence", production_cost_centavos=0,
            risk="LOW", status="EXPLORING", created_at=now)
        trend = TrendSignal(trend_id="t-"+suffix, source="CI_FAKE", source_ref="ci://trend/"+suffix,
            topic="ci topic", market="BR", language="pt-BR", metrics_json="{}",
            evidence="fixture", observed_at=now)
        s.add_all([niche, trend]); s.flush()
        creative = GrowthCreative(creative_id="c-"+suffix, niche_id=niche.niche_id,
            trend_id=trend.trend_id, experiment_id="e-"+suffix, plan_json="{}",
            evidence_ref=trend.source_ref, state="SCRIPTED", created_at=now)
        s.add(creative); s.commit()
        first = enqueue_job(s, creative.creative_id, "PREPARE_ASSETS")
        s.commit()
        second = enqueue_job(s, creative.creative_id, "PREPARE_ASSETS")
        assert first.job_id == second.job_id
        claimed = claim_due_job(s, "ci-worker")
        assert claimed.job_id == first.job_id
        assert claimed.state == "RUNNING"
        assert claimed.attempts == 1
        assert claimed.lease_owner == "ci-worker"


def test_expired_running_job_is_reclaimed(postgres_engine):
    from datetime import timedelta
    from server.growth_queue_models import GrowthJob, utcnow
    from server.growth_worker import claim_due_job
    from sqlalchemy.orm import Session
    from uuid import uuid4
    now = utcnow()
    with Session(postgres_engine) as session:
        creative_id = session.execute(__import__("sqlalchemy").text("select creative_id from growth_creatives limit 1")).scalar_one()
        job = GrowthJob(job_id=str(uuid4()), creative_id=creative_id, job_type="RECOVER_TEST",
            idempotency_key=str(uuid4()), state="RUNNING", attempts=1, available_at=now-timedelta(minutes=1),
            lease_owner="dead-worker", lease_until=now-timedelta(seconds=1), created_at=now, updated_at=now)
        session.add(job); session.commit()
        claimed = claim_due_job(session, "replacement-worker")
        assert claimed.job_id == job.job_id
        assert claimed.state == "RUNNING"
        assert claimed.lease_owner == "replacement-worker"
        assert claimed.attempts == 2
