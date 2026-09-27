"""One-operator, manual observation API. It never publishes or spends externally."""
import hmac
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import CommerceEvent, Experiment, ExperimentCost, ExperimentCostAdjustment


Money = Decimal


class ExperimentInput(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    decision_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(min_length=1, max_length=100)
    publication_action_id: str = Field(min_length=1, max_length=100)
    authority_evidence_ref: str = Field(min_length=6, max_length=500)
    market: Literal["UK"] = "UK"
    currency: Literal["GBP"] = "GBP"


class EventInput(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    action_id: str = Field(min_length=1, max_length=100)
    source: Literal["MANUAL_VERIFIED"] = "MANUAL_VERIFIED"
    external_event_id: str = Field(min_length=1, max_length=200)
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


def create_app(database_url: str | None = None, operator_token: str | None = None) -> FastAPI:
    url = database_url or os.environ.get("DATABASE_URL")
    token = operator_token or os.environ.get("OPERATOR_API_TOKEN")
    if not url or not token or len(token) < 32:
        raise RuntimeError("DATABASE_URL and a strong OPERATOR_API_TOKEN are required")
    engine = create_engine(url, pool_pre_ping=True)
    app = FastAPI(title="TikTok Shop UK Observation API")
    security = HTTPBearer(auto_error=False)

    def require_operator(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
        if credentials is None or not hmac.compare_digest(credentials.credentials, token):
            raise HTTPException(status_code=401, detail="Operator authentication required")

    @app.get("/health")
    def health():
        return {"status": "up"}

    @app.post("/v1/experiments", dependencies=[Depends(require_operator)])
    def record_experiment(item: ExperimentInput):
        with Session(engine) as session:
            existing = session.get(Experiment, item.experiment_id)
            if existing:
                current = {k: getattr(existing, k) for k in type(item).model_fields}
                if current != item.model_dump():
                    raise HTTPException(status_code=409, detail="Conflicting experiment identity")
                return {"experiment_id": item.experiment_id, "duplicate": True, "state": "MANUAL_ASSERTION"}
            session.add(Experiment(**item.model_dump(), created_at=datetime.now(timezone.utc)))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Conflicting experiment or action identity") from None
        return {"experiment_id": item.experiment_id, "duplicate": False, "state": "MANUAL_ASSERTION"}

    @app.post("/v1/events", dependencies=[Depends(require_operator)])
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
            existing = session.scalar(select(CommerceEvent).where(
                CommerceEvent.source == item.source, CommerceEvent.external_event_id == item.external_event_id))
            if existing:
                fields = item.model_dump()
                if any(getattr(existing, key) != value for key, value in fields.items() if key != "occurred_at") or \
                        existing.occurred_at.replace(tzinfo=timezone.utc) != item.occurred_at:
                    raise HTTPException(status_code=409, detail="Conflicting external event id")
                return {"event_id": existing.event_id, "duplicate": True, "state": "MANUAL_ASSERTION"}
            if item.event_type == "PUBLISHED" and session.scalar(select(CommerceEvent.event_id).where(
                CommerceEvent.experiment_id == item.experiment_id, CommerceEvent.event_type == "PUBLISHED")) is not None:
                raise HTTPException(status_code=409, detail="Publication already observed; reconcile before retry")
            if item.event_type != "PUBLISHED" and session.scalar(select(CommerceEvent.event_id).where(
                CommerceEvent.experiment_id == item.experiment_id, CommerceEvent.event_type == "PUBLISHED")) is None:
                raise HTTPException(status_code=409, detail="Publication observation required first")
            event = CommerceEvent(event_id=str(uuid4()), **item.model_dump(), observed_at=now)
            session.add(event)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="Concurrent external event identity conflict; read before retry") from None
            return {"event_id": event.event_id, "duplicate": False, "state": "MANUAL_ASSERTION"}

    @app.post("/v1/costs", dependencies=[Depends(require_operator)])
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
            events = session.scalars(select(CommerceEvent).where(CommerceEvent.experiment_id == experiment_id)).all()
            cost = session.get(ExperimentCost, experiment_id)
            adjustments = session.scalars(select(ExperimentCostAdjustment).where(
                ExperimentCostAdjustment.experiment_id == experiment_id)).all()
            types = {event.event_type for event in events}
            mature = {"PUBLISHED", "ORDER_CREATED", "DELIVERED", "COMMISSION_SETTLED"}.issubset(types)
            settled = sum((event.amount_gbp for event in events if event.event_type == "COMMISSION_SETTLED"), Decimal("0"))
            refunds = sum((event.amount_gbp for event in events if event.event_type == "REFUNDED"), Decimal("0"))
            net = max(Decimal("0"), settled - refunds) if "COMMISSION_SETTLED" in types else None
            observed_cost = cost.amount_gbp + sum((entry.amount_gbp for entry in adjustments), Decimal("0")) if cost else None
            contribution = net - observed_cost if net is not None and observed_cost is not None else None
            return {"experiment_id": experiment_id, "net_settled_gbp": str(net) if net is not None else None,
                    "observed_cost_gbp": str(observed_cost) if observed_cost is not None else None,
                    "realized_contribution_gbp": str(contribution) if contribution is not None else None,
                    "local_first_pound_candidate": bool(mature and contribution is not None and contribution >= Decimal("1.00")),
                    "commercial_proof": "NOT_PROVEN", "observation_source": "MANUAL_ASSERTION"}

    @app.post("/v1/cost-adjustments", dependencies=[Depends(require_operator)])
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

    return app
