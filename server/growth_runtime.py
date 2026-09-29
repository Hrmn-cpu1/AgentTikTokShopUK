"""Safe growth runtime quotas and truth-preserving scheduler helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .growth_models import GrowthControl, GrowthQuotaEvent


class QuotaExceeded(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _day_bounds(now: datetime):
    now = now.astimezone(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(day=start.day)  # preserve tzinfo before adding a day
    from datetime import timedelta
    end = start + timedelta(days=1)
    return start, end


def scheduler_enabled(control: GrowthControl) -> bool:
    return bool(control.scheduler_enabled)


def quota_snapshot(session: Session, control: GrowthControl, now: datetime | None = None) -> dict:
    now = now or utcnow()
    start, end = _day_bounds(now)
    def count(kind: str) -> int:
        return session.scalar(select(func.count(GrowthQuotaEvent.event_id)).where(
            GrowthQuotaEvent.event_type == kind,
            GrowthQuotaEvent.occurred_at >= start,
            GrowthQuotaEvent.occurred_at < end,
        )) or 0
    experiments = count("EXPERIMENT")
    handoffs = count("HANDOFF")
    return {
        "dateUtc": start.date().isoformat(),
        "experiments": {"used": experiments, "limit": control.daily_experiment_quota,
                        "remaining": max(0, control.daily_experiment_quota - experiments)},
        "handoffs": {"used": handoffs, "limit": control.daily_handoff_quota,
                     "remaining": max(0, control.daily_handoff_quota - handoffs)},
    }


def reserve_quota(session: Session, *, event_type: str, idempotency_key: str,
                  creative_id: str | None = None, delivery_id: str | None = None,
                  occurred_at: datetime | None = None) -> GrowthQuotaEvent:
    if event_type not in {"EXPERIMENT", "HANDOFF"}:
        raise ValueError("unsupported quota event")
    existing = session.scalar(select(GrowthQuotaEvent).where(
        GrowthQuotaEvent.idempotency_key == idempotency_key))
    if existing is not None:
        return existing

    control = session.get(GrowthControl, "default")
    if control is None:
        raise RuntimeError("growth control is not initialized")
    snapshot = quota_snapshot(session, control, occurred_at or utcnow())
    bucket = snapshot["experiments" if event_type == "EXPERIMENT" else "handoffs"]
    if bucket["remaining"] <= 0:
        raise QuotaExceeded(f"{event_type.lower()} daily quota reached")

    row = GrowthQuotaEvent(
        event_id=str(uuid4()),
        idempotency_key=idempotency_key,
        event_type=event_type,
        creative_id=creative_id,
        delivery_id=delivery_id,
        occurred_at=occurred_at or utcnow(),
    )
    session.add(row)
    session.flush()
    return row
