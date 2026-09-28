"""Authenticated durable API for Brazil growth experiments. No publishing side effect."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .growth_brain import TrendCandidate, build_creative_plan, canonical_plan, choose_niche, trend_score
from .growth_models import GrowthCreative, NicheHypothesis, TrendSignal

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

def add_growth_routes(app, engine, require_operator):
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
