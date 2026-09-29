from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from server.api import create_app
from server.models import Base, TikTokConnection


TOKEN = "test-only-operator-secret-32-characters-long"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    current = datetime.now(timezone.utc)
    # Fake account evidence is isolated to this engineering test database.
    with Session(create_engine(url)) as session:
        session.add(TikTokConnection(connection_id="fixture-connection", operator_id="primary",
            provider_user_id="fixture-tiktok-user", granted_scopes="user.info.basic", status="ACTIVE",
            connected_at=current, last_validated_at=current, access_expires_at=current+timedelta(days=1),
            refresh_expires_at=current+timedelta(days=365), manual_verified_at=current,
            manual_uk_evidence_ref="test:market:uk", manual_affiliate_evidence_ref="test:affiliate:status"))
        session.commit()
    operator = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    observed = datetime.now(timezone.utc).isoformat()
    assert operator.post('/v1/capital-authority', json={"authority_id":"capital-001","available_capital_gbp":"10.00",
        "capital_limit_gbp":"8.00","loss_limit_gbp":"5.00","minimum_allocation_score":60,
        "evidence_ref":"fixture:capital:receipt"}).status_code == 200
    assert operator.post('/v1/products', json={"product_id":"product-1","listing_ref":"fixture:listing:1",
        "evidence_ref":"fixture:product:1","observed_at":observed}).status_code == 200
    assert operator.post('/v1/opportunities', json={"opportunity_id":"opportunity-1","product_id":"product-1",
        "capital_required_gbp":"3.00","maximum_loss_gbp":"2.00","allocation_score":70,
        "evidence_ref":"fixture:opportunity:1","observed_at":observed}).status_code == 200
    yield url


def client(url):
    return TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})


def experiment(experiment_id="EXP-001"):
    return {"experiment_id": experiment_id, "decision_id": "DEC-001", "product_id": "product-1",
            "creative_id": "creative-1", "publication_action_id": f"publish-{experiment_id}",
            "authority_evidence_ref": "operator:approved:1", "opportunity_id":"opportunity-1", "market": "UK", "currency": "GBP"}


def event(event_type, external_event_id, amount=None, experiment_id="EXP-001", parent=None):
    return {"experiment_id": experiment_id, "action_id": f"publish-{experiment_id}",
            "source": "MANUAL_VERIFIED", "external_event_id": external_event_id,
            "parent_external_event_id":parent,"event_type": event_type, "amount_gbp": amount, "evidence_ref": f"receipt:{external_event_id}",
            "occurred_at": "2026-09-27T10:00:00Z"}


def launch(c):
    assert c.post('/v1/product-claims',json={"claim_id":"claim-1","product_id":"product-1",
        "text":"Observed product claim", "state":"SUPPORTED", "evidence_ref":"receipt:claim:1"}).status_code == 200
    assert c.post('/v1/creatives',json={"creative_id":"creative-1","experiment_id":"EXP-001",
        "content":"Operator reviewed creative", "claim_ids":["claim-1"], "evidence_ref":"receipt:creative:1"}).status_code == 200
    assert c.post('/v1/creative-approvals',json={"approval_id":"approve-1","experiment_id":"EXP-001",
        "creative_id":"creative-1","evidence_ref":"operator:approval:1"}).status_code == 200
    assert c.post('/v1/launch-intents',json={"packet_id":"packet-1","experiment_id":"EXP-001",
        "approval_id":"approve-1"}).status_code == 200


def test_migration_round_trip_and_metadata(database):
    engine = create_engine(database)
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    cfg = Config(str(ROOT / "alembic.ini"))
    command.downgrade(cfg, "base")
    assert "experiments" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "commerce_events" in inspect(engine).get_table_names()


def test_auth_and_missing_publication_fail_closed(database):
    anonymous = TestClient(create_app(database, TOKEN))
    assert anonymous.post("/v1/experiments", json=experiment()).status_code == 401
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).status_code == 200
    launch(c)
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "s1", "2.00")).status_code == 409
    assert c.post("/v1/events", json=event("PUBLISHED", "video-1", "2.00")).status_code == 422
    assert c.post("/v1/events", json=event("PUBLISHED", "video-1")).status_code == 200
    assert c.post("/v1/events", json=event("PUBLISHED", "video-2")).status_code == 409
    assert c.post("/v1/events", json=event("REFUNDED", "refund-1")).status_code == 422


