"""Server-owned UK manual launch authority. No external publishing occurs here."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .connection_api import utc
from .models import (CapitalAuthority, CreativeApproval, CreativeArtifact, Experiment,
                     LaunchIntent, OpportunityEvidence, ProductClaim, ProductEvidence)


def now():
    return datetime.now(timezone.utc)


def ref(value: str) -> str:
    if len(value.strip()) < 6 or any(fragment in value.lower() for fragment in ('password', 'secret', 'access_token', 'refresh_token', 'passport')):
        raise ValueError('A safe evidence reference is required')
    return value


class CapitalInput(BaseModel):
    authority_id: str = Field(min_length=1, max_length=100)
    available_capital_gbp: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    capital_limit_gbp: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    loss_limit_gbp: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    minimum_allocation_score: int = Field(ge=0, le=100)
    evidence_ref: str = Field(min_length=6, max_length=500)
    _validate_ref = field_validator('evidence_ref')(ref)


class ProductInput(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    listing_ref: str = Field(min_length=6, max_length=500)
    evidence_ref: str = Field(min_length=6, max_length=500)
    observed_at: datetime
    _validate_ref = field_validator('evidence_ref')(ref)


class OpportunityInput(BaseModel):
    opportunity_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    capital_required_gbp: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    maximum_loss_gbp: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    allocation_score: int = Field(ge=0, le=100)
    evidence_ref: str = Field(min_length=6, max_length=500)
    observed_at: datetime
    _validate_ref = field_validator('evidence_ref')(ref)


class ClaimInput(BaseModel):
    claim_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    state: Literal['VERIFIED', 'SUPPORTED', 'UNKNOWN', 'BLOCKED']
    evidence_ref: str | None = Field(default=None, max_length=500)

    @field_validator('evidence_ref')
    @classmethod
    def safe_ref(cls, value):
        return ref(value) if value is not None else None


class CreativeInput(BaseModel):
    creative_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50000)
    claim_ids: list[str] = Field(min_length=1, max_length=50)
    evidence_ref: str = Field(min_length=6, max_length=500)
    _validate_ref = field_validator('evidence_ref')(ref)


class ApprovalInput(BaseModel):
    approval_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(min_length=1, max_length=100)
    evidence_ref: str = Field(min_length=6, max_length=500)
    _validate_ref = field_validator('evidence_ref')(ref)


class LaunchInput(BaseModel):
    packet_id: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=100)
    approval_id: str = Field(min_length=1, max_length=100)


def fresh(timestamp):
    return now() - timedelta(days=30) < utc(timestamp) <= now()


def capital_check(session, opportunity):
    authority = session.scalar(select(CapitalAuthority).where(CapitalAuthority.operator_id == 'primary',
        CapitalAuthority.status == 'ACTIVE').order_by(CapitalAuthority.approved_at.desc()))
    if authority is None:
        raise HTTPException(403, 'Capital authority missing')
    if (opportunity.capital_required_gbp > authority.available_capital_gbp or
        opportunity.capital_required_gbp > authority.capital_limit_gbp or
        opportunity.maximum_loss_gbp > authority.loss_limit_gbp or
        opportunity.allocation_score < authority.minimum_allocation_score):
        raise HTTPException(403, 'Capital, loss or allocation limit exceeded')
    return authority


def truth_hash(session, product_id, creative):
    claims = session.scalars(select(ProductClaim).where(ProductClaim.product_id == product_id).order_by(ProductClaim.claim_id)).all()
    by_id = {claim.claim_id: claim for claim in claims}
    chosen = json.loads(creative.claim_ids_json)
    if not chosen or any(claim_id not in by_id for claim_id in chosen):
        raise HTTPException(403, 'ProductTruth missing')
    # All facts on the product are part of the approval snapshot, including later BLOCKED revisions.
    for claim_id in chosen:
        claim = by_id[claim_id]
        if claim.state not in {'SUPPORTED', 'VERIFIED'} or not claim.evidence_ref:
            raise HTTPException(403, 'Unknown or blocked claim')
        if any(other.text == claim.text and other.state in {'BLOCKED', 'UNKNOWN'} for other in claims):
            raise HTTPException(403, 'Claim has a blocking revision')
    facts = [(c.claim_id, c.text, c.state, c.evidence_ref) for c in claims]
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_launch(session, experiment, intent):
    creative = session.get(CreativeArtifact, experiment.creative_id)
    opportunity = session.get(OpportunityEvidence, experiment.opportunity_id)
    product = session.get(ProductEvidence, experiment.product_id)
    approval = session.get(CreativeApproval, intent.approval_id)
    if (not creative or not opportunity or not product or not approval or
        opportunity.product_id != experiment.product_id or not fresh(product.observed_at) or
        not fresh(opportunity.observed_at)):
        raise HTTPException(403, 'Launch evidence incomplete or expired')
    capital = capital_check(session, opportunity)
    fingerprint = truth_hash(session, experiment.product_id, creative)
    if (capital.authority_id != intent.capital_authority_id or fingerprint != intent.truth_hash or
        approval.creative_id != creative.creative_id or approval.content_hash != creative.content_hash or
        approval.truth_hash != fingerprint):
        raise HTTPException(403, 'Launch authority or approval changed')


def add_governance_routes(app, engine, require_operator, require_manual_authority):
    router = APIRouter(prefix='/v1')

    def commit(session):
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, 'Conflicting or concurrent business identity') from None

    @router.post('/capital-authority', dependencies=[Depends(require_manual_authority)])
    def capital(item: CapitalInput):
        with Session(engine) as session:
            existing = session.get(CapitalAuthority, item.authority_id)
            if existing:
                if any(getattr(existing, k) != v for k, v in item.model_dump().items()):
                    raise HTTPException(409, 'Conflicting capital authority id')
                return {'authorityId': existing.authority_id, 'status': existing.status, 'duplicate': True}
            for active in session.scalars(select(CapitalAuthority).where(CapitalAuthority.operator_id == 'primary',
                CapitalAuthority.status == 'ACTIVE').with_for_update()):
                active.status = 'REVOKED'
            session.add(CapitalAuthority(**item.model_dump(), operator_id='primary', approved_by='primary',
                approved_at=now(), status='ACTIVE'))
            commit(session)
            return {'authorityId': item.authority_id, 'status': 'ACTIVE', 'duplicate': False}

    @router.get('/capital-authority', dependencies=[Depends(require_operator)])
    def current_capital():
        with Session(engine) as session:
            record = session.scalar(select(CapitalAuthority).where(CapitalAuthority.operator_id == 'primary',
                CapitalAuthority.status == 'ACTIVE').order_by(CapitalAuthority.approved_at.desc()))
            return {'status': 'UNKNOWN'} if record is None else {'status': 'ACTIVE', 'authorityId': record.authority_id,
                'availableCapitalGbp': str(record.available_capital_gbp), 'capitalLimitGbp': str(record.capital_limit_gbp),
                'lossLimitGbp': str(record.loss_limit_gbp), 'minimumAllocationScore': record.minimum_allocation_score,
                'approvedAt': record.approved_at.isoformat(), 'evidenceRef': record.evidence_ref}

    @router.post('/products', dependencies=[Depends(require_manual_authority)])
    def product(item: ProductInput):
        if item.observed_at.tzinfo is None or not fresh(item.observed_at):
            raise HTTPException(422, 'Product observation must be recent with timezone')
        with Session(engine) as session:
            old = session.get(ProductEvidence, item.product_id)
            if old:
                if any(getattr(old, k) != v for k, v in item.model_dump().items() if k != 'observed_at') or utc(old.observed_at) != utc(item.observed_at):
                    raise HTTPException(409, 'Conflicting product identity')
                return {'productId': item.product_id, 'duplicate': True}
            session.add(ProductEvidence(**item.model_dump()))
            commit(session)
            return {'productId': item.product_id, 'duplicate': False}

    @router.post('/opportunities', dependencies=[Depends(require_manual_authority)])
    def opportunity(item: OpportunityInput):
        if item.observed_at.tzinfo is None or not fresh(item.observed_at):
            raise HTTPException(422, 'Opportunity evidence must be recent with timezone')
        with Session(engine) as session:
            if not session.get(ProductEvidence, item.product_id):
                raise HTTPException(409, 'Product evidence missing')
            old = session.get(OpportunityEvidence, item.opportunity_id)
            if old:
                if any(getattr(old, k) != v for k, v in item.model_dump().items() if k != 'observed_at') or utc(old.observed_at) != utc(item.observed_at):
                    raise HTTPException(409, 'Conflicting opportunity identity')
                return {'opportunityId': item.opportunity_id, 'duplicate': True}
            session.add(OpportunityEvidence(**item.model_dump()))
            commit(session)
            return {'opportunityId': item.opportunity_id, 'duplicate': False}

    @router.post('/product-claims', dependencies=[Depends(require_manual_authority)])
    def claim(item: ClaimInput):
        if item.state in {'SUPPORTED', 'VERIFIED'} and not item.evidence_ref:
            raise HTTPException(422, 'Claim evidence required')
        with Session(engine) as session:
            if not session.get(ProductEvidence, item.product_id):
                raise HTTPException(409, 'Product evidence missing')
            old = session.get(ProductClaim, item.claim_id)
            if old:
                if any(getattr(old, k) != v for k, v in item.model_dump().items()):
                    raise HTTPException(409, 'Conflicting claim identity')
                return {'claimId': item.claim_id, 'duplicate': True}
            session.add(ProductClaim(**item.model_dump(), recorded_at=now()))
            commit(session)
            return {'claimId': item.claim_id, 'duplicate': False}

    @router.get('/product-claims/{product_id}', dependencies=[Depends(require_operator)])
    def product_truth(product_id: str):
        with Session(engine) as session:
            if not session.get(ProductEvidence, product_id):
                raise HTTPException(404, 'Unknown product')
            claims = session.scalars(select(ProductClaim).where(ProductClaim.product_id == product_id)
                .order_by(ProductClaim.recorded_at)).all()
            return {'productId': product_id, 'claims': [{'claimId': c.claim_id, 'text': c.text,
                'state': c.state, 'evidenceRef': c.evidence_ref, 'recordedAt': c.recorded_at.isoformat()}
                for c in claims], 'authority': 'SERVER'}

    @router.post('/creatives', dependencies=[Depends(require_manual_authority)])
    def creative(item: CreativeInput):
        if len(set(item.claim_ids)) != len(item.claim_ids):
            raise HTTPException(422, 'Duplicate creative claim')
        with Session(engine) as session:
            experiment = session.get(Experiment, item.experiment_id)
            if not experiment or experiment.creative_id != item.creative_id:
                raise HTTPException(409, 'Creative experiment trace mismatch')
            digest = hashlib.sha256(item.content.encode()).hexdigest()
            ids = json.dumps(item.claim_ids, separators=(',', ':'))
            old = session.get(CreativeArtifact, item.creative_id)
            if old:
                if (old.experiment_id, old.content_hash, old.claim_ids_json, old.evidence_ref) != (item.experiment_id, digest, ids, item.evidence_ref):
                    raise HTTPException(409, 'Creative changed; a new experiment/creative identity is required')
                return {'creativeId': item.creative_id, 'contentHash': digest, 'duplicate': True}
            record = CreativeArtifact(creative_id=item.creative_id, experiment_id=item.experiment_id,
                content_hash=digest, claim_ids_json=ids, evidence_ref=item.evidence_ref, created_at=now())
            truth_hash(session, experiment.product_id, record)
            session.add(record)
            commit(session)
            return {'creativeId': item.creative_id, 'contentHash': digest, 'duplicate': False}

    @router.post('/creative-approvals', dependencies=[Depends(require_manual_authority)])
    def approve(item: ApprovalInput):
        with Session(engine) as session:
            experiment = session.get(Experiment, item.experiment_id)
            creative = session.get(CreativeArtifact, item.creative_id)
            if not experiment or not creative or experiment.creative_id != item.creative_id or creative.experiment_id != item.experiment_id:
                raise HTTPException(409, 'Experiment/creative trace mismatch')
            fingerprint = truth_hash(session, experiment.product_id, creative)
            old = session.get(CreativeApproval, item.approval_id)
            if old:
                if (old.creative_id, old.experiment_id, old.evidence_ref, old.content_hash, old.truth_hash) != (
                    item.creative_id, item.experiment_id, item.evidence_ref, creative.content_hash, fingerprint):
                    raise HTTPException(409, 'Conflicting or stale approval')
                return {'approvalId': item.approval_id, 'duplicate': True}
            session.add(CreativeApproval(**item.model_dump(), approved_by='primary', approved_at=now(),
                content_hash=creative.content_hash, truth_hash=fingerprint))
            commit(session)
            return {'approvalId': item.approval_id, 'duplicate': False}

    @router.post('/launch-intents', dependencies=[Depends(require_manual_authority)])
    def launch(item: LaunchInput):
        with Session(engine) as session:
            experiment = session.get(Experiment, item.experiment_id)
            approval = session.get(CreativeApproval, item.approval_id)
            if not experiment or not experiment.opportunity_id or not approval or approval.experiment_id != item.experiment_id:
                raise HTTPException(403, 'Frozen experiment and approval required')
            creative = session.get(CreativeArtifact, experiment.creative_id)
            opportunity = session.get(OpportunityEvidence, experiment.opportunity_id)
            product = session.get(ProductEvidence, experiment.product_id)
            if not creative or not opportunity or not product or opportunity.product_id != experiment.product_id or not fresh(product.observed_at) or not fresh(opportunity.observed_at):
                raise HTTPException(403, 'Fresh product and opportunity evidence required')
            capital = capital_check(session, opportunity)
            fingerprint = truth_hash(session, experiment.product_id, creative)
            if approval.creative_id != creative.creative_id or approval.content_hash != creative.content_hash or approval.truth_hash != fingerprint:
                raise HTTPException(403, 'Approval no longer matches ProductTruth or creative')
            existing = session.get(LaunchIntent, item.packet_id)
            if existing:
                if (existing.experiment_id, existing.approval_id, existing.capital_authority_id, existing.truth_hash) != (
                    item.experiment_id, item.approval_id, capital.authority_id, fingerprint):
                    raise HTTPException(409, 'Conflicting or stale launch intent')
                return {'packetId': item.packet_id, 'duplicate': True, 'externalExecutionAllowed': False}
            if session.scalar(select(LaunchIntent).where(LaunchIntent.experiment_id == item.experiment_id)):
                raise HTTPException(409, 'Experiment already has a launch intent')
            session.add(LaunchIntent(**item.model_dump(), capital_authority_id=capital.authority_id,
                truth_hash=fingerprint, created_at=now()))
            commit(session)
            return {'packetId': item.packet_id, 'duplicate': False, 'externalExecutionAllowed': False,
                'status': 'READY_FOR_MANUAL_PUBLICATION'}

    @router.get('/governance/{experiment_id}', dependencies=[Depends(require_operator)])
    def governance(experiment_id: str):
        with Session(engine) as session:
            experiment = session.get(Experiment, experiment_id)
            if not experiment:
                raise HTTPException(404, 'Unknown experiment')
            intent = session.scalar(select(LaunchIntent).where(LaunchIntent.experiment_id == experiment_id))
            approval = session.get(CreativeApproval, intent.approval_id) if intent else None
            return {'experimentId': experiment_id, 'launchIntent': intent.packet_id if intent else None,
                'approvalId': approval.approval_id if approval else None, 'approvedAt': approval.approved_at.isoformat()
                if approval else None, 'authority': 'SERVER', 'externalExecutionAllowed': False}

    app.include_router(router)
