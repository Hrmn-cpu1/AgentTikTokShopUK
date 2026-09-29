from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import json
import hashlib
import pytest
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from server.api import create_app
from server.models import Base
from server.growth_brain import TrendCandidate, build_creative_plan, canonical_plan
from server.growth_models import (GrowthControl, GrowthCreative, GrowthMediaArtifact,
    GrowthStateTransition, NicheHypothesis, PublicationIntent, TrendSignal)
from server.growth_queue_models import GrowthJob, utcnow
from server.growth_worker import claim_due_job, finish_internal_job
from server.media_storage import RailwayVolumeMediaStore
from server.growth_renderer import render_growth_plan


TOKEN = "test-only-operator-secret-32-characters-long"


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'materialization.db'}"
    Base.metadata.create_all(create_engine(url))
    return url


def seed_legacy_ready_creative(database, suffix="materialize"):
    engine = create_engine(database)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        control = session.get(GrowthControl, "default")
        if control is None:
            session.add(GrowthControl(control_id="default", mode="ACTION_REQUIRED", updated_at=now))
        else:
            control.mode = "ACTION_REQUIRED"
            control.updated_at = now
        niche = NicheHypothesis(niche_id=f"niche-{suffix}", market="BR", language="pt-BR",
            hypothesis="legacy creative durable media proof", trend_evidence=f"test:{suffix}:evidence",
            production_cost_centavos=0, risk="LOW", status="EXPLORING", created_at=now)
        trend = TrendSignal(trend_id=f"trend-{suffix}", source="PUBLIC_FIXTURE_RSS",
            source_ref=f"https://example.test/trend/{suffix}", topic="teste de mídia durável",
            market="BR", language="pt-BR", metrics_json="{}", evidence="public fixture signal",
            observed_at=now)
        candidate = TrendCandidate(topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
            evidence=trend.evidence, metrics={})
        creative = GrowthCreative(creative_id=f"creative-{suffix}", niche_id=niche.niche_id,
            trend_id=trend.trend_id, experiment_id=f"experiment-{suffix}",
            plan_json=canonical_plan(build_creative_plan(candidate, "curiosidades")),
            evidence_ref=trend.source_ref, state="READY", purpose="EXPERIMENT",
            quality_status="QUALITY_PASS", quality_json="{}", media_hash="a" * 64,
            created_at=now)
        creative_id = creative.creative_id
        session.add_all([niche, trend, creative])
        session.commit()
    return engine, creative_id


def make_client(database, store):
    return TestClient(create_app(database, TOKEN, media_store=store),
        headers={"Authorization": f"Bearer {TOKEN}"})


def test_materialization_auth_and_double_click_enqueue_one_job(database, tmp_path):
    engine, creative_id = seed_legacy_ready_creative(database, "double")
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    app = create_app(database, TOKEN, media_store=store)
    with TestClient(app) as anonymous:
        assert anonymous.post(f"/v1/growth/creatives/{creative_id}/materialize").status_code == 401
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        first = c.post(f"/v1/growth/creatives/{creative_id}/materialize")
        second = c.post(f"/v1/growth/creatives/{creative_id}/materialize")
        assert first.status_code == second.status_code == 200
        assert first.json()["jobType"] == "MATERIALIZE_DURABLE_MEDIA"
        assert first.json()["jobState"] == "PENDING"
        assert first.json()["duplicate"] is False
        assert second.json()["jobId"] == first.json()["jobId"]
        assert second.json()["duplicate"] is True
        assert second.json()["delivery"] == "UNCHANGED_NOT_CONFIRMED"
    with Session(engine) as session:
        assert session.scalar(select(func.count(GrowthJob.job_id)).where(
            GrowthJob.job_type == "MATERIALIZE_DURABLE_MEDIA")) == 1
        assert session.scalar(select(GrowthMediaArtifact.artifact_id)) is None
        assert session.get(GrowthControl, "default").mode == "ACTION_REQUIRED"
        assert session.scalar(select(PublicationIntent.publication_intent_id)) is None
        assert session.scalar(select(func.count(GrowthStateTransition.transition_id)).where(
            GrowthStateTransition.reason.contains("materialization"))) == 1


def test_retry_while_materialization_is_running_returns_same_job(database, tmp_path):
    engine, creative_id = seed_legacy_ready_creative(database, "running-retry")
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    c = make_client(database, store)
    first = c.post(f"/v1/growth/creatives/{creative_id}/materialize").json()
    with Session(engine) as session:
        job = session.get(GrowthJob, first["jobId"])
        job.state = "RUNNING"
        creative = session.get(GrowthCreative, creative_id)
        creative.state = "RENDERING"
        session.commit()

    retry = c.post(f"/v1/growth/creatives/{creative_id}/materialize")
    assert retry.status_code == 200
    assert retry.json()["jobId"] == first["jobId"]
    assert retry.json()["jobState"] == "RUNNING"
    assert retry.json()["duplicate"] is True
    with Session(engine) as session:
        assert session.scalar(select(func.count(GrowthMediaArtifact.artifact_id))) == 0
        assert session.scalar(select(func.count(GrowthJob.job_id)).where(
            GrowthJob.job_type == "MATERIALIZE_DURABLE_MEDIA")) == 1