def test_public_trend_to_original_mp4_is_idempotent_and_does_not_claim_delivery(database, tmp_path):
    from server.trend_sources import TrendEvidence
    now = datetime.now(timezone.utc)
    class FixtureTrendSource:
        def collect(self):
            return [TrendEvidence("gtr-br-test-first-run", "tema em alta", "PUBLIC_FIXTURE_RSS",
                "https://example.test/public-rss", "BR", "BR_SIGNAL", "UNKNOWN", now, now,
                {"google_approx_traffic_raw":"2,000+", "views":None, "likes":None, "comments":None, "shares":None},
                "public fixture evidence; not TikTok metrics")]
    from server.media_storage import RailwayVolumeMediaStore
    media_store = RailwayVolumeMediaStore(tmp_path / "media-volume", max_artifact_bytes=64 * 1024 * 1024,
                                          max_total_bytes=128 * 1024 * 1024)
    app = create_app(database, TOKEN, trend_source=FixtureTrendSource(), media_store=media_store)
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    first = c.post("/v1/growth/run")
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["source"] == "PUBLIC_FIXTURE_RSS"
    assert payload["market"] == "BR" and payload["languageSignal"] == "UNKNOWN"
    assert payload["selected"]["components"]["engagement_rate"] is None
    assert payload["plan"]["assetPlan"]["visuals"].startswith("original")
    assert payload["delivery"]["status"] == "NOT_SENT"
    retry = c.post("/v1/growth/run")
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    media = c.get(payload["videoUrl"])
    assert media.status_code == 409  # GET cannot secretly create a new, untracked render.
    from server.growth_models import GrowthCreative
    with Session(create_engine(database)) as session:
        creative = session.get(GrowthCreative, payload["creativeId"])
        assert creative.state == "SCRIPTED" and creative.media_hash is None


def test_observation_keeps_fourteen_views_out_of_learning_and_public_feed(database):
    from server.trend_sources import TrendEvidence
    now = datetime.now(timezone.utc)
    class FixtureTrendSource:
        def collect(self):
            return [TrendEvidence("gtr-br-observation-test", "tema de observação", "PUBLIC_FIXTURE_RSS",
                "https://example.test/trends", "BR", "BR_SIGNAL", "UNKNOWN", now, now,
                {"views":None,"likes":None,"comments":None,"shares":None}, "public test signal")]
    app = create_app(database, TOKEN, trend_source=FixtureTrendSource())
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    result = c.post("/v1/growth/run").json()
    observation = {"observation_id":"obs-14-views","creative_id":result["creativeId"],
        "source":"OWNER_TIKTOK_UI","publication_identity":"https://vt.tiktok.com/example123",
        "truth_classification":"OWNER_REPORTED","evidence_ref":"operator-supplied-screen:obs-14",
        "observed_at":datetime.now(timezone.utc).isoformat(),"views":14,"likes":1,
        "comments":0,"shares":0}
    response = c.post("/v1/growth/observations",json=observation)
    assert response.status_code==200
    assert response.json()["truth"]=="OWNER_REPORTED"
    assert response.json()["learningEligibility"]=="OBSERVED_BUT_NOT_LEARNING_ELIGIBLE"
    assert response.json()["exclusionReason"]=="QUALITY_GATE_NOT_PASSED"
    assert response.json()["learning"]["verdict"]=="INSUFFICIENT_EVIDENCE"
    assert c.post("/v1/growth/observations",json=observation).json()["duplicate"] is True
    public = TestClient(app).get("/v1/public/mrwho/feed")
    assert public.status_code==200
    assert public.json()=={"brand":"Mr.Who?","commerceEnabled":False,"items":[]}


