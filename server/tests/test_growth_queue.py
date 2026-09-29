from datetime import timedelta
import json
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server.models import Base
from server.growth_models import GrowthControl, GrowthCreative, NicheHypothesis, TrendSignal, PublicationIntent
from server.growth_queue_models import GrowthJob, utcnow
from server.growth_worker import claim_due_job, enqueue_job
from server.growth_worker import finish_internal_job
from server.growth_brain import TrendCandidate, build_creative_plan, canonical_plan


def queue_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:10]
    now = utcnow()
    with Session(engine) as session:
        session.add(GrowthControl(control_id="default", mode="READY", updated_at=now))
        niche = NicheHypothesis(niche_id="n-" + suffix, market="BR", language="pt-BR",
            hypothesis="queue fixture", trend_evidence="fixture:evidence", production_cost_centavos=0,
            risk="LOW", status="EXPLORING", created_at=now)
        trend = TrendSignal(trend_id="t-" + suffix, source="FIXTURE", source_ref="fixture://trend/" + suffix,
            topic="queue test", market="BR", language="pt-BR", metrics_json="{}",
            evidence="fixture", observed_at=now)
        session.add_all([niche, trend])
        session.flush()
        creative = GrowthCreative(creative_id="c-" + suffix, niche_id=niche.niche_id,
            trend_id=trend.trend_id, experiment_id="e-" + suffix, plan_json="{}",
            evidence_ref=trend.source_ref, state="SCRIPTED", created_at=now)
        session.add(creative)
        session.commit()
        return engine, creative.creative_id


def test_queue_idempotency_and_claim(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    with Session(engine) as session:
        first = enqueue_job(session, creative_id, "PREPARE_ASSETS")
        session.commit()
        second = enqueue_job(session, creative_id, "PREPARE_ASSETS")
        assert first.job_id == second.job_id
        claimed = claim_due_job(session, "ci-worker")
        assert claimed.job_id == first.job_id
        assert claimed.state == "RUNNING"
        assert claimed.attempts == 1
        assert claimed.lease_owner == "ci-worker"


def test_expired_running_job_is_reclaimed_after_process_restart(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    now = utcnow()
    with Session(engine) as session:
        job = GrowthJob(job_id="expired-" + uuid4().hex, creative_id=creative_id,
            job_type="RENDER_VIDEO", idempotency_key="expired:" + uuid4().hex,
            state="RUNNING", attempts=1, available_at=now-timedelta(minutes=1),
            lease_owner="dead-worker", lease_until=now-timedelta(seconds=1),
            created_at=now, updated_at=now)
        session.add(job)
        session.commit()
        claimed = claim_due_job(session, "replacement-worker")
        assert claimed.job_id == job.job_id
        assert claimed.state == "RUNNING"
        assert claimed.lease_owner == "replacement-worker"
        assert claimed.attempts == 2


def test_paused_control_prevents_worker_claim(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    with Session(engine) as session:
        session.add(enqueue_job(session, creative_id, "PREPARE_ASSETS"))
        control = session.get(GrowthControl, "default")
        control.mode = "PAUSED"
        session.commit()
        assert claim_due_job(session, "worker") is None
        assert session.scalar(select(GrowthJob.state)) == "PENDING"


def test_worker_advances_real_render_and_stops_at_action_required(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    with Session(engine) as session:
        creative = session.get(GrowthCreative, creative_id)
        trend = session.get(TrendSignal, creative.trend_id)
        creative.plan_json = canonical_plan(build_creative_plan(TrendCandidate(
            topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
            evidence=trend.evidence, metrics={}), "curiosidades"))
        control = session.get(GrowthControl, "default")
        control.mode = "RUNNING"
        first = enqueue_job(session, creative_id, "PREPARE_ASSETS")
        session.commit()

        claimed = claim_due_job(session, "worker-test")
        assert claimed.job_id == first.job_id
        assert finish_internal_job(session, claimed) == "SUCCEEDED"
        render_job = session.scalar(select(GrowthJob).where(GrowthJob.job_type == "RENDER_VIDEO"))
        assert render_job and render_job.state == "PENDING"

        render_job = claim_due_job(session, "worker-test")
        assert render_job and render_job.job_type == "RENDER_VIDEO"
        assert finish_internal_job(session, render_job) == "SUCCEEDED"
        session.refresh(creative)
        session.refresh(control)
        assert creative.state == "READY"
        assert creative.media_hash and len(creative.media_hash) == 64
        assert creative.quality_status in {"QUALITY_PASS", "QUALITY_REVIEW"}
        assert creative.creative_learning_eligible is False
        assert creative.style_baseline_eligible is False
        assert control.mode == "ACTION_REQUIRED"
        assert session.scalar(select(PublicationIntent.publication_intent_id)) is None
        assert claim_due_job(session, "worker-test") is None
