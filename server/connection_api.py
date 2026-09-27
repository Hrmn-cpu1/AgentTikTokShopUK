"""One-operator session, Login Kit identity, and fail-closed capability projection."""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OperatorSession, TikTokConnection, TikTokOAuthIntent
from .tiktok_provider import OfficialTikTokProvider, ProviderError, Tokens


def now_utc():
    return datetime.now(timezone.utc)


def utc(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


class LoginInput(BaseModel):
    access_key: str = Field(min_length=1)


class ManualVerificationInput(BaseModel):
    uk_market_evidence_ref: str = Field(min_length=6, max_length=500)
    affiliate_evidence_ref: str = Field(min_length=6, max_length=500)

    @field_validator("uk_market_evidence_ref", "affiliate_evidence_ref")
    @classmethod
    def no_sensitive_data(cls, value: str) -> str:
        if "?" in value or re.search(r"password|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|bearer|passport|bank[_ -]?account", value, re.I):
            raise ValueError("Use a safe evidence reference, not credentials or identity documents")
        return value


def add_connection_routes(app, engine, provider=None, *, login_secret=None, encryption_key=None):
    login_secret = login_secret or os.getenv("OPERATOR_LOGIN_SECRET")
    encryption_key = encryption_key or os.getenv("TIKTOK_TOKEN_ENCRYPTION_KEY")
    if login_secret is not None and len(login_secret) < 32:
        raise RuntimeError("OPERATOR_LOGIN_SECRET must have at least 32 characters")
    cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key) if encryption_key else None
    key = os.getenv("TIKTOK_CLIENT_KEY")
    secret = os.getenv("TIKTOK_CLIENT_SECRET")
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")
    if provider is None and all((key, secret, redirect_uri)):
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "https" or parsed.path != "/v1/tiktok/callback" or parsed.query or parsed.fragment or not parsed.netloc:
            raise RuntimeError("TIKTOK_REDIRECT_URI must be an HTTPS callback /v1/tiktok/callback without parameters")
        provider = OfficialTikTokProvider(key, secret, redirect_uri)
    router = APIRouter()

    def operator(request: Request, session: Session, *, csrf=False) -> OperatorSession:
        cookie = request.cookies.get("operator_session", "")
        if not cookie:
            raise HTTPException(401, "Operator login required")
        record = session.get(OperatorSession, digest(cookie))
        if record is None or utc(record.expires_at) <= now_utc():
            raise HTTPException(401, "Operator session expired")
        if csrf and not hmac.compare_digest(record.csrf_hash, digest(request.headers.get("x-csrf-token", ""))):
            raise HTTPException(403, "Invalid operator request")
        return record

    def require_ready():
        if provider is None or cipher is None:
            raise HTTPException(503, "TikTok developer app or server-side encryption is not configured")
        return provider, cipher

    def connection(session: Session):
        return session.scalar(select(TikTokConnection).where(TikTokConnection.operator_id == "primary").with_for_update())

    def save_tokens(record: TikTokConnection, tokens: Tokens, crypto: Fernet, now: datetime):
        record.encrypted_access_token = crypto.encrypt(tokens.access_token.encode()).decode()
        record.encrypted_refresh_token = crypto.encrypt(tokens.refresh_token.encode()).decode()
        record.granted_scopes = tokens.scope
        record.access_expires_at = now + timedelta(seconds=tokens.expires_in)
        record.refresh_expires_at = now + timedelta(seconds=tokens.refresh_expires_in)
        record.last_validated_at = now
        record.status = "ACTIVE"

    def validate(record: TikTokConnection, session: Session):
        if record.status != "ACTIVE":
            return
        current = now_utc()
        if utc(record.refresh_expires_at) <= current:
            record.status = "EXPIRED"
        elif utc(record.access_expires_at) <= current + timedelta(minutes=5):
            service, crypto = require_ready()
            try:
                token = crypto.decrypt(record.encrypted_refresh_token.encode()).decode()
                replacement = service.refresh(token)
                if replacement.open_id != record.provider_user_id:
                    record.status = "UNKNOWN"
                else:
                    save_tokens(record, replacement, crypto, current)
            except Exception:  # Fail closed; never print a provider response or credential.
                record.status = "REFRESH_FAILED"
        elif utc(record.last_validated_at) + timedelta(minutes=15) <= current:
            service, crypto = require_ready()
            try:
                access = crypto.decrypt(record.encrypted_access_token.encode()).decode()
                open_id, display_name = service.identity(access)
                if open_id != record.provider_user_id:
                    record.status = "UNKNOWN"
                else:
                    record.display_name = display_name
                    record.last_validated_at = current
            except Exception:
                record.status = "UNKNOWN"
        session.commit()

    def public_state(record: TikTokConnection | None):
        base = {name: "UNKNOWN" for name in ("IDENTITY", "TIKTOK_SHOP", "AFFILIATE",
            "PRODUCT_DISCOVERY", "CONTENT_PUBLISHING", "ORDER_READ", "COMMISSION_READ", "SETTLEMENT_READ")}
        if record is None:
            return {"connection": None, "capabilities": base, "mode": "BLOCKED"}
        if record.status == "REVOKED":
            base["IDENTITY"] = "BLOCKED"
        if record.status == "ACTIVE" and "user.info.basic" in record.granted_scopes.split(","):
            base["IDENTITY"] = "AVAILABLE"
            base["CONTENT_PUBLISHING"] = "REQUIRES_APPROVAL" if "video.publish" in record.granted_scopes.split(",") else "UNKNOWN"
        manual = bool(record.status == "ACTIVE" and record.manual_verified_at and
            utc(record.manual_verified_at) + timedelta(days=30) > now_utc() and
            record.manual_uk_evidence_ref and record.manual_affiliate_evidence_ref)
        return {"connection": {"connectionId": record.connection_id, "provider": "TIKTOK",
            "providerUserId": record.provider_user_id, "displayName": record.display_name,
            "connectedAt": record.connected_at.isoformat(), "lastValidatedAt": record.last_validated_at.isoformat(),
            "status": record.status, "tokenStatus": ("EXPIRING" if record.status == "ACTIVE" and
            utc(record.access_expires_at) <= now_utc() + timedelta(minutes=30) else record.status),
            "grantedScopes": record.granted_scopes.split(","),
            "manualVerification": {"source": "OPERATOR_ASSERTION", "ukMarketEvidenceRef": record.manual_uk_evidence_ref,
                "affiliateEvidenceRef": record.manual_affiliate_evidence_ref,
                "observedAt": record.manual_verified_at.isoformat() if record.manual_verified_at else None,
                "valid": manual}}, "capabilities": base,
            "mode": "MANUAL_VERIFIED" if manual else ("LIMITED" if base["IDENTITY"] == "AVAILABLE" else "BLOCKED")}

    @router.post("/v1/operator/login")
    def login(item: LoginInput, response: Response):
        if login_secret is None:
            raise HTTPException(503, "Operator login is not configured")
        if not hmac.compare_digest(item.access_key, login_secret):
            raise HTTPException(401, "Invalid operator credentials")
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(48)
        with Session(engine) as session:
            session.add(OperatorSession(session_hash=digest(session_token), csrf_hash=digest(csrf_token),
                expires_at=now_utc() + timedelta(hours=12)))
            session.commit()
        response.set_cookie("operator_session", session_token, httponly=True, secure=True,
            samesite="lax", max_age=12 * 3600, path="/")
        response.set_cookie("operator_csrf", csrf_token, httponly=False, secure=True,
            samesite="strict", max_age=12 * 3600, path="/")
        # CSRF belongs only to this authenticated browser session. It is not a provider credential.
        return {"authenticated": True, "csrfToken": csrf_token}

    @router.get("/v1/operator/session")
    def session_status(request: Request):
        with Session(engine) as session:
            operator(request, session)
        return {"authenticated": True}

    @router.get("/v1/tiktok/connection")
    def get_connection(request: Request):
        with Session(engine) as session:
            operator(request, session)
            record = connection(session)
            if record:
                validate(record, session)
            return {**public_state(record), "authorizationConfigured": provider is not None and cipher is not None}

    @router.get("/v1/tiktok/authorize")
    def authorize(request: Request):
        service, _ = require_ready()
        with Session(engine) as session:
            user_session = operator(request, session)
            state = secrets.token_urlsafe(48)
            session.add(TikTokOAuthIntent(state_hash=digest(state), session_hash=user_session.session_hash,
                expires_at=now_utc() + timedelta(minutes=5), platform="WEB"))
            session.commit()
        return RedirectResponse(service.authorization_url(state), status_code=302)

    @router.get("/v1/tiktok/authorize-native")
    def authorize_native(request: Request):
        service, _ = require_ready()
        with Session(engine) as session:
            user_session = operator(request, session)
            state = secrets.token_urlsafe(48)
            session.add(TikTokOAuthIntent(state_hash=digest(state), session_hash=user_session.session_hash,
                expires_at=now_utc() + timedelta(minutes=5), platform="ANDROID"))
            session.commit()
        return {"authorizationUrl": service.authorization_url(state)}

    @router.get("/v1/tiktok/callback")
    def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        service, crypto = require_ready()
        with Session(engine) as session:
            intent = session.scalar(select(TikTokOAuthIntent).where(
                TikTokOAuthIntent.state_hash == digest(state)).with_for_update()) if state else None
            if intent is None or intent.consumed_at or utc(intent.expires_at) <= now_utc():
                raise HTTPException(403, "Authorization state invalid or expired")
            if intent.platform == "WEB":
                user_session = operator(request, session)
                if intent.session_hash != user_session.session_hash:
                    raise HTTPException(403, "Authorization session mismatch")
            elif intent.platform == "ANDROID":
                owner = session.get(OperatorSession, intent.session_hash)
                if owner is None or utc(owner.expires_at) <= now_utc():
                    raise HTTPException(403, "Authorization session expired")
            else:
                raise HTTPException(403, "Authorization platform invalid")
            platform = intent.platform
            intent.consumed_at = now_utc()
            session.commit()  # Consume before external exchange: callback replay cannot duplicate effects.
        if error or not code:
            raise HTTPException(400, "TikTok authorization was declined")
        try:
            tokens = service.exchange(code)
            if "user.info.basic" not in tokens.scope.split(","):
                raise ProviderError("Identity scope was not granted")
            open_id, display_name = service.identity(tokens.access_token)
            if open_id != tokens.open_id:
                raise ProviderError("TikTok identity mismatch")
        except ProviderError:
            raise HTTPException(502, "TikTok identity could not be verified") from None
        with Session(engine) as session:
            record = connection(session)
            if record and record.provider_user_id != open_id:
                raise HTTPException(409, "A different TikTok identity is already recorded")
            current = now_utc()
            if record is None:
                record = TikTokConnection(connection_id=str(uuid4()), operator_id="primary", provider_user_id=open_id,
                    display_name=display_name, connected_at=current, access_expires_at=current,
                    refresh_expires_at=current, granted_scopes="", last_validated_at=current, status="UNKNOWN")
                session.add(record)
            else:
                # Reauthorization cannot silently reactivate an earlier manual Shop assertion.
                record.manual_verified_at = None
            record.display_name = display_name
            save_tokens(record, tokens, crypto, current)
            session.commit()
        return RedirectResponse("com.tiktokshopprofitagent.app://oauth-return" if platform == "ANDROID" else "/", status_code=303)

    @router.post("/v1/tiktok/disconnect")
    def disconnect(request: Request):
        service, crypto = require_ready()
        with Session(engine) as session:
            operator(request, session, csrf=True)
            record = connection(session)
            if record is None or record.status == "REVOKED":
                return public_state(record)
            # Remove operational authority before the provider call; failures cannot keep it active.
            record.status = "UNKNOWN"
            record.manual_verified_at = None
            session.commit()
            try:
                service.revoke(crypto.decrypt(record.encrypted_access_token.encode()).decode())
            except Exception:
                raise HTTPException(502, "Authorization disabled locally; TikTok revocation needs retry") from None
            record.status = "REVOKED"
            record.encrypted_access_token = None
            record.encrypted_refresh_token = None
            session.commit()
            return public_state(record)

    @router.post("/v1/tiktok/manual-verification")
    def manual_verification(request: Request, item: ManualVerificationInput):
        with Session(engine) as session:
            operator(request, session, csrf=True)
            record = connection(session)
            if record is None or record.status != "ACTIVE":
                raise HTTPException(409, "TikTok identity must be active")
            record.manual_uk_evidence_ref = item.uk_market_evidence_ref.strip()
            record.manual_affiliate_evidence_ref = item.affiliate_evidence_ref.strip()
            if len(record.manual_uk_evidence_ref) < 6 or len(record.manual_affiliate_evidence_ref) < 6:
                raise HTTPException(422, "Evidence references must be meaningful")
            record.manual_verified_at = now_utc()
            session.commit()
            return public_state(record)

    app.include_router(router)
    return operator