def test_materialization_worker_quality_storage_and_repeat_returns_same_bytes(database, tmp_path, monkeypatch):
    import server.growth_worker as worker

    engine, creative_id = seed_legacy_ready_creative(database, "real-render")
    store = RailwayVolumeMediaStore(tmp_path / "persistent-volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    c = make_client(database, store)
    queued = c.post(f"/v1/growth/creatives/{creative_id}/materialize").json()
    with Session(engine) as session:
        claim = claim_due_job(session, "materialize-worker")
        assert claim is not None and claim.job_type == "MATERIALIZE_DURABLE_MEDIA"
        assert claim.job_id == queued["jobId"]
        assert finish_internal_job(session, claim, media_store=store) == "SUCCEEDED"
        artifact = session.scalar(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.creative_id == creative_id))
        assert artifact is not None
        identity = (artifact.artifact_id, artifact.sha256, artifact.size_bytes,
            artifact.object_key, artifact.source_render_attempt)
        assert artifact.quality_status == "QUALITY_PASS"
        assert artifact.storage_state == "STORED_VERIFIED"
        assert artifact.codec == "h264" and artifact.height * 9 == artifact.width * 16
        assert artifact.duration_ms > 0 and artifact.size_bytes > 0
        assert artifact.sha256 == session.get(GrowthCreative, creative_id).media_hash
        assert session.get(GrowthControl, "default").mode == "ACTION_REQUIRED"
        assert session.scalar(select(PublicationIntent.publication_intent_id)) is None
        assert session.scalar(select(func.count(GrowthMediaArtifact.artifact_id))) == 1

    physical_path = store.object_path(identity[3])
    original_bytes = physical_path.read_bytes()
    assert len(original_bytes) == identity[2]
    assert hashlib.sha256(original_bytes).hexdigest() == identity[1]

    def forbidden_rerender(*args, **kwargs):
        raise AssertionError("idempotent materialize/readback must not invoke FFmpeg")
    monkeypatch.setattr(worker, "render_growth_plan", forbidden_rerender)
    second = c.post(f"/v1/growth/creatives/{creative_id}/materialize")
    assert second.status_code == 200
    response = second.json()
    assert response["mediaState"] == "MEDIA_READY"
    assert response["artifactId"] == identity[0]
    assert response["sha256"] == identity[1]
    assert response["sizeBytes"] == identity[2]
    video = c.get(response["videoUrl"])
    assert video.status_code == 200
    assert video.headers["x-media-state"] == "MEDIA_READY"
    assert video.headers["x-media-artifact-id"] == identity[0]
    assert video.headers["x-creative-sha256"] == identity[1]
    assert video.headers["etag"].strip('"') == identity[1]
    assert video.content == original_bytes
    assert hashlib.sha256(video.content).hexdigest() == identity[1]


def test_action_required_claims_only_durable_materialization(database, tmp_path):
    engine, creative_id = seed_legacy_ready_creative(database, "isolated-claim")
    now = utcnow()
    with Session(engine) as session:
        session.add_all([
            GrowthJob(job_id="ordinary-render", creative_id=creative_id, job_type="RENDER_VIDEO",
                idempotency_key="ordinary-render", state="PENDING", attempts=0,
                available_at=now, created_at=now, updated_at=now),
            GrowthJob(job_id="durable-render", creative_id=creative_id, job_type="MATERIALIZE_DURABLE_MEDIA",
                idempotency_key="durable-render", state="PENDING", attempts=0,
                available_at=now, created_at=now, updated_at=now),
        ])
        session.commit()
        claimed = claim_due_job(session, "action-required-worker")
        assert claimed.job_id == "durable-render"
        assert session.get(GrowthJob, "ordinary-render").state == "PENDING"


def test_materialization_requires_volume_ready_creative_and_action_required(database, tmp_path):
    engine, creative_id = seed_legacy_ready_creative(database, "preconditions")
    unconfigured = make_client(database, None)
    assert unconfigured.post(f"/v1/growth/creatives/{creative_id}/materialize").status_code == 503
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    c = make_client(database, store)
    with Session(engine) as session:
        session.get(GrowthControl, "default").mode = "PAUSED"
        session.commit()
    assert c.post(f"/v1/growth/creatives/{creative_id}/materialize").status_code == 409
    with Session(engine) as session:
        session.get(GrowthControl, "default").mode = "ACTION_REQUIRED"
        session.get(GrowthCreative, creative_id).state = "BLOCKED"
        session.commit()
    assert c.post(f"/v1/growth/creatives/{creative_id}/materialize").status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(GrowthJob.job_id)) is None


