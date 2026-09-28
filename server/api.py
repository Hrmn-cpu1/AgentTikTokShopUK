"""One-operator, manual observation API. It never publishes or spends externally."""
import hmac
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, File, Form, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import CommerceEvent, Experiment, ExperimentCost, ExperimentCostAdjustment, LaunchIntent, LearningRecord, OpportunityEvidence, ProductEvidence, TikTokConnection
from .connection_api import add_connection_routes, utc
from .governance import add_governance_routes, capital_check, fresh, validate_launch
from .video_studio import render_creator_video
from .growth_models import TrendSignal, NicheHypothesis


Money = Decimal


class ExperimentInput(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    decision_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(min_length=1, max_length=100)
    publication_action_id: str = Field(min_length=1, max_length=100)
    authority_evidence_ref: str = Field(min_length=6, max_length=500)
    opportunity_id: str = Field(min_length=1, max_length=100)
    market: Literal["UK"] = "UK"
    currency: Literal["GBP"] = "GBP"


class EventInput(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    action_id: str = Field(min_length=1, max_length=100)
    source: Literal["MANUAL_VERIFIED"] = "MANUAL_VERIFIED"
    external_event_id: str = Field(min_length=1, max_length=200)
    parent_external_event_id: str | None = Field(default=None, min_length=1, max_length=200)
    event_type: Literal["PUBLISHED", "ORDER_CREATED", "DELIVERED", "COMMISSION_SETTLED", "REFUNDED"]
    amount_gbp: Money | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    evidence_ref: str = Field(min_length=6, max_length=500)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at needs an explicit timezone")
        return value.astimezone(timezone.utc)


class CostInput(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    amount_gbp: Money = Field(ge=0, max_digits=18, decimal_places=2)
    evidence_ref: str = Field(min_length=6, max_length=500)


class CostAdjustmentInput(CostInput):
    adjustment_id: str = Field(min_length=1, max_length=100)
    amount_gbp: Money = Field(gt=0, max_digits=18, decimal_places=2)


class LearningInput(BaseModel):
    learning_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)


def create_app(database_url: str | None = None, operator_token: str | None = None,
               *, tiktok_provider=None, operator_login_secret=None, token_encryption_key=None) -> FastAPI:
    url = database_url or os.environ.get("DATABASE_URL")
    if url and url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url[len('postgresql://'):]
    token = operator_token or os.environ.get("OPERATOR_API_TOKEN")
    if not url or not token or len(token) < 32:
        raise RuntimeError("DATABASE_URL and a strong OPERATOR_API_TOKEN are required")
    engine = create_engine(url, pool_pre_ping=True)
    app = FastAPI(title="TikTok Shop UK Observation API")
    session_operator = add_connection_routes(app, engine, tiktok_provider, login_secret=operator_login_secret,
                          encryption_key=token_encryption_key)
    security = HTTPBearer(auto_error=False)

    def require_operator(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
        if credentials is not None:
            if not hmac.compare_digest(credentials.credentials, token):
                raise HTTPException(status_code=401, detail="Operator authentication required")
            return
        with Session(engine) as session:
            session_operator(request, session, csrf=request.method not in {"GET", "HEAD"})

    def require_manual_authority(_operator: None = Depends(require_operator)) -> None:
        with Session(engine) as session:
            connected = session.scalar(select(TikTokConnection).where(TikTokConnection.operator_id == "primary"))
            if connected is None or connected.status != "ACTIVE" or not connected.manual_verified_at or \
               not connected.manual_uk_evidence_ref or not connected.manual_affiliate_evidence_ref or \
               utc(connected.manual_verified_at) + timedelta(days=30) <= datetime.now(timezone.utc) or \
               utc(connected.last_validated_at) + timedelta(minutes=15) <= datetime.now(timezone.utc) or \
               utc(connected.access_expires_at) <= datetime.now(timezone.utc):
                raise HTTPException(status_code=403, detail="Active TikTok identity and current manual authority required")

    add_governance_routes(app, engine, require_operator, require_manual_authority)

    @app.post('/v1/creator-video', dependencies=[Depends(require_operator)])
    async def creator_video(photo: UploadFile = File(...), headline: str = Form(...),
                            message: str = Form(...), call_to_action: str = Form(...)):
        # This is a local creative export. It does not post to TikTok or verify product claims.
        image = await photo.read(3_000_001)
        if len(image) > 3_000_000:
            raise HTTPException(413, 'Imagem deve ter no máximo 3 MB')
        try:
            result, cleanup = render_creator_video(image, headline, message, call_to_action)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except (RuntimeError, TimeoutError):
            raise HTTPException(503, 'Não foi possível produzir o vídeo agora') from None
        return FileResponse(result, media_type='video/mp4', filename='agent-tiktok-shop-video.mp4',
                            background=BackgroundTask(cleanup))

    class GrowthTrendInput(BaseModel):
        source: str = Field(min_length=2, max_length=40)
        source_ref: str = Field(min_length=3, max_length=1000)
        topic: str = Field(min_length=2, max_length=300)
        evidence: str = Field(min_length=3, max_length=4000)
        observed_at: datetime

    class GrowthNicheInput(BaseModel):
        hypothesis: str = Field(min_length=3, max_length=2000)
        trend_id: str = Field(min_length=1, max_length=100)

    @app.post('/v1/growth/trends', dependencies=[Depends(require_operator)])
    def record_growth_trend(item: GrowthTrendInput):
        if item.observed_at.tzinfo is None:
            raise HTTPException(422, 'observed_at needs an explicit timezone')
        row = TrendSignal(trend_id='trend-'+uuid4().hex, source=item.source, source_ref=item.source_ref,
            topic=item.topic, market='BR', language='pt-BR', metrics_json='{}', evidence=item.evidence,
            observed_at=item.observed_at.astimezone(timezone.utc))
        with Session(engine) as session:
            session.add(row); session.commit()
        return {'trendId': row.trend_id, 'truth': 'OBSERVED_INPUT'}

    @app.post('/v1/growth/niches', dependencies=[Depends(require_operator)])
    def record_growth_niche(item: GrowthNicheInput):
        with Session(engine) as session:
            trend = session.get(TrendSignal, item.trend_id)
            if trend is None:
                raise HTTPException(404, 'Trend evidence required')
            row = NicheHypothesis(niche_id='niche-'+uuid4().hex, market='BR', language='pt-BR',
                hypothesis=item.hypothesis, trend_evidence=item.trend_id, production_cost_centavos=0,
                risk='LOW', status='EXPLORING', created_at=datetime.now(timezone.utc))
            session.add(row); session.commit()
        return {'nicheId': row.niche_id, 'status': row.status, 'truth': 'HYPOTHESIS'}

    @app.get("/health")
    def health():
        return {"status": "up"}

    @app.get("/ready")
    def ready():
        if not (operator_login_secret or os.environ.get('OPERATOR_LOGIN_SECRET')):
            raise HTTPException(503, 'Operator login is not configured')
        try:
            with engine.connect() as conn:
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                conn.execute(text("SELECT 1")).scalar_one()
            if revision != "0006_growth_engine":
                raise HTTPException(503, "Database migration required")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready", "database": "reachable", "migration": revision,
            "tiktokAuthorizationConfigured": bool(tiktok_provider or all(os.environ.get(k) for k in
                ('TIKTOK_CLIENT_KEY', 'TIKTOK_CLIENT_SECRET', 'TIKTOK_REDIRECT_URI', 'TIKTOK_TOKEN_ENCRYPTION_KEY')))}

    @app.post("/v1/experiments", dependencies=[Depends(require_manual_authority)])
    def record_experiment(item: ExperimentInput):
        with Session(engine) as session:
            existing = session.get(Experiment, item.experiment_id)
            if existing:
                current = {k: getattr(existing, k) for k in type(item).model_fields}
                if current != item.model_dump():
                    raise HTTPException(status_code=409, detail="Conflicting experiment identity")
                return {"experiment_id": item.experiment_id, "duplicate": True, "state": "MANUAL_ASSERTION"}
            product = session.get(ProductEvidence, item.product_id)
            opportunity = session.get(OpportunityEvidence, item.opportunity_id)
            if not product or not opportunity or opportunity.product_id != item.product_id or not fresh(product.observed_at) or not fresh(opportunity.observed_at):
                raise HTTPException(403, "Fresh product and opportunity evidence required")
            capital_check(session, opportunity)
            session.add(Experiment(**item.model_dump(), created_at=datetime.now(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Conflicting experiment or action identity") from None
        return {"experiment_id": item.experiment_id, "duplicate": False, "state": "MANUAL_ASSERTION"}

    @app.post("/v1/events", dependencies=[Depends(require_manual_authority)])
    def record_event(item: EventInput):
        if item.event_type in {"COMMISSION_SETTLED", "REFUNDED"} and item.amount_gbp is None:
            raise HTTPException(status_code=422, detail="Observed economic amount required")
        if item.event_type == "PUBLISHED" and item.amount_gbp is not None:
            raise HTTPException(status_code=422, detail="Publication is not money")
        now = datetime.now(timezone.utc)
        if item.occurred_at > now:
            raise HTTPException(status_code=422, detail="Future external event is not observed")
        with Session(engine) as session:
            experiment = session.get(Experiment, item.experiment_id)
            if experiment is None or item.action_id != experiment.publication_action_id:
                raise HTTPException(status_code=409, detail="Experiment/action trace mismatch")
            intent = session.scalar(select(LaunchIntent).where(LaunchIntent.experiment_id == item.experiment_id))
            if intent is None:
                raise HTTPException(403, "Governed launch intent required before observing publication")
            existing = session.scalar(select(CommerceEvent).where(
                CommerceEvent.source == item.source, CommerceEvent.external_event_id == item.external_event_id))
            if existing:
                fields = item.model_dump()
                if any(getattr(existing, key) != value for key, value in fields.items() if key not in {"occurred_at", "parent_external_event_id"}) or \
                        existing.occurred_at.replace(tzinfo=timezone.utc) != item.occurred_at:
                    raise HTTPException(status_code=409, detail="Conflicting external event id")
                parent = session.get(CommerceEvent, existing.parent_event_id) if existing.parent_event_id else None
                if (parent.external_event_id if parent else None) != item.parent_external_event_id:
                    raise HTTPException(409, "Conflicting parent event binding")
                return {"event_id": existing.event_id, "duplicate": True, "state": "MANUAL_ASSERTION"}
            if item.event_type == 'PUBLISHED':
                validate_launch(session, experiment, intent)
            if item.event_type == "PUBLISHED" and session.scalar(select(CommerceEvent.event_id).where(
                CommerceEvent.experiment_id == item.experiment_id, CommerceEvent.event_type == "PUBLISHED")) is not None:
                raise HTTPException(status_code=409, detail="Publication already observed; reconcile before retry")
            if item.event_type != "PUBLISHED" and session.scalar(select(CommerceEvent.event_id).where(
                CommerceEvent.experiment_id == item.experiment_id, CommerceEvent.event_type == "PUBLISHED")) is None:
                raise HTTPException(status_code=409, detail="Publication observation required first")
            expected_parent = {"PUBLISHED": None, "ORDER_CREATED": "PUBLISHED", "DELIVERED": "ORDER_CREATED",
                "COMMISSION_SETTLED": "ORDER_CREATED", "REFUNDED": "COMMISSION_SETTLED"}[item.event_type]
            parent = session.scalar(select(CommerceEvent).where(CommerceEvent.source == item.source,
                CommerceEvent.external_event_id == item.parent_external_event_id)) if item.parent_external_event_id else None
            if (expected_parent is None and item.parent_external_event_id) or (expected_parent is not None and
                (parent is None or parent.event_type != expected_parent or parent.experiment_id != item.experiment_id)):
                raise HTTPException(409, "External event binding missing or mismatched")
            if item.event_type == 'COMMISSION_SETTLED' and session.scalar(select(CommerceEvent.event_id).where(
                CommerceEvent.event_type == 'DELIVERED', CommerceEvent.parent_event_id == parent.event_id)) is None:
                raise HTTPException(409, 'Delivery observation required before settlement')
            event = CommerceEvent(event_id=str(uuid4()), **item.model_dump(exclude={"parent_external_event_id"}),
                parent_event_id=parent.event_id if parent else None, observed_at=now)
            session.add(event)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Concurrent external event identity conflict; read before retry") from None
            return {"event_id": event.event_id, "duplicate": False, "state": "MANUAL_ASSERTION"}

    @app.post("/v1/costs", dependencies=[Depends(require_manual_authority)])
    def record_cost(item: CostInput):
        with Session(engine) as session:
            if session.get(Experiment, item.experiment_id) is None:
                raise HTTPException(status_code=404, detail="Unknown experiment")
            existing = session.get(ExperimentCost, item.experiment_id)
            if existing:
                if existing.amount_gbp != item.amount_gbp or existing.evidence_ref != item.evidence_ref:
                    raise HTTPException(status_code=409, detail="Conflicting observed cost")
                return {"experiment_id": item.experiment_id, "duplicate": True}
            session.add(ExperimentCost(**item.model_dump(), observed_at=datetime.now(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Concurrent cost identity conflict") from None
        return {"experiment_id": item.experiment_id, "duplicate": False}

    @app.get("/v1/experiments/{experiment_id}/economics", dependencies=[Depends(require_operator)])
    def economics(experiment_id: str):
        with Session(engine) as session:
            if session.get(Experiment, experiment_id) is None:
                raise HTTPException(status_code=404, detail="Unknown experiment")
            net, observed_cost, contribution, candidate, _, _ = economic_projection(session, experiment_id)
            return {"experiment_id": experiment_id, "net_settled_gbp": str(net) if net is not None else None,
                    "observed_cost_gbp": str(observed_cost) if observed_cost is not None else None,
                    "realized_contribution_gbp": str(contribution) if contribution is not None else None,
                    "local_first_pound_candidate": candidate,
                    "commercial_proof": "NOT_PROVEN", "observation_source": "MANUAL_ASSERTION"}

    def economic_projection(session: Session, experiment_id: str):
        events = session.scalars(select(CommerceEvent).where(CommerceEvent.experiment_id == experiment_id)).all()
        cost = session.get(ExperimentCost, experiment_id)
        adjustments = session.scalars(select(ExperimentCostAdjustment).where(
            ExperimentCostAdjustment.experiment_id == experiment_id)).all()
        by_id = {event.event_id: event for event in events}
        valid_orders = {event.event_id for event in events if event.event_type == "ORDER_CREATED" and
            event.parent_event_id in by_id and by_id[event.parent_event_id].event_type == "PUBLISHED"}
        valid_deliveries = {event.parent_event_id for event in events if event.event_type == "DELIVERED" and
            event.parent_event_id in valid_orders}
        valid_settlements = {event.event_id for event in events if event.event_type == 'COMMISSION_SETTLED' and
            event.parent_event_id in valid_deliveries}
        settled = sum((by_id[event_id].amount_gbp for event_id in valid_settlements), Decimal('0'))
        refunds = sum((event.amount_gbp for event in events if event.event_type == 'REFUNDED' and
            event.parent_event_id in valid_settlements), Decimal('0'))
        net = settled - refunds if valid_settlements else None
        observed_cost = cost.amount_gbp + sum((entry.amount_gbp for entry in adjustments), Decimal('0')) if cost else None
        contribution = net - observed_cost if net is not None and observed_cost is not None else None
        mature = bool(valid_settlements) and session.scalar(select(LaunchIntent).where(
            LaunchIntent.experiment_id == experiment_id)) is not None
        candidate = bool(mature and contribution is not None and contribution >= Decimal("1.00"))
        return net, observed_cost, contribution, candidate, any(event.event_type == 'PUBLISHED' for event in events), mature

    @app.get("/v1/portfolio", dependencies=[Depends(require_operator)])
    def portfolio():
        """One durable, read-only projection for Home and Money; no browser assertions."""
        with Session(engine) as session:
            experiments = session.scalars(select(Experiment).order_by(Experiment.created_at)).all()
            results = []
            for experiment in experiments:
                net, observed_cost, contribution, candidate, published, _ = economic_projection(session, experiment.experiment_id)
                results.append({"experimentId": experiment.experiment_id, "decisionId": experiment.decision_id,
                    "productId": experiment.product_id, "creativeId": experiment.creative_id,
                    "publicationObserved": published,
                    "netSettledGbp": str(net) if net is not None else None,
                    "observedCostGbp": str(observed_cost) if observed_cost is not None else None,
                    "realizedContributionGbp": str(contribution) if contribution is not None else None,
                    "firstPoundCandidate": candidate,
                    "commercialProof": "NOT_PROVEN", "source": "MANUAL_ASSERTION"})
            return {"experiments": results, "commercialProof": "NOT_PROVEN",
                "authority": "SERVER_OBSERVATIONS_ONLY"}

    def economic_fingerprint(session, experiment_id):
        events = session.scalars(select(CommerceEvent).where(CommerceEvent.experiment_id == experiment_id)
            .order_by(CommerceEvent.event_id)).all()
        cost = session.get(ExperimentCost, experiment_id)
        adjustments = session.scalars(select(ExperimentCostAdjustment).where(
            ExperimentCostAdjustment.experiment_id == experiment_id).order_by(ExperimentCostAdjustment.adjustment_id)).all()
        facts = [(event.event_id, event.event_type, event.parent_event_id, str(event.amount_gbp)) for event in events]
        facts.extend([('cost', str(cost.amount_gbp) if cost else None)])
        facts.extend((a.adjustment_id, str(a.amount_gbp)) for a in adjustments)
        return hashlib.sha256(json.dumps(facts, separators=(',', ':')).encode()).hexdigest()

    @app.post('/v1/learning', dependencies=[Depends(require_manual_authority)])
    def record_learning(item: LearningInput):
        with Session(engine) as session:
            if session.get(Experiment, item.experiment_id) is None:
                raise HTTPException(404, 'Unknown experiment')
            _, cost, contribution, _, _, mature = economic_projection(session, item.experiment_id)
            if not mature or cost is None or contribution is None:
                raise HTTPException(403, 'Economically mature linked observations and cost required')
            fingerprint = economic_fingerprint(session, item.experiment_id)
            old = session.get(LearningRecord, item.learning_id)
            if old:
                if (old.experiment_id, old.economic_fingerprint, old.contribution_gbp) != (
                    item.experiment_id, fingerprint, contribution):
                    raise HTTPException(409, 'Conflicting or stale learning id')
                return {'learningId': item.learning_id, 'duplicate': True, 'contributionGbp': str(contribution),
                    'source': 'MANUAL_ASSERTION'}
            session.add(LearningRecord(learning_id=item.learning_id, experiment_id=item.experiment_id,
                economic_fingerprint=fingerprint, contribution_gbp=contribution, created_at=datetime.now(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, 'Concurrent learning identity conflict') from None
            return {'learningId': item.learning_id, 'duplicate': False, 'contributionGbp': str(contribution),
                'source': 'MANUAL_ASSERTION'}

    @app.get('/v1/learning', dependencies=[Depends(require_operator)])
    def learning():
        with Session(engine) as session:
            records = session.scalars(select(LearningRecord).order_by(LearningRecord.created_at)).all()
            return {'records': [{'learningId': record.learning_id, 'experimentId': record.experiment_id,
                'contributionGbp': str(record.contribution_gbp),
                'current': record.economic_fingerprint == economic_fingerprint(session, record.experiment_id)}
                for record in records], 'source': 'MANUAL_ASSERTION'}

    @app.post("/v1/cost-adjustments", dependencies=[Depends(require_manual_authority)])
    def add_cost(item: CostAdjustmentInput):
        with Session(engine) as session:
            if session.get(ExperimentCost, item.experiment_id) is None:
                raise HTTPException(status_code=409, detail="Initial observed cost required first")
            existing = session.get(ExperimentCostAdjustment, item.adjustment_id)
            if existing:
                if any(getattr(existing, key) != value for key, value in item.model_dump().items()):
                    raise HTTPException(status_code=409, detail="Conflicting cost adjustment id")
                return {"adjustment_id": item.adjustment_id, "duplicate": True}
            session.add(ExperimentCostAdjustment(**item.model_dump(), observed_at=datetime.now(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Concurrent cost adjustment identity conflict") from None
        return {"adjustment_id": item.adjustment_id, "duplicate": False}

    web_dir = os.environ.get("FRONTEND_DIST_DIR")
    if web_dir:
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