def test_growth_workspace_reads_server_truth_and_controls(database):
    from server.trend_sources import TrendEvidence
    class FixtureTrendSource:
        def collect(self):
            now = datetime.now(timezone.utc)
            return [TrendEvidence("gtr-br-control-test", "tema do teste", "PUBLIC_FIXTURE_RSS",
                "https://example.test/trends", "BR", "BR_SIGNAL", "UNKNOWN", now, now,
                {"google_approx_traffic_raw":"1,000+", "views":None, "likes":None,
                 "comments":None, "shares":None}, "control fixture")]
    c = TestClient(create_app(database, TOKEN, trend_source=FixtureTrendSource()),
        headers={"Authorization": f"Bearer {TOKEN}"})
    initial = c.get("/v1/growth/overview").json()
    assert initial["control"]["mode"] == "READY"
    assert initial["control"]["scheduler"] == "NOT_CONFIGURED"
    assert initial["followers"] is None
    assert initial["counts"]["experiments"] == 0
    paused = c.post("/v1/growth/control", json={"action": "PAUSE"})
    assert paused.status_code == 200 and paused.json()["mode"] == "PAUSED"
    assert c.post("/v1/growth/run").status_code == 409
    started = c.post("/v1/growth/control", json={"action": "START"})
    assert started.status_code == 200 and started.json()["mode"] == "RUNNING"
    assert started.json()["cycle"]["jobState"] == "PENDING"
    repeated_start = c.post("/v1/growth/control", json={"action":"START"})
    assert repeated_start.status_code == 200 and repeated_start.json()["duplicate"] is True
    assert c.get("/v1/growth/overview").json()["counts"]["experiments"] == 1
    assert c.post("/v1/growth/control", json={"action":"PAUSE"}).json()["mode"] == "PAUSED"
    assert c.post("/v1/growth/control", json={"action":"PAUSE"}).json()["duplicate"] is True
    assert c.post("/v1/growth/control", json={"action": "NOT_A_CONTROL"}).status_code == 422


def test_mobile_start_worker_ready_media_and_video_contract(database, tmp_path):
    """Protect the mobile START -> queued worker -> READY -> overview/video path."""
    from sqlalchemy import select
    from server.growth_models import GrowthCreative, GrowthStateTransition
    from server.growth_worker import claim_due_job, finish_internal_job
    from server.media_storage import RailwayVolumeMediaStore
    from server.trend_sources import TrendEvidence

    now = datetime.now(timezone.utc)

    class FixtureTrendSource:
        def collect(self):
            return [TrendEvidence("gtr-br-mobile-contract", "tema mobile", "PUBLIC_FIXTURE_RSS",
                "https://example.test/mobile-contract", "BR", "BR_SIGNAL", "UNKNOWN", now, now,
                {"views": None, "likes": None, "comments": None, "shares": None},
                "mobile contract fixture; no TikTok metrics")]

    media_store = RailwayVolumeMediaStore(tmp_path / "media-volume", max_artifact_bytes=64 * 1024 * 1024,
                                          max_total_bytes=128 * 1024 * 1024)
    c = TestClient(create_app(database, TOKEN, trend_source=FixtureTrendSource(), media_store=media_store),
        headers={"Authorization": f"Bearer {TOKEN}"})
    started = c.post("/v1/growth/control", json={"action": "START"})
    assert started.status_code == 200
    assert started.json()["mode"] == "RUNNING"
    creative_id = started.json()["cycle"]["creativeId"]
    experiment_id = started.json()["cycle"]["experimentId"]

    engine = create_engine(database)
    with Session(engine) as session:
        prepare = claim_due_job(session, "mobile-contract-test")
        assert prepare is not None and prepare.job_type == "PREPARE_ASSETS"
        assert finish_internal_job(session, prepare) == "SUCCEEDED"
        render = claim_due_job(session, "mobile-contract-test")
        assert render is not None and render.job_type == "RENDER_VIDEO"
        assert finish_internal_job(session, render, media_store=media_store) == "SUCCEEDED"

        creative = session.get(GrowthCreative, creative_id)
        assert creative is not None
        assert creative.quality_status in {"QUALITY_PASS", "QUALITY_REVIEW"}
        transitions = session.scalars(select(GrowthStateTransition).where(
            GrowthStateTransition.experiment_id == experiment_id)).all()
        transition_pairs = {(row.source_state, row.target_state) for row in transitions}
        assert ("ASSETS_PENDING", "RENDERING") in transition_pairs
        assert ("RENDERING", creative.state) in transition_pairs

    overview = c.get("/v1/growth/overview").json()
    assert overview["control"]["mode"] == "ACTION_REQUIRED"
    media = next(item for item in overview["media"] if item["creativeId"] == creative_id)
    assert len(media["mediaHash"]) == 64
    assert media["storageState"] == "STORED_VERIFIED"
    assert media["mediaReady"] is (creative.quality_status == "QUALITY_PASS")

    response = c.get(media["videoUrl"])
    if media["mediaReady"]:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("video/mp4")
        assert len(response.content) > 1000
        assert response.headers["x-media-state"] == "MEDIA_READY"
    else:
        assert response.status_code == 409
    assert overview["capabilities"]["autonomousPublish"] == "NOT_PROVEN"
    assert overview["capabilities"]["observe"] == "NOT_PROVEN"
    assert overview["capabilities"]["learn"] == "NOT_PROVEN"
    assert overview["capabilities"]["repeat"] == "NOT_PROVEN"


