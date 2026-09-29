from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server import action_effect_models  # register Effect Ledger tables for metadata
from server.delivery_models import DeliveryEffect
from server.growth_cycle import run_growth_cycle, run_scheduler_tick
from server.growth_models import (
    FollowerSnapshot,
    GrowthControl,
    GrowthCreative,
    GrowthObservation,
    GrowthQuotaEvent,
)
from server.growth_queue_models import GrowthJob
from server.models import Base
from server.trend_sources import TrendEvidence


class FakeBrazilSource:
    def collect(self):
        now = datetime.now(timezone.utc)
        return [
            TrendEvidence(
                trend_id="ci-trend-operational-loop",
                topic="como verificar uma curiosidade antes de compartilhar",
                source="CI_PUBLIC_SIGNAL",
                source_ref="ci://public/br/operational-loop",
                market="BR",
                geography="BR_SIGNAL",
                language="pt-BR",
                collected_at=now,
                observed_at=now,
                metrics={
                    "google_approx_traffic_raw": "100000+",
                    "views": None,
                    "likes": None,
                    "comments": None,
                    "shares": None,
                },
                evidence="CI public-signal fixture; TikTok metrics UNKNOWN.",
            )
        ]


def cycle_db(tmp_path, *, experiment_quota=3):
    engine = create_engine(f"sqlite:///{tmp_path / 'cycle.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(GrowthControl(
            control_id="default",
            mode="READY",
            scheduler_enabled=True,
            scheduler_interval_seconds=60,
            daily_experiment_quota=experiment_quota,
            daily_handoff_quota=3,
            follower_goal=1000,
            updated_at=datetime.now(timezone.utc),
        ))
        session.commit()
    return engine


def finish_job_and_add_human_evidence(engine, creative_id):
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        job = session.scalar(select(GrowthJob).where(GrowthJob.creative_id == creative_id))
        job.state = "SUCCEEDED"
        job.lease_owner = None
        job.lease_until = None
        creative = session.get(GrowthCreative, creative_id)
        creative.state = "OBSERVING"
        session.add(DeliveryEffect(
            delivery_id=str(uuid4()),
            action_contract_id=str(uuid4()),
            effect_id=str(uuid4()),
            artifact_id=str(uuid4()),
            creative_id=creative_id,
            artifact_sha256="a" * 64,
            target="ANDROID_SHARE_HANDOFF",
            provider="ANDROID_SHARE",
            target_account_id=None,
            state="HANDOFF_INITIATED",
            created_at=now,
            updated_at=now,
        ))
        session.add(GrowthObservation(
            observation_id="obs-" + creative_id,
            creative_id=creative_id,
            views=25,
            likes=2,
            comments=1,
            shares=1,
            publication_identity="https://www.tiktok.com/@owner/video/123",
            truth_classification="OWNER_REPORTED",
            followers_before=10,
            followers_after=12,
            source="OWNER_TIKTOK_UI",
            evidence_ref="owner-screenshot:" + creative_id,
            observed_at=now,
        ))
        control = session.get(GrowthControl, "default")
        control.mode = "RUNNING"
        control.last_scheduler_tick_at = None
        session.commit()


def test_initial_cycle_creates_original_plan_job_and_quota_event(tmp_path):
    engine = cycle_db(tmp_path)
    result = run_growth_cycle(engine, FakeBrazilSource(), trigger="MANUAL")
    assert result["jobState"] == "PENDING"
    assert result["plan"]["originalIdea"]["copyPolicy"] == "PATTERN_ONLY_NEVER_CONTENT"
    assert result["plan"]["creativeDNA"]["sceneCount"] == 5
    assert result["plan"]["provenance"]["privateApi"] is False
    assert result["plan"]["cycle"]["oneVideoIsLearning"] is False
    with Session(engine) as session:
        creative = session.get(GrowthCreative, result["creativeId"])
        assert creative.policy_status == "NOT_EVALUATED"
        event = session.scalar(select(GrowthQuotaEvent).where(
            GrowthQuotaEvent.event_type == "EXPERIMENT"))
        assert event and event.creative_id == result["creativeId"]


def test_scheduler_stops_at_human_publication_gate(tmp_path):
    engine = cycle_db(tmp_path)
    first = run_growth_cycle(engine, FakeBrazilSource(), trigger="MANUAL")
    with Session(engine) as session:
        job = session.scalar(select(GrowthJob).where(GrowthJob.creative_id == first["creativeId"]))
        job.state = "SUCCEEDED"
        session.commit()
    decision = run_scheduler_tick(engine, FakeBrazilSource())
    assert decision == {
        "decision": "WAITING",
        "reason": "HUMAN_PUBLICATION_OBSERVATION_REQUIRED",
    }
    with Session(engine) as session:
        assert session.scalar(select(GrowthCreative).where(
            GrowthCreative.creative_id != first["creativeId"])) is None


def test_one_owner_report_allows_next_exploration_but_not_learning_claim(tmp_path):
    engine = cycle_db(tmp_path)
    first = run_growth_cycle(engine, FakeBrazilSource(), trigger="MANUAL")
    finish_job_and_add_human_evidence(engine, first["creativeId"])
    decision = run_scheduler_tick(engine, FakeBrazilSource())
    assert decision["decision"] == "STARTED"
    with Session(engine) as session:
        second = session.get(GrowthCreative, decision["creativeId"])
        import json
        plan = json.loads(second.plan_json)
        assert plan["cycle"]["mutationMode"] == "DETERMINISTIC_EXPLORATION"
        assert plan["cycle"]["learningId"] is None
        assert plan["cycle"]["oneVideoIsLearning"] is False
        assert session.scalar(select(GrowthQuotaEvent).where(
            GrowthQuotaEvent.idempotency_key == "experiment:" + second.creative_id))


def test_daily_experiment_quota_blocks_repeat_even_after_human_evidence(tmp_path):
    engine = cycle_db(tmp_path, experiment_quota=1)
    first = run_growth_cycle(engine, FakeBrazilSource(), trigger="MANUAL")
    finish_job_and_add_human_evidence(engine, first["creativeId"])
    decision = run_scheduler_tick(engine, FakeBrazilSource())
    assert decision == {"decision": "QUOTA_REACHED", "reason": "DAILY_EXPERIMENT_QUOTA_REACHED"}


def test_follower_goal_stops_scheduler_conservatively(tmp_path):
    engine = cycle_db(tmp_path)
    first = run_growth_cycle(engine, FakeBrazilSource(), trigger="MANUAL")
    with Session(engine) as session:
        job = session.scalar(select(GrowthJob).where(GrowthJob.creative_id == first["creativeId"]))
        job.state = "SUCCEEDED"
        session.add(FollowerSnapshot(
            snapshot_id="followers-goal",
            account_id="primary",
            followers=1000,
            source="OWNER_TIKTOK_UI",
            truth_classification="OWNER_REPORTED",
            evidence_ref="owner-screenshot:followers-goal",
            observed_at=datetime.now(timezone.utc),
        ))
        session.get(GrowthControl, "default").last_scheduler_tick_at = None
        session.commit()
    decision = run_scheduler_tick(engine, FakeBrazilSource())
    assert decision == {"decision": "GOAL_REACHED", "reason": "FOLLOWER_GOAL_REACHED"}
