"""Authenticated delivery endpoints. This module records delivery identity and evidence only."""
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .delivery_gateway import (delivery_summary, prepare_delivery_for_effect,
    record_android_handoff, record_owner_publication_report, reserve_android_handoff)
from .delivery_models import DeliveryEffect
from .growth_models import GrowthMediaArtifact
from .models import TikTokConnection
from .tiktok_provider import ProviderError, TikTokOfficialProvider


class PrepareDeliveryInput(BaseModel):
    action_contract_id: str = Field(min_length=1, max_length=36)
    effect_id: str = Field(min_length=1, max_length=36)
    target: Literal["ANDROID_SHARE_HANDOFF", "TIKTOK_OFFICIAL_DIRECT_POST", "TIKTOK_OFFICIAL_UPLOAD_DRAFT"]
    target_account_id: str | None = Field(default=None, max_length=200)


class HandoffInput(BaseModel):
    artifact_sha256: str = Field(min_length=64, max_length=64)
    observed_at: datetime


class OwnerReportInput(BaseModel):
    publication_identity: str = Field(min_length=1, max_length=1000)
    observed_at: datetime


def _provider() -> TikTokOfficialProvider:
    return TikTokOfficialProvider(
        enabled=os.environ.get("TIKTOK_REAL_DISPATCH_ENABLED") == "1",
        content_posting_approved=os.environ.get("TIKTOK_CONTENT_POSTING_APPROVED") == "1",
        certified=os.environ.get("TIKTOK_REAL_DISPATCH_CERTIFIED") == "1",
    )


def _connection_state(session: Session):
    connection = session.scalar(select(TikTokConnection).where(
        TikTokConnection.operator_id == "primary"))
    scopes = set()
    if connection and connection.granted_scopes:
        scopes = set(connection.granted_scopes.replace(",", " ").split())
    return connection, scopes


def add_delivery_routes(app, engine, require_operator):
    @app.get("/v1/deliveries/tiktok/capabilities", dependencies=[Depends(require_operator)])
    def tiktok_delivery_capabilities():
        with Session(engine) as session:
            connection, scopes = _connection_state(session)
            expires = None if not connection else connection.access_expires_at
            if expires is not None and (expires.tzinfo is None or expires.utcoffset() is None):
                expires = expires.replace(tzinfo=timezone.utc)
            active = bool(connection and connection.status == "ACTIVE" and expires
                and expires > datetime.now(timezone.utc))
            return _provider().capabilities(scopes, active=active)

    @app.post("/v1/deliveries/prepare", dependencies=[Depends(require_operator)])
    def prepare_delivery(item: PrepareDeliveryInput):
        with Session(engine) as session:
            try:
                delivery = prepare_delivery_for_effect(session,
                    action_contract_id=item.action_contract_id, effect_id=item.effect_id,
                    target=item.target, target_account_id=item.target_account_id)
                session.commit()
                return {**delivery_summary(delivery), "duplicateSafe": True}
            except KeyError:
                session.rollback()
                raise HTTPException(404, "Delivery binding not found") from None
            except (ValueError, RuntimeError) as exc:
                session.rollback()
                raise HTTPException(409, str(exc)) from None

    @app.get("/v1/deliveries/{delivery_id}", dependencies=[Depends(require_operator)])
    def get_delivery(delivery_id: str):
        with Session(engine) as session:
            delivery = session.get(DeliveryEffect, delivery_id)
            if delivery is None:
                raise HTTPException(404, "Unknown delivery")
            return delivery_summary(delivery)

    @app.post("/v1/deliveries/{delivery_id}/reserve-handoff", dependencies=[Depends(require_operator)])
    def reserve_handoff(delivery_id: str):
        with Session(engine) as session:
            try:
                delivery, event = reserve_android_handoff(session, delivery_id=delivery_id)
                session.commit()
                return {"deliveryId": delivery.delivery_id, "quotaEventId": event.event_id,
                    "state": delivery.state, "reserved": True}
            except KeyError:
                session.rollback()
                raise HTTPException(404, "Unknown delivery") from None
            except (ValueError, RuntimeError) as exc:
                session.rollback()
                raise HTTPException(409, str(exc)) from None

    @app.post("/v1/deliveries/{delivery_id}/handoff", dependencies=[Depends(require_operator)])
    def handoff_delivery(delivery_id: str, item: HandoffInput):
        with Session(engine) as session:
            try:
                delivery, evidence = record_android_handoff(session, delivery_id=delivery_id,
                    artifact_sha256=item.artifact_sha256, observed_at=item.observed_at)
                session.commit()
                return {**delivery_summary(delivery), "evidenceId": evidence.evidence_id,
                    "publication": "UNKNOWN"}
            except KeyError:
                session.rollback()
                raise HTTPException(404, "Unknown delivery") from None
            except (ValueError, RuntimeError) as exc:
                session.rollback()
                raise HTTPException(409, str(exc)) from None

    @app.post("/v1/deliveries/{delivery_id}/owner-report", dependencies=[Depends(require_operator)])
    def owner_report(delivery_id: str, item: OwnerReportInput):
        with Session(engine) as session:
            try:
                evidence = record_owner_publication_report(session, delivery_id=delivery_id,
                    publication_identity=item.publication_identity, observed_at=item.observed_at)
                session.commit()
                return {"deliveryId": delivery_id, "evidenceId": evidence.evidence_id,
                    "classification": "OWNER_REPORTED", "publicationConfirmed": False}
            except KeyError:
                session.rollback()
                raise HTTPException(404, "Unknown delivery") from None
            except (ValueError, RuntimeError) as exc:
                session.rollback()
                raise HTTPException(409, str(exc)) from None

    @app.post("/v1/deliveries/{delivery_id}/tiktok-dry-run", dependencies=[Depends(require_operator)])
    def tiktok_dry_run(delivery_id: str):
        with Session(engine) as session:
            delivery = session.get(DeliveryEffect, delivery_id)
            if delivery is None:
                raise HTTPException(404, "Unknown delivery")
            if delivery.target not in {"TIKTOK_OFFICIAL_DIRECT_POST", "TIKTOK_OFFICIAL_UPLOAD_DRAFT"}:
                raise HTTPException(409, "Delivery is not bound to an official TikTok posting target")
            artifact = session.get(GrowthMediaArtifact, delivery.artifact_id)
            connection, scopes = _connection_state(session)
            active = bool(connection and connection.status == "ACTIVE")
            try:
                return _provider().dry_run(
                    target=delivery.target,
                    granted_scopes=scopes,
                    active=active,
                    artifact_verified=bool(artifact and artifact.storage_state == "STORED_VERIFIED"
                        and artifact.quality_status == "QUALITY_PASS"
                        and artifact.sha256 == delivery.artifact_sha256),
                    contract_valid=bool(delivery.action_contract_id and delivery.effect_id),
                    target_bound=bool(delivery.target_account_id),
                )
            except ProviderError as exc:
                raise HTTPException(409, str(exc)) from None