def test_emergency_stop_blocks_queued_work_and_render_request(database):
    from server.growth_queue_models import GrowthJob
    from server.growth_queue_models import utcnow
    from server.trend_sources import TrendEvidence
    now = datetime.now(timezone.utc)
    class FixtureTrendSource:
        def collect(self):
            return [TrendEvidence("gtr-br-stop-test", "tema de teste", "PUBLIC_FIXTURE",
                "https://example.test/trends", "BR", "BR_SIGNAL", "UNKNOWN", now, now,
                {"views": None, "likes": None, "comments": None, "shares": None}, "Fixture evidence")]
    c = TestClient(create_app(database, TOKEN, trend_source=FixtureTrendSource()),
        headers={"Authorization": f"Bearer {TOKEN}"})
    result = c.post("/v1/growth/run").json()
    job_now = utcnow()
    with Session(create_engine(database)) as session:
        session.add(GrowthJob(job_id="pending-stop-test", creative_id=result["creativeId"],
            job_type="RENDER_VIDEO", idempotency_key="stop-test:render", state="PENDING", attempts=0,
            available_at=job_now, created_at=job_now, updated_at=job_now))
        session.commit()
    stopped = c.post("/v1/growth/control", json={"action": "EMERGENCY_STOP"})
    assert stopped.status_code == 200 and stopped.json()["mode"] == "STOPPED"
    assert c.post("/v1/growth/control", json={"action":"EMERGENCY_STOP"}).json()["duplicate"] is True
    with Session(create_engine(database)) as session:
        assert session.get(GrowthJob, "pending-stop-test").state == "BLOCKED"
    assert c.get(result["videoUrl"]).status_code == 409


def test_restart_exact_retry_conflict_and_refund_revocation(database):
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).json()["duplicate"] is False
    assert c.post("/v1/experiments", json=experiment()).json()["duplicate"] is True
    assert c.post("/v1/experiments", json={**experiment(), "decision_id": "DEC-OTHER"}).status_code == 409
    launch(c)
    for typ, ext, amount in [("PUBLISHED", "video", None), ("ORDER_CREATED", "order", None),
                             ("DELIVERED", "delivered", None), ("COMMISSION_SETTLED", "settlement", "2.00")]:
        assert c.post("/v1/events", json=event(typ, ext, amount, parent={"ORDER_CREATED":"video", "DELIVERED":"order", "COMMISSION_SETTLED":"order"}.get(typ))).status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": "EXP-001", "amount_gbp": "0.01", "evidence_ref": "receipt:cost"}).status_code == 200
    before = c.get("/v1/experiments/EXP-001/economics").json()
    assert before["realized_contribution_gbp"] == "1.99"
    assert before["local_first_pound_candidate"] is True
    assert before["commercial_proof"] == "NOT_PROVEN"
    recovered = client(database)
    assert recovered.post("/v1/events", json=event("COMMISSION_SETTLED", "settlement", "2.00",parent="order")).json()["duplicate"] is True
    assert recovered.post("/v1/events", json=event("COMMISSION_SETTLED", "settlement", "9.00",parent="order")).status_code == 409
    assert recovered.post("/v1/events", json=event("REFUNDED", "refund", "1.01",parent="settlement")).status_code == 200
    after = recovered.get("/v1/experiments/EXP-001/economics").json()
    assert after["net_settled_gbp"] == "0.99"
    assert after["realized_contribution_gbp"] == "0.98"
    assert after["local_first_pound_candidate"] is False
    assert after["commercial_proof"] == "NOT_PROVEN"
    projected = recovered.get("/v1/portfolio").json()
    assert projected["experiments"][0]["realizedContributionGbp"] == "0.98"
    assert projected["experiments"][0]["firstPoundCandidate"] is False


