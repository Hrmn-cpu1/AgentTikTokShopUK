"""Authenticated durable API for Brazil growth experiments. No publishing side effect."""
import json
import os
from collections import Counter
from datetime import timedelta
from typing import Literal
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .growth_brain import TrendCandidate, build_creative_plan, canonical_plan, choose_niche, trend_score, choose_hook_family
from .growth_models import (GrowthCreative, GrowthControl, GrowthLearning, GrowthObservation,
    FollowerSnapshot, NicheHypothesis, PublicationIntent, TrendSignal, GrowthStateTransition,
    GrowthMediaArtifact)
from .growth_queue_models import GrowthJob
from .growth_worker import enqueue_job, record_transition
from .growth_learning import eligible_for_comparison, compare_hook_families
from .models import TikTokConnection
from .delivery_models import DeliveryEffect
from .trend_sources import GoogleTrendsBrazilRSS, rank_public_signal
from .media_storage import (MediaArtifactCorrupt, MediaArtifactMissing,
    MediaStorageError, MediaStorageNotConfigured, RailwayVolumeMediaStore)

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

class ObservationInput(BaseModel):
    observation_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(min_length=1, max_length=100)
    source: Literal["OWNER_TIKTOK_UI"]
    publication_identity: str = Field(min_length=10, max_length=500)
    truth_classification: Literal["OWNER_REPORTED"] = "OWNER_REPORTED"
    evidence_ref: str = Field(min_length=6, max_length=1000)
    observed_at: datetime
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_before: int | None = Field(default=None, ge=0)
    followers_after: int | None = Field(default=None, ge=0)