def test_concurrent_materialization_requests_share_idempotency_key(database, tmp_path):
    engine, creative_id = seed_legacy_ready_creative(database, "concurrent")
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    url = f"/v1/growth/creatives/{creative_id}/materialize"

    def request_once():
        with make_client(database, store) as c:
            return c.post(url)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: request_once(), range(2)))
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    assert responses[0].json()["jobId"] == responses[1].json()["jobId"]
    with Session(engine) as session:
        assert session.scalar(select(func.count(GrowthJob.job_id)).where(
            GrowthJob.job_type == "MATERIALIZE_DURABLE_MEDIA")) == 1
        assert session.scalar(select(func.count(GrowthMediaArtifact.artifact_id))) == 0


@pytest.mark.parametrize("crash_point", [
    "after_ffmpeg_before_artifact_row",
    "after_artifact_row_before_promotion",
    "after_promotion_before_storage_state",
    "after_unverified_before_readback",
    "after_verified_before_cleanup",
])
def test_materialization_crash_recovery_matrix(database, tmp_path, monkeypatch, crash_point):
    import server.growth_worker as worker

    engine, creative_id = seed_legacy_ready_creative(database, "crash-" + crash_point)
    store = RailwayVolumeMediaStore(tmp_path / "volume", max_artifact_bytes=64 * 1024 * 1024,
                                    max_total_bytes=128 * 1024 * 1024)
    now = utcnow()
    with Session(engine) as session:
        creative = session.get(GrowthCreative, creative_id)
        trend = session.get(TrendSignal, creative.trend_id)
        creative.plan_json = canonical_plan(build_creative_plan(TrendCandidate(
            topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
            evidence=trend.evidence, metrics={}), "curiosidades"))
        creative.state = "RENDERING"
        job = GrowthJob(job_id="crash-job-" + crash_point, creative_id=creative_id,
            job_type="MATERIALIZE_DURABLE_MEDIA", idempotency_key=creative_id + ":MATERIALIZE_DURABLE_MEDIA",
            state="RUNNING", attempts=1, available_at=now, lease_owner="crashed-worker",
            lease_until=now-timedelta(seconds=1), lease_acquired_at=now-timedelta(minutes=2),
            heartbeat_at=now-timedelta(minutes=2), lease_generation=1,
            lease_attempt_id=str(uuid4()), created_at=now, updated_at=now)
        session.add(job)
        session.get(GrowthControl, "default").mode = "ACTION_REQUIRED"
        session.commit()

        staging_key = store.staging_key(job.job_id, "try-1-crash-matrix")
        output_dir = store.staging_directory(staging_key)
        output, digest, _cleanup = render_growth_plan(creative.plan_json, output_dir=output_dir)
        manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
        initial_artifact_id = None

        if crash_point != "after_ffmpeg_before_artifact_row":
            artifact = worker._persist_render_artifact(session, job, creative, store,
                staging_key, str(output), digest, manifest)
            initial_artifact_id = artifact.artifact_id
            if crash_point == "after_artifact_row_before_promotion":
                artifact.storage_state = "RENDERED_TEMPORARY"
            elif crash_point == "after_promotion_before_storage_state":
                artifact.storage_state = "STORING"
                session.commit()
                store.promote_staging(object_key=artifact.object_key, staging_key=staging_key,
                    expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes)
                artifact.storage_state = "STORING"
            elif crash_point == "after_unverified_before_readback":
                artifact.storage_state = "STORED_UNVERIFIED"
                session.commit()
                store.promote_staging(object_key=artifact.object_key, staging_key=staging_key,
                    expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes)
                artifact.storage_state = "STORED_UNVERIFIED"
            elif crash_point == "after_verified_before_cleanup":
                artifact.storage_state = "STORED_VERIFIED"
                session.commit()
                store.promote_staging(object_key=artifact.object_key, staging_key=staging_key,
                    expected_sha256=artifact.sha256, expected_size_bytes=artifact.size_bytes)
                artifact.storage_state = "STORED_VERIFIED"
            session.commit()

    def forbidden_rerender(*args, **kwargs):
        raise AssertionError(f"crash recovery at {crash_point} must not rerender")
        monkeypatch.setattr(worker, "render_growth_plan", forbidden_rerender)
        with Session(engine) as session:
            job = claim_due_job(session, "recovery-worker")
            assert job and job.job_id == "crash-job-" + crash_point and job.lease_generation == 2
            assert finish_internal_job(session, job, media_store=store) == "SUCCEEDED"
        artifact = session.scalar(select(GrowthMediaArtifact).where(
            GrowthMediaArtifact.creative_id == creative_id))
        assert artifact is not None
        assert artifact.quality_status == "QUALITY_PASS"
        assert artifact.storage_state == "STORED_VERIFIED"
        assert session.scalar(select(func.count(GrowthMediaArtifact.artifact_id)).where(
            GrowthMediaArtifact.creative_id == creative_id)) == 1
        if initial_artifact_id:
            assert artifact.artifact_id == initial_artifact_id
        verified = store.verify_object(artifact.object_key, expected_sha256=artifact.sha256,
            expected_size_bytes=artifact.size_bytes)
        assert hashlib.sha256(verified.path.read_bytes()).hexdigest() == artifact.sha256
        assert artifact.size_bytes > 0
        assert session.get(GrowthControl, "default").mode == "ACTION_REQUIRED"
