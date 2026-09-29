"""Reusable Brazil growth cycle and safe scheduler.

The scheduler can discover/create/render experiments, but it cannot cross the human
publication boundary. A new cycle is allowed only after the latest creative has
an Android handoff plus an OWNER_REPORTED publication observation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import threading
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .delivery_models import DeliveryEffect
from .growth_brain import (TrendCandidate, build_creative_plan, canonical_plan,
    choose_hook_family, choose_niche)
from .creative_research import derive_creative_dna
from .growth_models import (FollowerSnapshot, GrowthControl, GrowthCreative, GrowthCreativeDNA, GrowthLearning,
    GrowthObservation, GrowthSchedulerTick, NicheHypothesis, TrendSignal)
from .growth_queue_models import GrowthJob
from .growth_runtime import QuotaExceeded, quota_snapshot, reserve_quota, scheduler_enabled
from .growth_worker import enqueue_job, record_transition
from .trend_sources import rank_public_signal


logger = logging.getLogger(__name__)


class CycleBlocked(RuntimeError):
    def __init__(self, code: str, detail: str, *, status: int = 409):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _control_row(session: Session) -> GrowthControl:
    control = session.get(GrowthControl, "default")
    if control is None:
        control = GrowthControl(control_id="default", mode="READY",
            scheduler_enabled=True, scheduler_interval_seconds=300,
            daily_experiment_quota=3, daily_handoff_quota=3,
            follower_goal=1000, updated_at=utcnow())
        session.add(control)
        session.flush()
    return control


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_follower(session: Session):
    return session.scalar(select(FollowerSnapshot).order_by(
        FollowerSnapshot.observed_at.desc()).limit(1))


def _latest_creative(session: Session):
    return session.scalar(select(GrowthCreative).order_by(
        GrowthCreative.created_at.desc(), GrowthCreative.creative_id.desc()).limit(1))


def _latest_owner_observation(session: Session, creative_id: str):
    return session.scalar(select(GrowthObservation).where(
        GrowthObservation.creative_id == creative_id,
        GrowthObservation.source == "OWNER_TIKTOK_UI",
        GrowthObservation.truth_classification == "OWNER_REPORTED",
        GrowthObservation.publication_identity.is_not(None),
    ).order_by(GrowthObservation.observed_at.desc()).limit(1))


def _latest_delivery(session: Session, creative_id: str):
    return session.scalar(select(DeliveryEffect).where(
        DeliveryEffect.creative_id == creative_id
    ).order_by(DeliveryEffect.created_at.desc()).limit(1))


def cycle_gate(session: Session, *, trigger: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    control = _control_row(session)
    if trigger == "SCHEDULER" and not scheduler_enabled(control):
        return {"allowed": False, "decision": "WAITING", "reason": "SCHEDULER_DISABLED"}
    if control.mode not in {"READY", "RUNNING"}:
        return {"allowed": False, "decision": "WAITING",
                "reason": f"CONTROL_MODE_{control.mode}"}

    pending = session.scalar(select(func.count(GrowthJob.job_id)).where(
        GrowthJob.state.in_(("PENDING", "RETRY", "RUNNING")))) or 0
    if pending:
        return {"allowed": False, "decision": "WAITING", "reason": "DURABLE_JOB_IN_FLIGHT"}

    follower = _latest_follower(session)
    if follower and follower.followers is not None and follower.followers >= control.follower_goal:
        return {"allowed": False, "decision": "GOAL_REACHED", "reason": "FOLLOWER_GOAL_REACHED"}

    quota = quota_snapshot(session, control, now)
    if quota["experiments"]["remaining"] <= 0:
        return {"allowed": False, "decision": "QUOTA_REACHED", "reason": "DAILY_EXPERIMENT_QUOTA_REACHED"}

    latest = _latest_creative(session)
    if latest is None:
        return {"allowed": True, "decision": "STARTED", "reason": "INITIAL_EXPERIMENT", "quota": quota}

    observation = _latest_owner_observation(session, latest.creative_id)
    if observation is None:
        return {"allowed": False, "decision": "WAITING",
                "reason": "HUMAN_PUBLICATION_OBSERVATION_REQUIRED"}
    delivery = _latest_delivery(session, latest.creative_id)
    if delivery is None or delivery.state != "HANDOFF_INITIATED":
        return {"allowed": False, "decision": "WAITING",
                "reason": "ANDROID_HANDOFF_EVIDENCE_REQUIRED"}

    return {"allowed": True, "decision": "STARTED",
            "reason": "LATEST_EXPERIMENT_HAS_HUMAN_EVIDENCE", "quota": quota}


def _unused_learning_mutation(session: Session):
    used_ids = set()
    for plan_json in session.scalars(select(GrowthCreative.plan_json)).all():
        try:
            learning_id = json.loads(plan_json).get("cycle", {}).get("learningId")
        except (TypeError, ValueError):
            learning_id = None
        if learning_id:
            used_ids.add(str(learning_id))
    rows = session.scalars(select(GrowthLearning).where(
        GrowthLearning.verdict == "HYPOTHESIS_READY"
    ).order_by(GrowthLearning.created_at.desc())).all()
    for row in rows:
        if row.learning_id in used_ids:
            continue
        try:
            mutation = json.loads(row.next_mutation_json)
        except (TypeError, ValueError):
            continue
        if mutation.get("variable") == "hookFamily" and mutation.get("to"):
            return row, mutation
    return None, None


def _rank_candidates(source, now: datetime):
    try:
        candidates = source.collect()
    except Exception as exc:
        raise CycleBlocked("TREND_SOURCE_UNAVAILABLE",
                           f"Trend source unavailable: {type(exc).__name__}", status=503) from None
    # Source collection happens after the caller captured `now`; use a fresh
    # wall-clock reading so an item timestamped during collection is not rejected
    # as microscopically "from the future".
    freshness_now = max(now, utcnow())
    fresh = [item for item in candidates if item.market == "BR"
             and item.observed_at.tzinfo is not None
             and 0 <= (freshness_now - item.observed_at.astimezone(timezone.utc)).total_seconds() <= 48 * 3600]
    if not fresh:
        raise CycleBlocked("NO_FRESH_BR_SIGNAL", "No fresh public Brazil trend signals", status=503)
    ranked = sorted(((rank_public_signal(item, now), item) for item in fresh),
                    key=lambda row: (-row[0]["score"], -row[1].observed_at.timestamp(), row[1].trend_id))
    return ranked


def run_growth_cycle(engine, source, *, trigger: str = "MANUAL") -> dict:
    if trigger not in {"MANUAL", "SCHEDULER"}:
        raise ValueError("unsupported cycle trigger")
    now = utcnow()
    with Session(engine) as session:
        gate = cycle_gate(session, trigger=trigger, now=now)
        if not gate["allowed"]:
            if trigger == "MANUAL" and gate["reason"] in {
                    "DURABLE_JOB_IN_FLIGHT", "HUMAN_PUBLICATION_OBSERVATION_REQUIRED",
                    "ANDROID_HANDOFF_EVIDENCE_REQUIRED", "CONTROL_MODE_ACTION_REQUIRED"}:
                current = _latest_creative(session)
                if current is not None:
                    job = session.scalar(select(GrowthJob).where(
                        GrowthJob.creative_id == current.creative_id
                    ).order_by(GrowthJob.created_at.desc()).limit(1))
                    try:
                        plan = json.loads(current.plan_json)
                    except (TypeError, ValueError):
                        plan = {}
                    return {
                        "state": current.state,
                        "duplicate": True,
                        "creativeId": current.creative_id,
                        "experimentId": current.experiment_id,
                        "market": "BR",
                        "plan": plan,
                        "jobState": job.state if job else "UNKNOWN",
                        "videoUrl": f"/v1/growth/creatives/{current.creative_id}/video",
                        "delivery": {"status": "NOT_SENT", "publication": "UNKNOWN"},
                        "reason": gate["reason"],
                    }
            raise CycleBlocked(gate["reason"], gate["reason"])

    ranked = _rank_candidates(source, now)
    ranking = [{"trendId": item.trend_id, "topic": item.topic, **score}
               for score, item in ranked[:20]]
    chosen_score, chosen = ranked[0]
    metrics = dict(chosen.metrics)
    metrics["ranking"] = chosen_score

    with Session(engine) as session:
        control = session.scalar(select(GrowthControl).where(
            GrowthControl.control_id == "default").with_for_update())
        if control is None:
            control = _control_row(session)
        gate = cycle_gate(session, trigger=trigger, now=now)
        if not gate["allowed"]:
            raise CycleBlocked(gate["reason"], gate["reason"])

        trend = session.get(TrendSignal, chosen.trend_id)
        if trend is None:
            trend = TrendSignal(
                trend_id=chosen.trend_id,
                source=chosen.source,
                source_ref=chosen.source_ref,
                topic=chosen.topic[:300],
                market="BR",
                language=chosen.language,
                metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")),
                evidence=chosen.evidence,
                observed_at=chosen.observed_at.astimezone(timezone.utc),
            )
            session.add(trend)
            session.flush()

        candidate = TrendCandidate(topic=chosen.topic, source=chosen.source,
            source_ref=chosen.source_ref, evidence=chosen.evidence, metrics=metrics)
        all_creatives = session.scalars(select(GrowthCreative).order_by(
            GrowthCreative.created_at)).all()
        niche_counts = Counter()
        for previous in all_creatives:
            if previous.niche_id.startswith("niche-"):
                niche_counts[previous.niche_id.removeprefix("niche-")] += 1
        niche_name = choose_niche(candidate, dict(niche_counts))
        niche_id = "niche-" + niche_name
        niche = session.get(NicheHypothesis, niche_id)
        if niche is None:
            niche = NicheHypothesis(
                niche_id=niche_id, market="BR", language="pt-BR",
                hypothesis=f"Testar conteúdo original {niche_name} com evidência pública no Brasil",
                trend_evidence=chosen.source_ref, production_cost_centavos=0,
                risk="LOW", status="EXPLORING", created_at=now)
            session.add(niche)

        same_topic = [previous for previous in all_creatives
                      if previous.trend_id == chosen.trend_id]
        hook_counts = Counter()
        for previous in same_topic:
            try:
                hook_counts[json.loads(previous.plan_json).get("hookFamily", "question")] += 1
            except (TypeError, ValueError):
                hook_counts["question"] += 1

        recent_learning_rows = session.scalars(select(GrowthLearning).order_by(
            GrowthLearning.created_at.desc()).limit(24)).all()
        research_learnings = []
        for row in recent_learning_rows:
            try:
                next_mutation = json.loads(row.next_mutation_json)
            except (TypeError, ValueError):
                next_mutation = {}
            research_learnings.append({
                "learningId": row.learning_id,
                "verdict": row.verdict,
                "rationale": row.rationale,
                "nextMutation": next_mutation,
            })
        creative_dna = derive_creative_dna(research_learnings)

        learning, mutation = _unused_learning_mutation(session)
        learned_hook = mutation.get("to") if mutation else creative_dna.get("patterns", {}).get("hook", {}).get("familyHint")
        if learned_hook:
            hook_family = str(learned_hook)
            learning_id = learning.learning_id if learning is not None else None
            mutation_mode = "EVIDENCE_BACKED_HYPOTHESIS" if learning is not None else "OWN_RESULTS_MEMORY"
        else:
            hook_family = choose_hook_family(candidate, dict(hook_counts))
            learning_id = None
            mutation_mode = "DETERMINISTIC_EXPLORATION"

        plan = build_creative_plan(candidate, niche_name, hook_family, creative_dna=creative_dna)
        plan["sourceEvidence"].update({
            "geography": chosen.geography,
            "collectedAt": chosen.collected_at.isoformat(),
            "observedAt": chosen.observed_at.isoformat(),
            "rankingComponents": chosen_score["components"],
            "rankingScore": chosen_score["score"],
            "selectionReason": "fresh BR public-search signal selected for topic; creative form learned from public official BR references and own eligible results when available; TikTok organic engagement remains UNKNOWN",
            "hookFamily": hook_family,
            "hookSelection": mutation_mode,
        })
        sequence = len(all_creatives) + 1
        identity_material = f"{chosen.trend_id}|{sequence}|{hook_family}|{trigger}|{now.isoformat()}"
        identity = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:24]
        creative_id = "creative-br-" + identity
        experiment_id = "experiment-br-" + identity
        plan["cycle"] = {
            "sequence": sequence,
            "trigger": trigger,
            "mutationMode": mutation_mode,
            "learningId": learning_id,
            "learningVerdictRequiredForMutation": "HYPOTHESIS_READY",
            "oneVideoIsLearning": False,
        }

        creative = GrowthCreative(
            creative_id=creative_id,
            niche_id=niche_id,
            trend_id=chosen.trend_id,
            experiment_id=experiment_id,
            plan_json=canonical_plan(plan),
            evidence_ref=chosen.source_ref,
            state="SCRIPTED",
            purpose="EXPERIMENT",
            creative_learning_eligible=False,
            style_baseline_eligible=False,
            exclusion_reason="AWAITING_QUALITY_POLICY_PUBLICATION_AND_OBSERVATION",
            quality_status="NOT_EVALUATED",
            quality_json="{}",
            policy_status="NOT_EVALUATED",
            created_at=now,
        )
        session.add(creative)
        session.flush()
        dna_row = GrowthCreativeDNA(
            dna_id=str(uuid4()),
            creative_id=creative_id,
            source_priority=creative_dna["sourcePriority"],
            references_json=json.dumps(creative_dna["publicReferences"], ensure_ascii=False, sort_keys=True),
            patterns_json=json.dumps(creative_dna["patterns"], ensure_ascii=False, sort_keys=True),
            evidence_digest=creative_dna["evidenceDigest"],
            created_at=now,
        )
        session.add(dna_row)
        session.flush()
        try:
            reserve_quota(session, event_type="EXPERIMENT",
                          idempotency_key="experiment:" + creative_id,
                          creative_id=creative_id, occurred_at=now)
        except QuotaExceeded as exc:
            session.rollback()
            raise CycleBlocked("DAILY_EXPERIMENT_QUOTA_REACHED", str(exc)) from None

        job = enqueue_job(session, creative_id, "PREPARE_ASSETS")
        record_transition(session, "SCRIPTED", "QUEUED",
                          f"{trigger.lower()} cycle queued original render job",
                          experiment_id, job.job_id)
        control.mode = "RUNNING"
        control.updated_at = now
        session.commit()
        return {
            "state": creative.state,
            "duplicate": False,
            "creativeId": creative_id,
            "experimentId": experiment_id,
            "source": chosen.source,
            "market": "BR",
            "geography": chosen.geography,
            "languageSignal": chosen.language,
            "ranking": ranking,
            "selected": {"trendId": chosen.trend_id, "topic": chosen.topic,
                         "score": chosen_score["score"],
                         "components": chosen_score["components"]},
            "plan": plan,
            "jobId": job.job_id,
            "jobState": "PENDING",
            "videoUrl": f"/v1/growth/creatives/{creative_id}/video",
            "trigger": trigger,
            "learningApplied": learning_id,
            "creativeDNAId": dna_row.dna_id,
            "creativeDNA": creative_dna,
            "delivery": {"status": "NOT_SENT", "publication": "UNKNOWN"},
        }


def record_scheduler_tick(session: Session, *, decision: str, reason: str,
                          creative_id: str | None = None, now: datetime | None = None):
    now = now or utcnow()
    row = GrowthSchedulerTick(
        tick_id=str(uuid4()), decision=decision, reason=reason[:200],
        creative_id=creative_id, observed_at=now)
    session.add(row)
    control = session.get(GrowthControl, "default")
    if control is not None:
        control.last_scheduler_tick_at = now
        control.updated_at = now
    session.flush()
    return row


def run_scheduler_tick(engine, source) -> dict:
    now = utcnow()
    with Session(engine) as session:
        control = session.get(GrowthControl, "default")
        if control is None:
            return {"decision": "BLOCKED", "reason": "CONTROL_NOT_INITIALIZED"}
        effective_enabled = scheduler_enabled(control)
        if not effective_enabled:
            record_scheduler_tick(session, decision="WAITING", reason="SCHEDULER_DISABLED", now=now)
            session.commit()
            return {"decision": "WAITING", "reason": "SCHEDULER_DISABLED"}
        if control.last_scheduler_tick_at:
            last = _aware(control.last_scheduler_tick_at)
            if now - last < timedelta(seconds=control.scheduler_interval_seconds):
                return {"decision": "WAITING", "reason": "SCHEDULER_INTERVAL_NOT_ELAPSED"}
        gate = cycle_gate(session, trigger="SCHEDULER", now=now)
        if not gate["allowed"]:
            record_scheduler_tick(session, decision=gate["decision"], reason=gate["reason"], now=now)
            session.commit()
            return {"decision": gate["decision"], "reason": gate["reason"]}
        # Reserve the cadence slot before public-source I/O; cycle_gate is rechecked later.
        control.last_scheduler_tick_at = now
        session.commit()

    try:
        cycle = run_growth_cycle(engine, source, trigger="SCHEDULER")
    except CycleBlocked as exc:
        with Session(engine) as session:
            decision = "BLOCKED" if exc.status >= 500 else "WAITING"
            record_scheduler_tick(session, decision=decision, reason=exc.code, now=utcnow())
            session.commit()
        return {"decision": decision, "reason": exc.code}

    with Session(engine) as session:
        record_scheduler_tick(session, decision="STARTED", reason="SAFE_NEXT_EXPERIMENT_STARTED",
                              creative_id=cycle["creativeId"], now=utcnow())
        session.commit()
    return {"decision": "STARTED", "reason": "SAFE_NEXT_EXPERIMENT_STARTED",
            "creativeId": cycle["creativeId"], "experimentId": cycle["experimentId"]}


def run_growth_scheduler(engine, source, stop: threading.Event, poll_seconds: float = 60.0):
    """Poll scheduler state; never dispatch or publish to TikTok."""
    poll_seconds = max(60.0, float(poll_seconds))
    while not stop.wait(poll_seconds):
        try:
            run_scheduler_tick(engine, source)
        except Exception:
            logger.exception("Safe growth scheduler tick failed")
