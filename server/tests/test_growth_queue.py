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
from server.media_storage import RailwayVolumeMediaStore
from server.growth_models import GrowthMediaArtifact


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


def test_render_jobs_are_not_claimed_without_durable_storage(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    now = utcnow()
    with Session(engine) as session:
        job = GrowthJob(job_id="needs-volume", creative_id=creative_id, job_type="RENDER_VIDEO",
            idempotency_key="needs-volume", state="PENDING", attempts=0,
            available_at=now, created_at=now, updated_at=now)
        session.add(job)
        session.commit()
        assert claim_due_job(session, "worker-without-volume", media_storage_available=False) is None
        assert session.get(GrowthJob, job.job_id).state == "PENDING"


def test_worker_advances_real_render_and_stops_at_action_required(tmp_path):
    engine, creative_id = queue_db(tmp_path)
    with Session(engine) as session:
        creative = session.get(GrowthCreative, creative_id)
        trend = session.get(TrendSignal, creative.trend_id)
        creative.plan_json = canonical_plan(build_creative_plan(TrendCandidate(
            topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
            evidence=trend.evidence, metrics={}), "curiosidades"))
        creative.state = "ASSETS_PENDING"
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
        media_store = RailwayVolumeMediaStore(tmp_path / "media-volume", max_artifact_bytes=64 * 1024 * 1024,
                                              max_total_bytes=128 * 1024 * 1024)
        assert finish_internal_job(session, render_job, media_store=media_store) == "SUCCEEDED"
        session.refresh(creative)
        session.refresh(control)
        artifact = session.scalar(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.creative_id == creative_id))
        assert artifact is not None
        assert artifact.storage_state == "STORED_VERIFIED"
        assert artifact.sha256 == creative.media_hash
        assert media_store.verify_object(artifact.object_key, expected_sha256=artifact.sha256,
            expected_size_bytes=artifact.size_bytes).path.is_file()
        assert creative.state == ("READY" if artifact.quality_status == "QUALITY_PASS" else "BLOCKED")
        assert creative.media_hash and len(creative.media_hash) == 64
        assert creative.quality_status in {"QUALITY_PASS", "QUALITY_REVIEW"}
        assert creative.creative_learning_eligible is False
        assert creative.style_baseline_eligible is False
        assert control.mode == "ACTION_REQUIRED"
        assert session.scalar(select(PublicationIntent.publication_intent_id)) is None
        assert claim_due_job(session, "worker-test") is None


def test_restart_reconciles_same_artifact_without_rerender(tmp_path, monkeypatch):
    from server.growth_models import GrowthMediaArtifact
    from server.media_storage import RailwayVolumeMediaStore
    import server.growth_worker as worker

    engine, creative_id = queue_db(tmp_path)
    store = RailwayVolumeMediaStore(tmp_path / "persistent-volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    with Session(engine) as session:
        creative = session.get(GrowthCreative, creative_id)
        trend = session.get(TrendSignal, creative.trend_id)
        creative.plan_json = canonical_plan(build_creative_plan(TrendCandidate(
            topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
            evidence=trend.evidence, metrics={}), "curiosidades"))
        creative.state = "ASSETS_PENDING"
        session.get(GrowthControl, "default").mode = "RUNNING"
        render = GrowthJob(job_id="restart-render-job", creative_id=creative_id,
            job_type="RENDER_VIDEO", idempotency_key="restart-render-job", state="RUNNING",
            attempts=1, available_at=utcnow(), lease_owner="old-worker",
            lease_until=utcnow()+timedelta(minutes=1), created_at=utcnow(), updated_at=utcnow())
        session.add(render)
        session.commit()
        assert worker.finish_internal_job(session, render, media_store=store) == "SUCCEEDED"
        artifact = session.scalar(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.render_job_id == render.job_id))
        original_identity = (artifact.artifact_id, artifact.sha256)
        final_path = store.object_path(artifact.object_key)
        preserved_bytes = final_path.read_bytes()
        final_path.unlink()
        stage_dir = store.staging_directory(artifact.staging_key)
        (stage_dir / "growth.mp4").write_bytes(preserved_bytes)
        artifact.storage_state = "STORED_UNVERIFIED"
        render.state = "RUNNING"
        render.attempts = 2
        creative.state = "RENDERING"
        session.get(GrowthControl, "default").mode = "RUNNING"
        session.commit()

        def forbidden_rerender(*args, **kwargs):
            raise AssertionError("restart recovery must not re-render")
        monkeypatch.setattr(worker, "render_growth_plan", forbidden_rerender)
        assert worker.finish_internal_job(session, render, media_store=store) == "SUCCEEDED"
        session.refresh(artifact)
        assert (artifact.artifact_id, artifact.sha256) == original_identity
        assert artifact.storage_state == "STORED_VERIFIED"
        restored = store.verify_object(artifact.object_key, expected_sha256=artifact.sha256,
                                       expected_size_bytes=artifact.size_bytes)
        assert restored.path.read_bytes() == preserved_bytes