def test_later_cost_revokes_pound_without_overwriting_initial_receipt(database):
    c = client(database)
    c.post("/v1/experiments", json=experiment())
    launch(c)
    for typ, ext, amount in [("PUBLISHED", "video", None), ("ORDER_CREATED", "order", None),
                             ("DELIVERED", "delivery", None), ("COMMISSION_SETTLED", "settlement", "2.00")]:
        assert c.post("/v1/events", json=event(typ, ext, amount, parent={"ORDER_CREATED":"video", "DELIVERED":"order", "COMMISSION_SETTLED":"order"}.get(typ))).status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": "EXP-001", "amount_gbp": "0.00", "evidence_ref": "receipt:initial"}).status_code == 200
    assert c.get("/v1/experiments/EXP-001/economics").json()["local_first_pound_candidate"] is True
    adjustment = {"adjustment_id": "cost:camera:1", "experiment_id": "EXP-001", "amount_gbp": "1.01", "evidence_ref": "receipt:camera"}
    assert c.post("/v1/cost-adjustments", json=adjustment).json()["duplicate"] is False
    assert client(database).post("/v1/cost-adjustments", json=adjustment).json()["duplicate"] is True
    assert c.post("/v1/cost-adjustments", json={**adjustment, "amount_gbp": "1.02"}).status_code == 409
    result = client(database).get("/v1/experiments/EXP-001/economics").json()
    assert result["observed_cost_gbp"] == "1.01"
    assert result["realized_contribution_gbp"] == "0.99"
    assert result["local_first_pound_candidate"] is False


def test_money_and_cross_experiment_guards(database):
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).status_code == 200
    launch(c)
    assert c.post("/v1/events", json=event("PUBLISHED", "video")).status_code == 200
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "fractional", "1.001")).status_code == 422
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "negative", "-1.00")).status_code == 422
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "cross", "99.00", "EXP-002")).status_code == 409
    assert c.get("/v1/experiments/EXP-001/economics").json()["net_settled_gbp"] is None


def test_configuration_requires_server_side_secret(database):
    with pytest.raises(RuntimeError):
        create_app(database, "short")


def test_operator_browser_session_reads_server_truth_and_requires_csrf_for_writes(database):
    c=TestClient(create_app(database,TOKEN,operator_login_secret="operator-test-secret-longer-than-32-characters"),
        base_url="https://agent.example")
    assert c.get("/v1/portfolio").status_code==401
    assert c.post("/v1/operator/login",json={"access_key":"operator-test-secret-longer-than-32-characters"}).status_code==200
    assert c.get("/v1/portfolio").json()["experiments"]==[]
    assert c.post("/v1/experiments",json=experiment()).status_code==403
    csrf=c.cookies.get("operator_csrf")
    assert c.post("/v1/experiments",json=experiment(),headers={"X-CSRF-Token":csrf}).status_code==200
    recovered=TestClient(create_app(database,TOKEN,operator_login_secret="operator-test-secret-longer-than-32-characters"),
        base_url="https://agent.example")
    recovered.cookies.update(c.cookies)
    assert recovered.get("/v1/portfolio").json()["experiments"][0]["experimentId"]=="EXP-001"


def test_settlement_five_cost_three_refund_two_revokes_first_pound_after_restart(database):
    c=client(database)
    assert c.post("/v1/experiments",json=experiment()).status_code==200
    launch(c)
    for kind,external,amount in [("PUBLISHED","video-one",None),("ORDER_CREATED","order-one",None),
        ("DELIVERED","delivery-one",None),("COMMISSION_SETTLED","settlement-one","5.00")]:
        assert c.post("/v1/events",json=event(kind,external,amount,parent={"ORDER_CREATED":"video-one","DELIVERED":"order-one","COMMISSION_SETTLED":"order-one"}.get(kind))).status_code==200
    assert c.post("/v1/costs",json={"experiment_id":"EXP-001","amount_gbp":"3.00",
        "evidence_ref":"receipt:cost:three"}).status_code==200
    assert c.get("/v1/portfolio").json()["experiments"][0]["realizedContributionGbp"]=="2.00"
    assert c.get("/v1/portfolio").json()["experiments"][0]["firstPoundCandidate"] is True
    assert c.post("/v1/events",json=event("REFUNDED","refund-one","2.00",parent="settlement-one")).status_code==200
    restarted=client(database)
    assert restarted.get("/v1/portfolio").json()["experiments"][0]["realizedContributionGbp"]=="0.00"
    assert restarted.get("/v1/portfolio").json()["experiments"][0]["firstPoundCandidate"] is False
    assert restarted.get("/v1/experiments/EXP-001/economics").json()["commercial_proof"]=="NOT_PROVEN"
    assert restarted.post("/v1/events",json=event("REFUNDED","refund-two","4.00",parent="settlement-one")).status_code==200
    assert restarted.get("/v1/portfolio").json()["experiments"][0]["realizedContributionGbp"]=="-4.00"