def add_growth_routes(app, engine, require_operator, trend_source=None, media_store=None):
    source = trend_source or GoogleTrendsBrazilRSS()

    def control_row(session):
        control = session.get(GrowthControl, "default")
        if control is None:
            control = GrowthControl(control_id="default", mode="READY", updated_at=datetime.now(timezone.utc))
            session.add(control)
            session.flush()
        return control

    @app.get("/v1/growth/observation-capabilities", dependencies=[Depends(require_operator)])
    def observation_capabilities():
        with Session(engine) as session:
            connection = session.scalar(select(TikTokConnection).where(TikTokConnection.operator_id == "primary"))
            granted = set()
            if connection and connection.granted_scopes:
                granted = set(connection.granted_scopes.replace(",", " ").split())
        active = bool(connection and connection.status == "ACTIVE")
        return {"currentGrantedScopes": sorted(granted),
            "identity": "AVAILABLE" if active else "UNKNOWN",
            "followerCount": "AVAILABLE" if active and "user.info.stats" in granted else "REQUIRES_APPROVAL",
            "publicVideoMetrics": "AVAILABLE" if active and "video.list" in granted else "REQUIRES_APPROVAL",
            "watchTimeAndRetention": "UNKNOWN",
            "reason": "user.info.basic alone returns identity fields; profile statistics and the video list require their own authorized scopes.",
            "sources": ["https://developers.tiktok.com/docs/en/tiktok-api-scopes",
                "https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info",
                "https://developers.tiktok.com/docs/en/tiktok-api-v2-video-list"]}

    @app.get("/v1/public/mrwho/feed")
    def mrwho_public_feed():
        """Minimal read model: no operator, token, job, trend-evidence or debug data."""
        with Session(engine) as session:
            creatives = session.scalars(select(GrowthCreative).where(
                GrowthCreative.mrwho_public.is_(True),
                GrowthCreative.purpose == "EXPERIMENT",
                GrowthCreative.quality_status == "QUALITY_PASS",
                GrowthCreative.creative_learning_eligible.is_(True),
            ).order_by(GrowthCreative.created_at.desc()).limit(24)).all()
            items = []
            for creative in creatives:
                observation = session.scalar(select(GrowthObservation).where(
                    GrowthObservation.creative_id == creative.creative_id,
                    GrowthObservation.truth_classification == "OWNER_REPORTED"
                ).order_by(GrowthObservation.observed_at.desc()).limit(1))
                if not observation or not observation.publication_identity:
                    continue
                plan = json.loads(creative.plan_json)
                items.append({"id": creative.creative_id, "title": str(plan.get("topic", ""))[:120],
                    "hook": str(plan.get("hook", ""))[:140], "tiktokUrl": observation.publication_identity,
                    "publishedAt": observation.observed_at.isoformat()})
        return {"brand": "Mr.Who?", "commerceEnabled": False, "items": items}

    @app.get("/mr-who", response_class=HTMLResponse)
    def mrwho_public_home():
        return HTMLResponse("""<!doctype html><html lang='pt-BR'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Mr.Who?</title><style>body{margin:0;background:#080b12;color:#f7f8fc;font:16px system-ui}main{max-width:680px;margin:auto;padding:32px 18px}h1{font-size:42px;margin:0;color:#ff1685}article{padding:16px;margin:14px 0;border:1px solid #293140;border-radius:18px;background:#101722}a{color:#62e9e7}.muted{color:#aab4c4}</style><main><p class='muted'>CONTEÚDO ORIGINAL · BRASIL</p><h1>Mr.Who?</h1><p class='muted'>Curiosidade, descoberta e ideias originais em vídeos curtos.</p><section id='feed'><p class='muted'>Carregando conteúdo público elegível…</p></section><p class='muted'>Comércio TikTok Shop: desativado.</p></main><script>fetch('/v1/public/mrwho/feed').then(r=>r.json()).then(d=>{const root=document.querySelector('#feed');root.replaceChildren();if(!d.items.length){root.textContent='Nenhum conteúdo público elegível disponível ainda.';return}for(const item of d.items){const card=document.createElement('article'),title=document.createElement('h2'),hook=document.createElement('p'),link=document.createElement('a');title.textContent=item.title;hook.textContent=item.hook;link.href=item.tiktokUrl;link.rel='noopener noreferrer';link.textContent='Assistir no TikTok';card.append(title,hook,link);root.append(card)}}).catch(()=>{document.querySelector('#feed').textContent='Feed público indisponível no momento.'})</script></html>""")

    @app.post("/v1/growth/observations", dependencies=[Depends(require_operator)])
    def record_growth_observation(item: ObservationInput):
        if item.observed_at.tzinfo is None or item.observed_at.utcoffset() is None:
            raise HTTPException(422, "observed_at needs an explicit timezone")
        observed_at = item.observed_at.astimezone(timezone.utc)
        if observed_at > datetime.now(timezone.utc):
            raise HTTPException(422, "Future observation is not accepted")
        metrics = (item.views, item.likes, item.comments, item.shares, item.followers_before, item.followers_after)
        if all(value is None for value in metrics):
            raise HTTPException(422, "At least one observed metric is required; absent metrics remain UNKNOWN")
        with Session(engine) as session:
            creative = session.get(GrowthCreative, item.creative_id)
            if not creative:
                raise HTTPException(404, "Unknown creative")
            old = session.get(GrowthObservation, item.observation_id)
            expected = item.model_dump()
            expected["observed_at"] = observed_at
            if old:
                actual = {key: getattr(old, key) for key in expected}
                stored_at = actual.get("observed_at")
                if stored_at is not None and (stored_at.tzinfo is None or stored_at.utcoffset() is None):
                    actual["observed_at"] = stored_at.replace(tzinfo=timezone.utc)
                elif stored_at is not None:
                    actual["observed_at"] = stored_at.astimezone(timezone.utc)
                if actual != expected:
                    raise HTTPException(409, "Conflicting observation identity")
                return {"observationId": old.observation_id, "duplicate": True,
                    "truth": old.truth_classification, "learningEligibility": "NOT_RECOMPUTED"}
            session.add(GrowthObservation(observation_id=item.observation_id, creative_id=item.creative_id,
                views=item.views, likes=item.likes, comments=item.comments, shares=item.shares,
                followers_before=item.followers_before, followers_after=item.followers_after,
                source=item.source, publication_identity=item.publication_identity,
                truth_classification=item.truth_classification, evidence_ref=item.evidence_ref,
                observed_at=observed_at))
            session.flush()
            can_compare, exclusion = eligible_for_comparison(
                quality_status=creative.quality_status, purpose=creative.purpose, source=item.source,
                truth_classification=item.truth_classification, publication_identity=item.publication_identity,
                evidence_ref=item.evidence_ref, views=item.views, observed_at=observed_at,
                created_at=creative.created_at if creative.created_at.tzinfo else creative.created_at.replace(tzinfo=timezone.utc))
            creative.creative_learning_eligible = can_compare
            creative.style_baseline_eligible = False
            creative.exclusion_reason = None if can_compare else exclusion

            rows = session.execute(select(GrowthObservation, GrowthCreative, TrendSignal)
                .join(GrowthCreative, GrowthObservation.creative_id == GrowthCreative.creative_id)
                .join(TrendSignal, GrowthCreative.trend_id == TrendSignal.trend_id)).all()
            by_comparison: dict[tuple[str, str, str, int], list[dict]] = {}
            for observation, candidate_creative, trend in rows:
                plan = json.loads(candidate_creative.plan_json)
                sample_ok, _ = eligible_for_comparison(
                    quality_status=candidate_creative.quality_status, purpose=candidate_creative.purpose,
                    source=observation.source, truth_classification=observation.truth_classification,
                    publication_identity=observation.publication_identity, evidence_ref=observation.evidence_ref,
                    views=observation.views, observed_at=observation.observed_at,
                    created_at=candidate_creative.created_at if candidate_creative.created_at.tzinfo else candidate_creative.created_at.replace(tzinfo=timezone.utc))
                rate = None
                if sample_ok and observation.views and all(value is not None for value in
                    (observation.likes, observation.comments, observation.shares)):
                    rate = (observation.likes + observation.comments + observation.shares) / observation.views
                style = plan.get("creativeStyle", {})
                key = (trend.topic.casefold(), str(style.get("styleId", "")),
                       str(style.get("styleVersion", "")), len(plan.get("scenePlan", [])))
                by_comparison.setdefault(key, []).append({"eligible": sample_ok,
                    "topic": trend.topic.casefold(), "hookFamily": plan.get("hookFamily"),
                    "engagementRate": rate, "creativeId": candidate_creative.creative_id,
                    "experimentId": candidate_creative.experiment_id, "evidenceRef": observation.evidence_ref})
            learning_result = {"verdict": "INSUFFICIENT_EVIDENCE", "nextMutation": {},
                "rationale": exclusion if not can_compare else "One eligible observation cannot establish a repeatable comparison."}
            if can_compare:
                comparisons = [compare_hook_families(samples) for samples in by_comparison.values()]
                learning_result = next((result for result in comparisons if result["verdict"] == "HYPOTHESIS_READY"),
                    {"verdict": "INSUFFICIENT_EVIDENCE", "nextMutation": {},
                     "rationale": "Insufficient replicated observations; no style change is justified."})
            learning_id = "learning-" + item.observation_id
            session.add(GrowthLearning(learning_id=learning_id, creative_id=item.creative_id,
                verdict=learning_result["verdict"], rationale=learning_result["rationale"],
                next_mutation_json=json.dumps(learning_result["nextMutation"], ensure_ascii=False, sort_keys=True),
                created_at=datetime.now(timezone.utc)))
            record_transition(session, "OBSERVED", "LEARNING_ELIGIBLE" if can_compare else "OBSERVED_BUT_NOT_LEARNING_ELIGIBLE",
                learning_result["rationale"], creative.experiment_id)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Concurrent observation or learning identity conflict") from None
            return {"observationId": item.observation_id, "duplicate": False,
                "truth": "OWNER_REPORTED", "learningEligibility": "ELIGIBLE_FOR_COMPARISON" if can_compare else "OBSERVED_BUT_NOT_LEARNING_ELIGIBLE",
                "exclusionReason": None if can_compare else exclusion,
                "learning": learning_result}

    @app.get("/v1/growth/control", dependencies=[Depends(require_operator)])
    def get_growth_control():
        with Session(engine) as session:
            control = control_row(session)
            session.commit()
            return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                "scheduler": "NOT_CONFIGURED"}

    @app.post("/v1/growth/control", dependencies=[Depends(require_operator)])
    def set_growth_control(payload: dict):
        action = payload.get("action")
        if action not in {"START", "PAUSE", "EMERGENCY_STOP"}:
            raise HTTPException(422, "action must be START, PAUSE, or EMERGENCY_STOP")
        now = datetime.now(timezone.utc)
        should_discover = False
        old_mode = "READY"
        with Session(engine) as session:
            control = control_row(session)
            old_mode = control.mode
            if action == "START" and old_mode == "RUNNING":
                return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                    "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                    "scheduler": "NOT_CONFIGURED", "duplicate": True, "cycle": {"state":"ALREADY_RUNNING"}}
            if action == "PAUSE" and old_mode == "PAUSED":
                return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                    "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                    "scheduler": "NOT_CONFIGURED", "duplicate": True}
            if action == "EMERGENCY_STOP" and old_mode == "STOPPED":
                return {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                    "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                    "scheduler": "NOT_CONFIGURED", "duplicate": True}
            if action == "START":
                if old_mode == "STOPPED":
                    raise HTTPException(409, "Emergency Stop is latched; operator reset required")
                if old_mode in {"ACTION_REQUIRED", "BLOCKED", "FAILED"}:
                    raise HTTPException(409, f"Resolve {old_mode} before starting another run")
                pending = session.scalar(select(func.count(GrowthJob.job_id)).where(
                    GrowthJob.state.in_(["PENDING", "RETRY", "RUNNING"]))) or 0
                previous = session.scalar(select(func.count(GrowthCreative.creative_id))) or 0
                should_discover = old_mode != "RUNNING" and pending == 0 and previous == 0
                if old_mode == "RUNNING":
                    control.mode = "RUNNING"
                elif pending == 0 and previous > 0:
                    control.mode = "ACTION_REQUIRED"
                else:
                    control.mode = "RUNNING"
            elif action == "PAUSE":
                if old_mode == "STOPPED":
                    raise HTTPException(409, "Emergency Stop is latched")
                control.mode = "PAUSED"
            else:
                control.mode = "STOPPED"
            control.updated_at = now
            if action == "EMERGENCY_STOP":
                jobs = session.scalars(select(GrowthJob).where(GrowthJob.state.in_(["PENDING", "RETRY", "RUNNING"]))).all()
                for job in jobs:
                    job.state = "BLOCKED"
                    job.last_error = "Blocked by operator emergency stop"
                    job.lease_owner = None
                    job.lease_until = None
                    job.updated_at = now
            record_transition(session, old_mode, control.mode,
                {"START":"operator start/resume requested", "PAUSE":"operator pause requested",
                 "EMERGENCY_STOP":"latched operator kill switch"}[action])
            session.commit()
            response = {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                "scheduler": "NOT_CONFIGURED"}
        if action == "START" and should_discover:
            try:
                response["cycle"] = run_first_experiment()
            except HTTPException as exc:
                with Session(engine) as session:
                    control = session.get(GrowthControl, "default")
                    if control and control.mode == "RUNNING":
                        old = control.mode
                        control.mode = "BLOCKED" if exc.status_code in {409, 503} else "FAILED"
                        control.updated_at = datetime.now(timezone.utc)
                        record_transition(session, old, control.mode, "initial discovery could not start")
                        session.commit()
                raise
        elif action == "START":
            response["cycle"] = {"state": "ALREADY_RUNNING" if old_mode == "RUNNING" else
                "RESUMING_DURABLE_QUEUE" if old_mode == "PAUSED" and response["mode"] == "RUNNING" else "ACTION_REQUIRED",
                "detail": "No new experiment is created without an evidence-backed next mutation."}
        return response

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
            artifacts = session.scalars(select(GrowthMediaArtifact).order_by(
                GrowthMediaArtifact.created_at.desc())).all()
            artifacts_by_creative = {}
            for artifact in artifacts:
                artifacts_by_creative.setdefault(artifact.creative_id, artifact)
            deliveries = session.scalars(select(DeliveryEffect).order_by(
                DeliveryEffect.created_at.desc())).all()
            deliveries_by_creative = {}
            for delivery in deliveries:
                deliveries_by_creative.setdefault(delivery.creative_id, delivery)
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
                delivery = deliveries_by_creative.get(creative.creative_id)
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
                    "delivery": {"state": delivery.state if delivery else
                            (intent.provider_status if intent else "NOT_REQUESTED"),
                        "provider": delivery.provider if delivery else (intent.provider if intent else None),
                        "providerId": delivery.provider_reference if delivery else
                            (intent.provider_publish_id if intent else None),
                        "deliveryId": delivery.delivery_id if delivery else None,
                        "actionContractId": delivery.action_contract_id if delivery else None,
                        "effectId": delivery.effect_id if delivery else None},
                    "quality": {"status": creative.quality_status, "details": json.loads(creative.quality_json)},
                    "purpose": creative.purpose, "creativeLearningEligible": creative.creative_learning_eligible,
                    "styleBaselineEligible": creative.style_baseline_eligible,
                    "exclusionReason": creative.exclusion_reason,
                    "observation": None if observation is None else {"source": observation.source,
                        "evidenceRef": observation.evidence_ref, "observedAt": observation.observed_at.isoformat(),
                        "views": observation.views, "likes": observation.likes, "comments": observation.comments,
                        "shares": observation.shares, "followersBefore": observation.followers_before,
                        "followersAfter": observation.followers_after},
                    "learning": None if learning is None else {"verdict": learning.verdict, "rationale": learning.rationale,
                        "nextMutation": json.loads(learning.next_mutation_json), "createdAt": learning.created_at.isoformat()}}
                experiment_items.append(record)
                if creative.media_hash:
                    artifact = artifacts_by_creative.get(creative.creative_id)
                    media_items.append({"creativeId": creative.creative_id, "experimentId": creative.experiment_id,
                        "topic": record["topic"], "state": creative.state, "mediaHash": creative.media_hash,
                        "artifactId": artifact.artifact_id if artifact else None,
                        "storageState": artifact.storage_state if artifact else "UNKNOWN",
                        "mediaReady": bool(artifact and artifact.storage_state == "STORED_VERIFIED"
                                           and artifact.quality_status == "QUALITY_PASS"),
                        "deliveryId": delivery.delivery_id if delivery else None,
                        "deliveryState": delivery.state if delivery else "NOT_PREPARED",
                        "actionContractId": delivery.action_contract_id if delivery else None,
                        "effectId": delivery.effect_id if delivery else None,
                        "createdAt": creative.created_at.isoformat(), "videoUrl": f"/v1/growth/creatives/{creative.creative_id}/video"})
            observations_count = total_observations
            follower_snapshot = followers[0] if followers else None
            current_job = next((job for job in jobs if job.state in {"PENDING", "RETRY", "RUNNING"}), None)
            now_utc = datetime.now(timezone.utc)
            lease_expiry = current_job.lease_until if current_job else None
            if lease_expiry is not None and lease_expiry.tzinfo is None:
                lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
            lease_expired = bool(current_job and current_job.state == "RUNNING" and
                (not lease_expiry or not current_job.lease_owner or not current_job.lease_attempt_id
                 or lease_expiry <= now_utc))
            latest_creative = creatives[0] if creatives else None
            if lease_expired:
                current_activity = "Worker sem heartbeat válido; aguardando recuperação da lease"
            elif control.mode == "RUNNING":
                current_activity = {
                    "PREPARE_ASSETS": "Preparando ativos originais",
                    "RENDER_VIDEO": "Renderizando o vídeo", "DELIVERY_ACTION_REQUIRED": "Aguardando sua confirmação"}.get(
                        current_job.job_type if current_job else "", "Iniciando descoberta de tendências")
            elif control.mode == "ACTION_REQUIRED":
                current_activity = "Vídeo pronto; falta a confirmação de entrega no TikTok"
            elif control.mode == "PAUSED":
                current_activity = "Agente pausado com estado preservado"
            elif control.mode == "STOPPED":
                current_activity = "Parada de emergência ativada"
            elif control.mode == "BLOCKED":
                current_activity = "Execução bloqueada; consulte os detalhes do sistema"
            elif control.mode == "FAILED":
                current_activity = "A execução falhou; consulte o erro do trabalho"
            else:
                current_activity = "Agente pronto para iniciar"
            latest_transition = session.scalar(select(GrowthStateTransition).order_by(
                GrowthStateTransition.transitioned_at.desc()).limit(1))
            granted = set(connection.granted_scopes.replace(",", " ").split()) if connection and connection.granted_scopes else set()
            session.commit()
            return {"control": {"mode": control.mode, "updatedAt": control.updated_at.isoformat(),
                    "execution": "SERVER_WORKER" if os.environ.get("GROWTH_WORKER_ENABLED") == "1" else "SERVER_QUEUE_ONLY",
                    "scheduler": "NOT_CONFIGURED"},
                "identity": {"status": "AVAILABLE" if connection and connection.status == "ACTIVE" else "UNKNOWN",
                    "source": "tiktok_connections.status" if connection else "No server connection record",
                    "connectedAt": connection.connected_at.isoformat() if connection else None},
                "capabilities": {"discover": "PARTIAL", "analyze": "PARTIAL", "create": "PARTIAL",
                    "render": "REAL", "delivery": "MANUAL", "autonomousPublish": "NOT_PROVEN",
                    "observe": "NOT_PROVEN" if not observations_count else "PARTIAL",
                    "learn": "NOT_PROVEN" if not learnings else "PARTIAL", "repeat": "NOT_PROVEN"},
                "currentActivity": current_activity,
                "currentJob": None if not current_job else {"jobId": current_job.job_id,
                    "type": current_job.job_type,
                    "state": "RECOVERING" if lease_expired else current_job.state,
                    "attempts": current_job.attempts, "owner": current_job.lease_owner,
                    "leaseGeneration": current_job.lease_generation,
                    "leaseAcquiredAt": current_job.lease_acquired_at.isoformat() if current_job.lease_acquired_at else None,
                    "leaseExpiresAt": current_job.lease_until.isoformat() if current_job.lease_until else None,
                    "heartbeatAt": current_job.heartbeat_at.isoformat() if current_job.heartbeat_at else None,
                    "attemptId": current_job.lease_attempt_id, "revision": current_job.revision,
                    "lastError": current_job.last_error},
                "lastTransition": None if not latest_transition else {"from":latest_transition.source_state,
                    "to":latest_transition.target_state,"reason":latest_transition.reason,
                    "at":latest_transition.transitioned_at.isoformat()},
                "observationAccess": {"followerCount": "AVAILABLE" if connection and connection.status == "ACTIVE" and "user.info.stats" in granted else "REQUIRES_APPROVAL",
                    "publicVideoMetrics": "AVAILABLE" if connection and connection.status == "ACTIVE" and "video.list" in granted else "REQUIRES_APPROVAL",
                    "watchTimeAndRetention": "UNKNOWN"},
                "counts": {"experiments": total_creatives, "rendered": total_rendered,
                    "ready": total_ready, "observations": observations_count,
                    "learningRecords": total_learnings, "pendingJobs": total_pending_jobs},
                "followers": None if follower_snapshot is None else {"value": follower_snapshot.followers,
                    "source": follower_snapshot.source, "observedAt": follower_snapshot.observed_at.isoformat(),
                    "evidenceRef": follower_snapshot.evidence_ref},
                "experiments": experiment_items, "media": media_items,
                "mediaStorage": {"provider": "RAILWAY_VOLUME", "configured": media_store is not None,
                    "integrityModel": "SHA256_READBACK", "publicAccess": False},
                "transitions": [{"experimentId": t.experiment_id, "jobId": t.job_id,
                    "from": t.source_state, "to": t.target_state, "reason": t.reason,
                    "at": t.transitioned_at.isoformat()} for t in session.scalars(
                        select(GrowthStateTransition).order_by(GrowthStateTransition.transitioned_at.desc()).limit(30)).all()],
                "observations": [{"creativeId": o.creative_id, "source": o.source, "evidenceRef": o.evidence_ref,
                    "observedAt": o.observed_at.isoformat(), "views": o.views, "likes": o.likes,
                    "comments": o.comments, "shares": o.shares} for o in observations]}

    @app.post("/v1/growth/creatives/{creative_id}/materialize", dependencies=[Depends(require_operator)])
    def materialize_durable_media(creative_id: str):
        """Queue one auditable, idempotent render for a legacy READY creative; never publish."""
        if media_store is None:
            raise HTTPException(503, "Durable media storage is not configured")
        artifact_to_verify = None
        artifact_job_type = None
        with Session(engine) as session:
            control = session.scalar(select(GrowthControl).where(
                GrowthControl.control_id == "default").with_for_update())
            if control is None or control.mode != "ACTION_REQUIRED":
                raise HTTPException(409, "Durable materialization requires ACTION_REQUIRED control mode")
            creative = session.scalar(select(GrowthCreative).where(
                GrowthCreative.creative_id == creative_id).with_for_update())
            if creative is None:
                raise HTTPException(404, "Unknown creative")
            idempotency_key = creative_id + ":MATERIALIZE_DURABLE_MEDIA"
            existing_job = session.scalar(select(GrowthJob).where(
                GrowthJob.idempotency_key == idempotency_key))
            if existing_job and existing_job.state in {"PENDING", "RUNNING", "RETRY"}:
                if creative.state not in {"READY", "RENDERING"}:
                    raise HTTPException(409, "Active materialization job conflicts with creative state")
                return {"creativeId": creative_id, "experimentId": creative.experiment_id,
                    "jobId": existing_job.job_id, "jobType": existing_job.job_type,
                    "jobState": existing_job.state, "duplicate": True,
                    "mediaState": "MATERIALIZATION_PENDING", "delivery": "UNCHANGED_NOT_CONFIRMED"}

            if creative.state != "READY":
                raise HTTPException(409, "Only a READY creative can be durably materialized")

            artifacts = session.scalars(select(GrowthMediaArtifact).where(
                GrowthMediaArtifact.creative_id == creative_id).order_by(
                    GrowthMediaArtifact.created_at.desc())).all()
            if artifacts:
                verified = [artifact for artifact in artifacts if
                    artifact.quality_status == "QUALITY_PASS" and artifact.storage_state == "STORED_VERIFIED"]
                if len(artifacts) != 1 or len(verified) != 1:
                    raise HTTPException(409, "Existing artifact history needs integrity review; no rerender was queued")
                artifact_to_verify = verified[0]
                artifact_job = session.get(GrowthJob, artifact_to_verify.render_job_id)
                artifact_job_type = artifact_job.job_type if artifact_job else "UNKNOWN"
            else:
                try:
                    media_store.preflight()
                except MediaStorageError as exc:
                    raise HTTPException(503, f"Durable media storage unavailable: {type(exc).__name__}") from None

                jobs = session.scalars(select(GrowthJob).where(
                    GrowthJob.creative_id == creative_id,
                    GrowthJob.job_type.in_(("RENDER_VIDEO", "PREPARE_ASSETS"))
                ).order_by(GrowthJob.created_at.desc())).all()
                active = next((job for job in jobs if job.state in {"PENDING", "RUNNING", "RETRY"}), None)
                if active:
                    raise HTTPException(409, "An existing render job is active; no concurrent render was queued")
                if existing_job:
                    raise HTTPException(409,
                        f"Materialization job is terminal ({existing_job.state}); no rerender was queued")
                try:
                    job = enqueue_job(session, creative_id, "MATERIALIZE_DURABLE_MEDIA")
                    record_transition(session, creative.state, creative.state,
                        "operator requested durable media materialization; TikTok delivery was not invoked",
                        creative.experiment_id, job.job_id)
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    existing = session.scalar(select(GrowthJob).where(
                        GrowthJob.creative_id == creative_id,
                        GrowthJob.idempotency_key == creative_id + ":MATERIALIZE_DURABLE_MEDIA"))
                    if existing is None:
                        raise HTTPException(409, "Concurrent materialization request conflicted; retry safely") from None
                    return {"creativeId": creative_id, "experimentId": creative.experiment_id,
                        "jobId": existing.job_id, "jobType": existing.job_type, "jobState": existing.state,
                        "duplicate": True,
                        "mediaState": "MATERIALIZATION_PENDING" if existing.state in {"PENDING", "RUNNING", "RETRY"}
                            else "MATERIALIZATION_ACCEPTED",
                        "delivery": "UNCHANGED_NOT_CONFIRMED"}
                return {"creativeId": creative_id, "experimentId": creative.experiment_id,
                    "jobId": job.job_id, "jobType": job.job_type, "jobState": job.state,
                    "duplicate": False, "mediaState": "MATERIALIZATION_PENDING",
                    "delivery": "UNCHANGED_NOT_CONFIRMED"}

        try:
            readback = media_store.verify_object(artifact_to_verify.object_key,
                expected_sha256=artifact_to_verify.sha256,
                expected_size_bytes=artifact_to_verify.size_bytes,
                expected_content_type=artifact_to_verify.content_type)
        except MediaArtifactMissing:
            with Session(engine) as session:
                row = session.get(GrowthMediaArtifact, artifact_to_verify.artifact_id)
                if row:
                    row.storage_state = "ARTIFACT_MISSING"
                    row.failure_reason = "materialization idempotency readback found no canonical object"
                    session.commit()
            raise HTTPException(503, "Existing durable media artifact is missing; no rerender was queued") from None
        except MediaArtifactCorrupt:
            with Session(engine) as session:
                row = session.get(GrowthMediaArtifact, artifact_to_verify.artifact_id)
                if row:
                    row.storage_state = "ARTIFACT_CORRUPT"
                    row.failure_reason = "materialization idempotency readback failed integrity verification"
                    session.commit()
            raise HTTPException(503, "Existing durable media artifact is corrupt; no rerender was queued") from None
        except MediaStorageError:
            raise HTTPException(503, "Durable media storage is unavailable") from None
        return {"creativeId": artifact_to_verify.creative_id,
            "experimentId": artifact_to_verify.experiment_id,
            "jobId": artifact_to_verify.render_job_id,
            "jobType": artifact_job_type, "jobState": "SUCCEEDED",
            "duplicate": True, "artifactId": artifact_to_verify.artifact_id,
            "objectKey": artifact_to_verify.object_key, "sha256": readback.sha256,
            "sizeBytes": readback.size_bytes, "qualityStatus": artifact_to_verify.quality_status,
            "storageState": artifact_to_verify.storage_state, "mediaState": "MEDIA_READY",
            "videoUrl": f"/v1/growth/creatives/{artifact_to_verify.creative_id}/video",
            "delivery": "UNCHANGED_NOT_CONFIRMED"}

    @app.post("/v1/growth/run", dependencies=[Depends(require_operator)])
    def run_first_experiment():
        """Discover current public BR signals, select deterministically and create one original plan."""
        with Session(engine) as session:
            control = control_row(session)
            mode = control.mode
            previous_creatives = session.scalar(select(func.count(GrowthCreative.creative_id))) or 0
        if mode not in {"READY", "RUNNING"}:
            raise HTTPException(409, f"Growth agent is {mode.lower()}")
        if mode == "RUNNING" and previous_creatives:
            raise HTTPException(409, "A cycle is already active or waiting for owner confirmation")
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
            if control_row(session).mode not in {"READY", "RUNNING"}:
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
                previous_creatives = session.scalars(select(GrowthCreative).join(TrendSignal,
                    GrowthCreative.trend_id == TrendSignal.trend_id).where(
                        func.lower(TrendSignal.topic) == chosen.topic.casefold())).all()
                previous_hook_counts = Counter()
                for previous in previous_creatives:
                    previous_hook_counts[json.loads(previous.plan_json).get("hookFamily", "question")] += 1
                hook_family = choose_hook_family(candidate, dict(previous_hook_counts))
                plan = build_creative_plan(candidate, niche_name, hook_family)
                plan["sourceEvidence"].update({"geography": chosen.geography,
                    "collectedAt": chosen.collected_at.isoformat(), "observedAt": chosen.observed_at.isoformat(),
                    "rankingComponents": chosen_score["components"], "rankingScore": chosen_score["score"],
                    "selectionReason": "highest reproducible fresh BR public-search score; TikTok engagement is UNKNOWN",
                    "hookFamily": hook_family, "hookSelection": "least-used style family for this topic; deterministic exploration"})
                creative = GrowthCreative(creative_id=creative_id, niche_id=niche_id, trend_id=chosen.trend_id,
                    experiment_id=experiment_id, plan_json=canonical_plan(plan), evidence_ref=chosen.source_ref,
                    state="SCRIPTED", purpose="EXPERIMENT", creative_learning_eligible=False,
                    style_baseline_eligible=False,
                    exclusion_reason="AWAITING_QUALITY_PUBLICATION_AND_OBSERVATION",
                    quality_status="NOT_EVALUATED", quality_json="{}", created_at=now)
                session.add(creative)
                session.commit()
            if creative.state == "SCRIPTED":
                job = enqueue_job(session, creative.creative_id, "PREPARE_ASSETS")
                record_transition(session, "SCRIPTED", "QUEUED", "idempotent render job enqueued",
                                  creative.experiment_id, job.job_id)
                session.commit()
            plan = json.loads(creative.plan_json)
            return {"state": creative.state, "duplicate": duplicate, "creativeId": creative.creative_id,
                "experimentId": creative.experiment_id, "source": chosen.source,
                "market": "BR", "geography": chosen.geography, "languageSignal": chosen.language,
                "ranking": ranking, "selected": {"trendId": chosen.trend_id, "topic": chosen.topic,
                    "score": chosen_score["score"], "components": chosen_score["components"]},
                "plan": plan, "jobState": "PENDING" if creative.state == "SCRIPTED" else creative.state,
                "videoUrl": f"/v1/growth/creatives/{creative.creative_id}/video",
                "delivery": {"status": "NOT_SENT", "reason": "TikTok Content Posting scope video.upload is not currently granted"}}

    @app.get("/v1/growth/creatives/{creative_id}/video", dependencies=[Depends(require_operator)])
    def render_experiment_video(creative_id: str):
        with Session(engine) as session:
            if control_row(session).mode not in {"READY", "RUNNING", "ACTION_REQUIRED", "PAUSED"}:
                raise HTTPException(409, "Growth agent is paused or stopped")
            creative = session.get(GrowthCreative, creative_id)
            if not creative:
                raise HTTPException(404, "Unknown creative")
            if media_store is None:
                raise HTTPException(503, "Durable media storage is not configured")
            artifact = session.scalar(select(GrowthMediaArtifact).where(
                GrowthMediaArtifact.creative_id == creative_id,
                GrowthMediaArtifact.storage_state == "STORED_VERIFIED",
                GrowthMediaArtifact.quality_status == "QUALITY_PASS"
            ).order_by(GrowthMediaArtifact.created_at.desc()))
            if artifact is None:
                raise HTTPException(409, "No quality-passed, durably verified artifact is available")
            artifact_id, object_key = artifact.artifact_id, artifact.object_key
            digest, size_bytes = artifact.sha256, artifact.size_bytes
        try:
            verified = media_store.verify_object(object_key, expected_sha256=digest,
                                                 expected_size_bytes=size_bytes)
        except MediaArtifactMissing:
            with Session(engine) as session:
                row = session.get(GrowthMediaArtifact, artifact_id)
                if row:
                    row.storage_state = "ARTIFACT_MISSING"
                    row.failure_reason = "volume readback found no canonical object"
                    session.commit()
            raise HTTPException(503, "Durable media artifact is missing") from None
        except MediaArtifactCorrupt:
            with Session(engine) as session:
                row = session.get(GrowthMediaArtifact, artifact_id)
                if row:
                    row.storage_state = "ARTIFACT_CORRUPT"
                    row.failure_reason = "volume readback failed integrity verification"
                    session.commit()
            raise HTTPException(503, "Durable media integrity verification failed") from None
        except MediaStorageError:
            raise HTTPException(503, "Durable media storage is unavailable") from None
        return FileResponse(verified.path, media_type="video/mp4", filename=f"{creative_id}.mp4",
            headers={"ETag": f'"{digest}"', "X-Creative-SHA256": digest,
                     "X-Media-Artifact-ID": artifact_id, "X-Media-State": "MEDIA_READY"})

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
