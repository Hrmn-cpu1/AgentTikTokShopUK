"""Authenticated durable API for Brazil growth experiments. No publishing side effect."""
import json
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .growth_brain import TrendCandidate, build_creative_plan, canonical_plan, choose_niche, trend_score
from .growth_models import (GrowthCreative, GrowthControl, GrowthLearning, GrowthObservation,
    FollowerSnapshot, NicheHypothesis, PublicationIntent, TrendSignal)
from .growth_queue_models import GrowthJob
from .models import TikTokConnection
from .growth_renderer import render_growth_plan
from .trend_sources import GoogleTrendsBrazilRSS, rank_public_signal

class TrendInput(BaseModel):
    trend_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=2, max_length=40)
    source_ref: str = Field(min_length=6, max_length=1000)
    evidence: str = Field(min_length=3, max_length=4000)
    metrics: dict = Field(default_factory=dict)
    observed_at: datetime

class CreativeRequest(BaseModel):
    creative_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)
    trend_id: str = Field(min_length=1, max_length=100)

def add_growth_routes(app, engine, require_operator, trend_source=None):
    source = trend_source or GoogleTrendsBrazilRSS()

    def control_row(session):
        control = session.get(GrowthControl, "default")
        if control is None:
            control = GrowthControl(control_id="default", mode="READY", updated_at=datetime.now(timezone.utc))
            session.add(control)
            session.flush()
        return control

    @app.get("/v1/growth/control", dependencies=[Depends(require_operator)])
    def get_growth_control():
        with Session(engine) as session:
            control = control_row(session)
            session.commit()
            return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                "execution": "ON_DEMAND", "scheduler": "NOT_CONFIGURED"}

    @app.post("/v1/growth/control", dependencies=[Depends(require_operator)])
    def set_growth_control(payload: dict):
        action = payload.get("action")
        modes = {"START": "READY", "PAUSE": "PAUSED", "EMERGENCY_STOP": "STOPPED"}
        if action not in modes:
            raise HTTPException(422, "action must be START, PAUSE, or EMERGENCY_STOP")
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            control = control_row(session)
            control.mode = modes[action]
            control.updated_at = now
            if action == "EMERGENCY_STOP":
                jobs = session.scalars(select(GrowthJob).where(GrowthJob.state.in_(["PENDING", "RETRY"]))).all()
                for job in jobs:
                    job.state = "BLOCKED"
                    job.last_error = "Blocked by operator emergency stop"
                    job.updated_at = now
            session.commit()
            return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                "execution": "ON_DEMAND", "scheduler": "NOT_CONFIGURED"}

    @app.get("/v1/growth/overview", dependencies=[Depends(require_operator)])
    def growth_overview():
        with Session(engine) as session:
            control = control_row(session)
            creatives = session.scalars(select(GrowthCreative).order_by(GrowthCreative.created_at.desc()).limit(50)).all()
            observations = session.scalars(select(GrowthObservation).order_by(GrowthObservation.observed_at.desc()).limit(100)).all()
            followers = session.scalars(select(FollowerSnapshot).order_by(FollowerSnapshot.observed_at.desc()).limit(1)).all()
            intents = session.scalars(select(PublicationIntent).order_by(PublicationIntent.created_at.desc()).limit(50)).all()
            learnings = session.scalars(select(GrowthLearning).order_by(GrowthLearning.created_at.desc()).limit(50)).all()
            jobs = session.scalars(select(GrowthJob).order_by(GrowthJob.created_at.desc()).limit(20)).all()
            connection = session.scalar(select(TikTokConnection).where(TikTokConnection.operator_id == "primary"))
            total_creatives = session.scalar(select(func.count(GrowthCreative.creative_id))) or 0
            total_rendered = session.scalar(select(func.count(GrowthCreative.creative_id)).where(GrowthCreative.media_hash.is_not(None))) or 0
            total_ready = session.scalar(select(func.count(GrowthCreative.creative_id)).where(GrowthCreative.state == "READY")) or 0
            total_observations = session.scalar(select(func.count(GrowthObservation.observation_id))) or 0
            total_learnings = session.scalar(select(func.count(GrowthLearning.learning_id))) or 0
            total_pending_jobs = session.scalar(select(func.count(GrowthJob.job_id)).where(GrowthJob.state.in_(["PENDING", "RETRY", "RUNNING"]))) or 0
            creatives_by_id = {item.creative_id: item for item in creatives}
            latest_observations = {}
            for item in observations:
                latest_observations.setdefault(item.creative_id, item)
            intents_by_creative = {}
            for item in intents:
                intents_by_creative.setdefault(item.creative_id, item)
            learning_by_creative = {}
            for item in learnings:
                learning_by_creative.setdefault(item.creative_id, item)
            experiment_items = []
            media_items = []
            for creative in creatives:
                plan = json.loads(creative.plan_json)
                trend = session.get(TrendSignal, creative.trend_id)
                observation = latest_observations.get(creative.creative_id)
                intent = intents_by_creative.get(creative.creative_id)
                learning = learning_by_creative.get(creative.creative_id)
                metrics = json.loads(trend.metrics_json) if trend else {}
                evidence = plan.get("sourceEvidence", {})
                record = {"creativeId": creative.creative_id, "experimentId": creative.experiment_id,
                    "state": creative.state, "createdAt": creative.created_at.isoformat(),
                    "topic": trend.topic if trend else "UNKNOWN", "source": trend.source if trend else "UNKNOWN",
                    "sourceRef": trend.source_ref if trend else None, "observedAt": trend.observed_at.isoformat() if trend else None,
                    "evidence": trend.evidence if trend else "UNKNOWN", "rankingScore": evidence.get("rankingScore"),
                    "rankingComponents": evidence.get("rankingComponents"), "selectionReason": evidence.get("selectionReason"),
                    "metrics": metrics, "plan": plan,
                    "delivery": {"state": intent.provider_status if intent else "NOT_REQUESTED",
                        "provider": intent.provider if intent else None, "providerId": intent.provider_publish_id if intent else None},
                    "observation": None if observation is None else {"source": observation.source,
                        "evidenceRef": observation.evidence_ref, "observedAt": observation.observed_at.isoformat(),
                        "views": observation.views, "likes": observation.likes, "comments": observation.comments,
                        "shares": observation.shares, "followersBefore": observation.followers_before,
                        "followersAfter": observation.followers_after},
                    "learning": None if learning is None else {"verdict": learning.verdict, "rationale": learning.rationale,
                        "nextMutation": json.loads(learning.next_mutation_json), "createdAt": learning.created_at.isoformat()}}
                experiment_items.append(record)
                if creative.media_hash:
                    media_items.append({"creativeId": creative.creative_id, "experimentId": creative.experiment_id,
                        "topic": record["topic"], "state": creative.state, "mediaHash": creative.media_hash,
                        "createdAt": creative.created_at.isoformat(), "videoUrl": f"/v1/growth/creatives/{creative.creative_id}/video"})
            observations_count = total_observations
            follower_snapshot = followers[0] if followers else None
            session.commit()
            return {"control": {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                    "execution": "ON_DEMAND", "scheduler": "NOT_CONFIGURED"},
                "identity": {"status": "AVAILABLE" if connection and connection.status == "ACTIVE" else "UNKNOWN",
                    "source": "tiktok_connections.status" if connection else "No server connection record",
                    "connectedAt": connection.connected_at.isoformat() if connection else None},
                "capabilities": {"discover": "PARTIAL", "analyze": "PARTIAL", "create": "PARTIAL",
                    "render": "REAL", "delivery": "MANUAL", "autonomousPublish": "NOT_PROVEN",
                    "observe": "NOT_PROVEN" if not observations_count else "PARTIAL",
                    "learn": "NOT_PROVEN" if not learnings else "PARTIAL", "repeat": "NOT_PROVEN"},
                "counts": {"experiments": total_creatives, "rendered": total_rendered,
                    "ready": total_ready, "observations": observations_count,
                    "learningRecords": total_learnings, "pendingJobs": total_pending_jobs},
                "followers": None if follower_snapshot is None else {"value": follower_snapshot.followers,
                    "source": follower_snapshot.source, "observedAt": follower_snapshot.observed_at.isoformat(),
                    "evidenceRef": follower_snapshot.evidence_ref},
                "experiments": experiment_items, "media": media_items,
                "observations": [{"creativeId": o.creative_id, "source": o.source, "evidenceRef": o.evidence_ref,
                    "observedAt": o.observed_at.isoformat(), "views": o.views, "likes": o.likes,
                    "comments": o.comments, "shares": o.shares} for o in observations]}

    @app.post("/v1/growth/run", dependencies=[Depends(require_operator)])
    def run_first_experiment():
        """Discover current public BR signals, select deterministically and create one original plan."""
        with Session(engine) as session:
            control = control_row(session)
            mode = control.mode
        if mode != "READY":
            raise HTTPException(409, f"Growth agent is {mode.lower()}")
        try:
            candidates = source.collect()
        except Exception as exc:
            raise HTTPException(503, f"Trend source unavailable: {type(exc).__name__}") from None
        now = datetime.now(timezone.utc)
        candidates = [item for item in candidates if item.market == "BR" and
                      item.observed_at.tzinfo is not None and
                      0 <= (now - item.observed_at.astimezone(timezone.utc)).total_seconds() <= 48 * 3600]
        if not candidates:
            raise HTTPException(503, "No fresh public Brazil trend signals")
        ranked = sorted(((rank_public_signal(item, now), item) for item in candidates),
                        key=lambda row: (-row[0]["score"], -row[1].observed_at.timestamp(), row[1].trend_id))
        ranking = [{"trendId": item.trend_id, "topic": item.topic, **score} for score, item in ranked[:20]]
        chosen_score, chosen = ranked[0]
        metrics = dict(chosen.metrics)
        metrics["ranking"] = chosen_score
        with Session(engine) as session:
            if control_row(session).mode != "READY":
                session.rollback()
                raise HTTPException(409, "Growth agent was stopped before the experiment could be saved")
            trend = session.get(TrendSignal, chosen.trend_id)
            if trend is None:
                trend = TrendSignal(trend_id=chosen.trend_id, source=chosen.source, source_ref=chosen.source_ref,
                    topic=chosen.topic[:300], market="BR", language=chosen.language,
                    metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    evidence=chosen.evidence, observed_at=chosen.observed_at.astimezone(timezone.utc))
                session.add(trend)
                session.flush()
            creative_id = "creative-" + chosen.trend_id
            experiment_id = "experiment-" + chosen.trend_id
            creative = session.get(GrowthCreative, creative_id)
            duplicate = creative is not None
            if creative is None:
                niche_name = choose_niche(TrendCandidate(topic=chosen.topic, source=chosen.source,
                    source_ref=chosen.source_ref, evidence=chosen.evidence, metrics=metrics), {})
                niche_id = "niche-" + niche_name
                niche = session.get(NicheHypothesis, niche_id)
                if niche is None:
                    niche = NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR",
                        hypothesis=f"Testar hook e checklist original sobre sinal público de busca: {chosen.topic[:180]}",
                        trend_evidence=chosen.source_ref, production_cost_centavos=0, risk="LOW",
                        status="EXPLORING", created_at=now)
                    session.add(niche)
                candidate = TrendCandidate(topic=chosen.topic, source=chosen.source, source_ref=chosen.source_ref,
                    evidence=chosen.evidence, metrics=metrics)
                plan = build_creative_plan(candidate, niche_name)
                plan["sourceEvidence"].update({"geography": chosen.geography,
                    "collectedAt": chosen.collected_at.isoformat(), "observedAt": chosen.observed_at.isoformat(),
                    "rankingComponents": chosen_score["components"], "rankingScore": chosen_score["score"],
                    "selectionReason": "highest reproducible fresh BR public-search score; TikTok engagement is UNKNOWN"})
                creative = GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=chosen.trend_id,
                    experiment_id=experiment_id, plan_json=canonical_plan(plan), evidence_ref=chosen.source_ref,
                    state="SCRIPTED", created_at=now)
                session.add(creative)
                session.commit()
            plan = json.loads(creative.plan_json)
            return {"state": creative.state, "duplicate": duplicate, "creativeId": creative.creative_id,
                "experimentId": creative.experiment_id, "source": chosen.source,
                "market": "BR", "geography": chosen.geography, "languageSignal": chosen.language,
                "ranking": ranking, "selected": {"trendId": chosen.trend_id, "topic": chosen.topic,
                    "score": chosen_score["score"], "components": chosen_score["components"]},
                "plan": plan, "videoUrl": f"/v1/growth/creatives/{creative.creative_id}/video",
                "delivery": {"status": "NOT_SENT", "reason": "TikTok Content Posting scope video.upload is not currently granted"}}

    @app.get("/v1/growth/creatives/{creative_id}/video", dependencies=[Depends(require_operator)])
    def render_experiment_video(creative_id: str):
        with Session(engine) as session:
            if control_row(session).mode != "READY":
                raise HTTPException(409, "Growth agent is paused or stopped")
            creative = session.get(GrowthCreative, creative_id)
            if not creative:
                raise HTTPException(404, "Unknown creative")
            plan_json = creative.plan_json
        directory = tempfile.mkdtemp(prefix="growth-delivery-")
        def cancelled():
            with Session(engine) as session:
                control = session.get(GrowthControl, "default")
                return control is not None and control.mode != "READY"
        try:
            output, digest, cleanup = render_growth_plan(plan_json, output_dir=directory, should_cancel=cancelled)
        except InterruptedError:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(409, "Render cancelled by operator control") from None
        except Exception:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Could not render the experiment video") from None
        with Session(engine) as session:
            creative = session.get(GrowthCreative, creative_id)
            creative.media_ref = f"rendered:{creative_id}/growth.mp4"
            creative.media_hash = digest
            creative.state = "READY"
            session.commit()
        return FileResponse(output, media_type="video/mp4", filename=f"{creative_id}.mp4",
                            headers={"X-Creative-SHA256": digest, "X-Delivery-State": "LOCAL_RENDERED"},
                            background=BackgroundTask(lambda: __import__("shutil").rmtree(directory, ignore_errors=True)))

    @app.post("/v1/growth/trends", dependencies=[Depends(require_operator)])
    def ingest_trend(item: TrendInput):
        if item.observed_at.tzinfo is None or item.observed_at.utcoffset() is None:
            raise HTTPException(422, "observed_at needs an explicit timezone")
        with Session(engine) as session:
            existing = session.get(TrendSignal, item.trend_id)
            metrics_json = json.dumps(item.metrics, sort_keys=True, separators=(",", ":"))
            if existing:
                expected = (item.source, item.source_ref, item.topic, metrics_json, item.evidence)
                actual = (existing.source, existing.source_ref, existing.topic, existing.metrics_json, existing.evidence)
                if actual != expected:
                    raise HTTPException(409, "Conflicting trend identity")
                return {"trendId": item.trend_id, "duplicate": True, "truth": "EVIDENCE_BACKED_INPUT"}
            session.add(TrendSignal(trend_id=item.trend_id, source=item.source, source_ref=item.source_ref,
                topic=item.topic, market="BR", language="pt-BR", metrics_json=metrics_json,
                evidence=item.evidence, observed_at=item.observed_at.astimezone(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Concurrent trend identity conflict") from None
            return {"trendId": item.trend_id, "duplicate": False,
                "score": trend_score(item.metrics), "truth": "EVIDENCE_BACKED_INPUT"}

    @app.post("/v1/growth/creatives", dependencies=[Depends(require_operator)])
    def create_creative(item: CreativeRequest):
        with Session(engine) as session:
            old = session.get(GrowthCreative, item.creative_id)
            if old:
                if old.experiment_id != item.experiment_id or old.trend_id != item.trend_id:
                    raise HTTPException(409, "Conflicting creative identity")
                return {"creativeId": old.creative_id, "experimentId": old.experiment_id,
                    "nicheId": old.niche_id, "duplicate": True, "state": old.state,
                    "plan": json.loads(old.plan_json)}
            if session.scalar(select(GrowthCreative).where(GrowthCreative.experiment_id == item.experiment_id)):
                raise HTTPException(409, "Experiment identity already bound")
            trend = session.get(TrendSignal, item.trend_id)
            if not trend:
                raise HTTPException(404, "Unknown trend evidence")
            candidate = TrendCandidate(topic=trend.topic, source=trend.source, source_ref=trend.source_ref,
                evidence=trend.evidence, metrics=json.loads(trend.metrics_json))
            counts = dict(session.execute(select(NicheHypothesis.niche_id, func.count(GrowthCreative.creative_id))
                .outerjoin(GrowthCreative, GrowthCreative.niche_id == NicheHypothesis.niche_id)
                .group_by(NicheHypothesis.niche_id)).all())
            niche_name = choose_niche(candidate, counts)
            niche_id = "niche-" + niche_name
            niche = session.get(NicheHypothesis, niche_id)
            if niche is None:
                niche = NicheHypothesis(niche_id=niche_id, market="BR", language="pt-BR",
                    hypothesis=f"Testar {niche_name} para crescimento legítimo no Brasil",
                    trend_evidence=trend.source_ref, production_cost_centavos=0, risk="LOW",
                    status="EXPLORING", created_at=datetime.now(timezone.utc))
                session.add(niche)
            plan = build_creative_plan(candidate, niche_name)
            creative = GrowthCreative(creative_id=item.creative_id, niche_id=niche_id, trend_id=trend.trend_id,
                experiment_id=item.experiment_id, plan_json=canonical_plan(plan),
                evidence_ref=trend.source_ref, state="SCRIPTED", created_at=datetime.now(timezone.utc))
            session.add(creative)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Concurrent creative identity conflict") from None
            return {"creativeId": item.creative_id, "experimentId": item.experiment_id,
                "nicheId": niche_id, "duplicate": False, "state": "SCRIPTED", "plan": plan}

    @app.get("/v1/growth/state", dependencies=[Depends(require_operator)])
    def growth_state():
        with Session(engine) as session:
            niches = session.scalars(select(NicheHypothesis).order_by(NicheHypothesis.created_at)).all()
            creatives = session.scalars(select(GrowthCreative).order_by(GrowthCreative.created_at.desc()).limit(20)).all()
            return {"market": "BR", "objective": "LEGITIMATE_FOLLOWER_GROWTH_AND_INFORMATION_GAIN",
                "truth": "SERVER_BUSINESS_TRUTH",
                "niches": [{"nicheId": n.niche_id, "status": n.status, "risk": n.risk} for n in niches],
                "creatives": [{"creativeId": c.creative_id, "experimentId": c.experiment_id,
                    "nicheId": c.niche_id, "trendId": c.trend_id, "state": c.state} for c in creatives]}
