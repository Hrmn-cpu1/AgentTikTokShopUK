from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from server.growth_models import GrowthCreative, NicheHypothesis, TrendSignal
from server.growth_queue_models import GrowthJob
from server.growth_worker import claim_due_job, enqueue_job

def test_queue_idempotency_and_claim(postgres_engine):
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
